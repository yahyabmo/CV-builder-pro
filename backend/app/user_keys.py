"""En ligne : le choix d'IA et les clés d'API de chaque personne, dans son dossier.

Chacun choisit entre le relais de Yahya (par défaut), sa propre clé Gemini ou sa propre
clé Mistral. Les clés sont chiffrées (Fernet) avec ``CVB_SECRET``, le secret du serveur :
le fichier ``cles.json`` seul ne révèle rien, et aucune page ne les renvoie, pas même
l'administration. Elles ne quittent le serveur que vers leur fournisseur.
"""

import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app import paths

KEYS_FILE = "cles.json"
PREFS_FILE = "reglages-ia.json"
# Ce que chacun peut choisir en ligne, le relais en premier.
ONLINE_PROVIDERS = ("relais", "gemini", "mistral")
OWN_KEYS = ("gemini", "mistral")


class SecretMissing(RuntimeError):
    pass


def check_secret() -> None:
    """Au démarrage en mode serveur : sans secret, pas de clé chiffrable."""
    if len(os.environ.get("CVB_SECRET", "").strip()) < 32:
        raise SecretMissing("Mode serveur : CVB_SECRET (au moins 32 caractères) est obligatoire.")


def _fernet() -> Fernet:
    check_secret()
    digest = hashlib.sha256(os.environ["CVB_SECRET"].strip().encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _path(name: str) -> Path:
    return paths.user_root() / name


def _read(name: str) -> dict[str, str]:
    try:
        data = json.loads(_path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, str)} if isinstance(data, dict) else {}


def _write(name: str, data: dict[str, str]) -> None:
    file = _path(name)
    file.parent.mkdir(parents=True, exist_ok=True)
    tmp = file.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1)
    os.replace(tmp, file)


def get_key(provider: str) -> str | None:
    token = _read(KEYS_FILE).get(provider)
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        # Secret du serveur changé : la clé est illisible, la personne la recolle.
        return None


def set_key(provider: str, key: str) -> None:
    if provider not in OWN_KEYS:
        raise ValueError(provider)
    data = _read(KEYS_FILE)
    data[provider] = _fernet().encrypt(key.encode()).decode()
    _write(KEYS_FILE, data)


def delete_key(provider: str) -> None:
    data = _read(KEYS_FILE)
    if data.pop(provider, None) is not None:
        _write(KEYS_FILE, data)


def provider() -> str:
    chosen = _read(PREFS_FILE).get("provider", "relais")
    return chosen if chosen in ONLINE_PROVIDERS else "relais"


def set_provider(chosen: str) -> None:
    if chosen not in ONLINE_PROVIDERS:
        raise ValueError(chosen)
    data = _read(PREFS_FILE)
    data["provider"] = chosen
    _write(PREFS_FILE, data)
