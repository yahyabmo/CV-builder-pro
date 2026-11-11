"""La connexion en mode serveur, par Cloudflare Access.

En ligne, personne n'atteint l'appli sans passer par Cloudflare Access : la personne
donne son e-mail, reçoit un code, et Cloudflare ne laisse entrer que les adresses
invitées. Il ajoute alors à chaque requête un jeton signé (en-tête
``Cf-Access-Jwt-Assertion``) qui porte l'e-mail.

Ici, chaque requête ``/api`` vérifie ce jeton (signature, audience, émetteur, date)
avant de servir quoi que ce soit, puis range les données dans le dossier de cette
adresse (``data/users/<e-mail>``). Sans jeton valide : 401, rien n'est lu ni écrit.

Réglages, obligatoires en mode serveur :

- ``CF_ACCESS_TEAM`` : le domaine d'équipe, par exemple ``cv-pro.cloudflareaccess.com`` ;
- ``CF_ACCESS_AUD`` : l'« Application Audience (AUD) Tag » de l'application Access.
"""

import asyncio
import json
import logging
import os
import re
from collections.abc import Awaitable, Callable, MutableMapping
from functools import lru_cache
from typing import Any

import jwt

from app import people
from app.paths import as_user, ensure_base, server_mode

log = logging.getLogger(__name__)

HEADER = b"cf-access-jwt-assertion"
COOKIE = "CF_Authorization"
# Une adresse ordinaire, en minuscules : elle sert aussi de nom de dossier.
EMAIL = re.compile(r"[a-z0-9][a-z0-9._%+-]{0,63}@[a-z0-9-]+(\.[a-z0-9-]+)+")
# Les adresses /api ouvertes sans connexion.
PUBLIC = {"/api/health"}

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class AccessError(Exception):
    pass


def config() -> tuple[str, str]:
    """L'adresse de l'équipe Access et l'audience attendue, ou une erreur claire."""
    team = os.environ.get("CF_ACCESS_TEAM", "").strip().removeprefix("https://").rstrip("/")
    aud = os.environ.get("CF_ACCESS_AUD", "").strip()
    if not team or not aud:
        raise AccessError("Mode serveur : CF_ACCESS_TEAM et CF_ACCESS_AUD sont obligatoires.")
    return f"https://{team}", aud


@lru_cache(maxsize=4)
def _jwks(issuer: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{issuer}/cdn-cgi/access/certs", cache_keys=True, lifespan=300)


def signing_key(token: str, issuer: str) -> Any:
    """La clé publique de Cloudflare qui a signé ce jeton (remplacée dans les tests)."""
    return _jwks(issuer).get_signing_key_from_jwt(token).key


def email_from(token: str) -> str:
    """Vérifie le jeton d'Access et renvoie l'e-mail qu'il porte."""
    issuer, aud = config()
    try:
        claims = jwt.decode(
            token,
            signing_key(token, issuer),
            algorithms=["RS256"],
            audience=aud,
            issuer=issuer,
            options={"require": ["exp", "iat", "aud", "iss", "email"]},
        )
    except (jwt.PyJWTError, ValueError) as error:
        raise AccessError(f"Jeton refusé : {type(error).__name__}") from error
    email = str(claims.get("email", "")).strip().lower()
    if not EMAIL.fullmatch(email) or ".." in email:
        raise AccessError("Jeton sans e-mail valable")
    return email


def _token(scope: Scope) -> str | None:
    cookie = ""
    for name, value in scope.get("headers", []):
        if name == HEADER:
            return value.decode("latin-1")
        if name == b"cookie":
            cookie = value.decode("latin-1")
    for part in cookie.split(";"):
        key, _, value = part.strip().partition("=")
        if key == COOKIE and value:
            return value
    return None


async def _refuse(send: Send, message: str, status: int = 401, **extra: str) -> None:
    body = json.dumps({"detail": message, **extra}, ensure_ascii=False).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store")],
        }
    )
    await send({"type": "http.response.body", "body": body})


class AccessMiddleware:
    """En mode serveur, chaque requête /api passe par la connexion ci-dessus."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if (
            scope["type"] != "http"
            or not server_mode()
            or not (path == "/api" or path.startswith("/api/"))
            or path in PUBLIC
        ):
            await self.app(scope, receive, send)
            return
        token = _token(scope)
        if not token:
            await _refuse(send, "Connexion requise.")
            return
        try:
            email = await asyncio.to_thread(email_from, token)
        except AccessError as error:
            log.warning("connexion refusée : %s", error)
            await _refuse(send, "Connexion refusée. Reconnecte-toi.")
            return
        # Retirée par l'administrateur : coupée tout de suite, même si Cloudflare la laisse
        # encore passer jusqu'à la fin de sa session.
        if not people.allowed(email):
            # « paused » : l'interface montre l'écran « Ton accès est en pause ».
            await _refuse(
                send, "Ton accès a été retiré. Demande à Yahya.", 403, code="paused", email=email
            )
            return
        people.seen(email)
        with as_user(email):
            # Première visite : le CV fictif, comme au premier lancement de l'appli.
            ensure_base()
            await self.app(scope, receive, send)
