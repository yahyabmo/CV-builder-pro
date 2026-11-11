"""En ligne : les personnes invitées, et leur liste chez Cloudflare Access.

La liste vit à deux endroits :

- ``data/acces.json``, lue par l'appli à chaque requête : une personne retirée perd
  l'accès tout de suite, même si sa session Cloudflare dure encore ;
- le groupe Cloudflare Access de l'appli, que l'appli réécrit à chaque changement : une
  adresse absente ne reçoit même pas de code de connexion.

L'administrateur (``CVB_ADMIN``, une ou plusieurs adresses séparées par des virgules)
entre toujours, sans figurer dans la liste.

Réglages Cloudflare, facultatifs (sans eux, seule la liste de l'appli change) :
``CF_API_TOKEN`` (droit « Access: Organizations, Identity Providers, and Groups » en
écriture, rien d'autre), ``CF_ACCOUNT_ID`` et ``CF_ACCESS_GROUP_ID``.
"""

import json
import os
import re
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel

from app import paths

EMAIL = re.compile(r"[a-z0-9][a-z0-9._%+-]{0,63}@[a-z0-9-]+(\.[a-z0-9-]+)+")
# La dernière visite n'est réécrite qu'au plus toutes les 5 minutes.
SEEN_EVERY = 300
_lock = threading.Lock()


class Person(BaseModel):
    invited: str
    removed: str | None = None
    last_seen: str | None = None


class SyncError(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _file() -> Path:
    return paths.DATA_DIR / "acces.json"


def admins() -> set[str]:
    return {a.strip().lower() for a in os.environ.get("CVB_ADMIN", "").split(",") if a.strip()}


def is_admin(email: str | None) -> bool:
    return bool(email) and email in admins()


def clean(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL.fullmatch(email) or ".." in email:
        raise ValueError("Adresse e-mail invalide.")
    return email


def load() -> dict[str, Person]:
    try:
        raw = json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {email: Person.model_validate(p) for email, p in raw.items()}


def save(people: dict[str, Person]) -> None:
    file = _file()
    file.parent.mkdir(parents=True, exist_ok=True)
    tmp = file.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({e: p.model_dump() for e, p in sorted(people.items())}, indent=1) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, file)


def allowed(email: str) -> bool:
    """Invitée et pas retirée, ou administrateur."""
    if is_admin(email):
        return True
    person = load().get(email)
    return person is not None and person.removed is None


_last_write: dict[str, float] = {}


def seen(email: str) -> None:
    """Note la visite (au plus une écriture toutes les 5 minutes par personne)."""
    now = time.monotonic()
    if now - _last_write.get(email, -SEEN_EVERY) < SEEN_EVERY:
        return
    _last_write[email] = now
    with _lock:
        people = load()
        if email in people:
            people[email].last_seen = _now()
            save(people)


def active() -> list[str]:
    """Les adresses qui doivent pouvoir se connecter : invitées non retirées et admins."""
    return sorted({e for e, p in load().items() if p.removed is None} | admins())


def invite(email: str) -> None:
    # Une personne réinvitée : sa prochaine visite est notée tout de suite.
    _last_write.pop(email, None)
    with _lock:
        people = load()
        person = people.get(email)
        if person is None:
            people[email] = Person(invited=_now())
        else:
            person.removed = None
        save(people)


def remove(email: str) -> None:
    with _lock:
        people = load()
        if email not in people:
            raise KeyError(email)
        people[email].removed = _now()
        save(people)


def forget(email: str) -> None:
    _last_write.pop(email, None)
    with _lock:
        people = load()
        people.pop(email, None)
        save(people)


# ─── Cloudflare Access ───────────────────────────────────────────────────────

API = "https://api.cloudflare.com/client/v4"


def cloudflare_ready() -> bool:
    return all(os.environ.get(k) for k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_ACCESS_GROUP_ID"))


def _group() -> tuple[str, dict[str, str]]:
    url = (
        f"{API}/accounts/{os.environ['CF_ACCOUNT_ID']}/access/groups/"
        f"{os.environ['CF_ACCESS_GROUP_ID']}"
    )
    return url, {"authorization": f"Bearer {os.environ['CF_API_TOKEN']}"}


def members() -> set[str] | None:
    """Les adresses que Cloudflare laisse recevoir un code ; None sans réglages Cloudflare."""
    if not cloudflare_ready():
        return None
    url, headers = _group()
    try:
        with httpx.Client(timeout=20, headers=headers) as client:
            answer = client.get(url)
            answer.raise_for_status()
            include = answer.json()["result"].get("include") or []
    except (httpx.HTTPError, KeyError, ValueError, AttributeError) as error:
        raise SyncError(f"Cloudflare n'a pas pu être relu ({type(error).__name__})") from None
    return {
        str(rule["email"]["email"]).strip().lower()
        for rule in include
        if isinstance(rule, dict)
        and isinstance(rule.get("email"), dict)
        and rule["email"].get("email")
    }


def sync() -> None:
    """Réécrit le groupe Access avec la liste active. Sans réglages Cloudflare : rien."""
    if not cloudflare_ready():
        return
    url, headers = _group()
    try:
        with httpx.Client(timeout=20, headers=headers) as client:
            current = client.get(url)
            current.raise_for_status()
            group: dict[str, Any] = current.json()["result"]
            body = {
                "name": group["name"],
                "include": [{"email": {"email": e}} for e in active()],
                "exclude": group.get("exclude") or [],
                "require": group.get("require") or [],
            }
            client.put(url, json=body).raise_for_status()
    except (httpx.HTTPError, KeyError, ValueError) as error:
        raise SyncError(f"Cloudflare n'a pas pris la liste ({type(error).__name__})") from None
