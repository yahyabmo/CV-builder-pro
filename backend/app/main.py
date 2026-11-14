"""Application FastAPI de CV Builder.

En local, une seule personne et ``data/``. En mode serveur (``CVB_MODE=serveur``),
plusieurs personnes connectées par Cloudflare Access, chacune dans son dossier
(``app/access.py``).

Avec ``make start`` (ou l'image Docker), ce serveur sert aussi l'interface déjà
construite (``frontend/dist``) : tout tient sur une seule adresse. Avec
``make dev``, l'interface tourne sur Vite et appelle ce serveur.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from app import access, people, user_keys
from app.api import (
    admin,
    ai_settings,
    assets,
    ats,
    cvs,
    export,
    letters,
    library,
    project_ideas,
    rules,
    signature,
    system,
    target,
    welcome,
)
from app.paths import WEB_DIR, ensure_base, server_mode, user_root


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if server_mode():
        # Sans réglages de connexion, le serveur ne démarre pas : jamais d'appli ouverte à tous.
        access.config()
        user_keys.check_secret()
    else:
        # Au démarrage du serveur seulement : les tests n'écrivent jamais dans data/.
        ensure_base()
    yield


app = FastAPI(title="CV Builder Pro", version="1.0.0", lifespan=lifespan)

# En développement, l'interface tourne sur Vite (port 5173).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ajouté en dernier, donc passé en premier : la connexion avant tout le reste.
app.add_middleware(access.AccessMiddleware)

app.include_router(cvs.router)
app.include_router(assets.router)
app.include_router(library.router)
app.include_router(target.router)
app.include_router(ai_settings.router)
app.include_router(ats.router)
app.include_router(rules.router)
app.include_router(letters.router)
app.include_router(signature.router)
app.include_router(welcome.router)
app.include_router(project_ideas.router)
app.include_router(system.router)
app.include_router(export.router)
app.include_router(admin.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    # « app » distingue CV Builder Pro des autres applis qui répondent aussi sur /api/health
    # (le raccourci du bureau s'en sert pour savoir si c'est bien lui qui tourne).
    return {"status": "ok", "app": "cv-builder-pro"}


@app.get("/api/me")
def me() -> dict[str, str | bool | None]:
    """Qui est connecté : l'e-mail en mode serveur (et s'il administre), rien en local."""
    if not server_mode():
        return {"mode": "local", "email": None, "admin": False}
    email = user_root().name
    return {"mode": "serveur", "email": email, "admin": people.is_admin(email)}


_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


@app.api_route("/api", methods=_METHODS, include_in_schema=False)
@app.api_route("/api/{rest:path}", methods=_METHODS, include_in_schema=False)
def unknown_api(rest: str = "") -> None:
    """Une adresse /api inconnue : 404, jamais l'interface servie à la racine."""
    raise HTTPException(404, f"Adresse inconnue : /api/{rest}")


class _Web(StaticFiles):
    """L'interface construite. ``index.html`` n'est jamais repris d'un cache : il nomme les
    fichiers de la version en cours (sinon le navigateur garde l'ancienne interface après une
    mise à jour). Les fichiers de ``assets/`` changent de nom à chaque version : gardés."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if path.startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response


# L'interface construite, servie à la racine (après les routes /api).
if (WEB_DIR / "index.html").exists():
    app.mount("/", _Web(directory=WEB_DIR, html=True), name="web")
