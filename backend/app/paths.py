"""Les dossiers de l'appli.

Tout ce qui est personnel vit dans ``data/``, hors du dépôt : la version classique
du CV, les CV ciblés, la bibliothèque, les thèmes et la corbeille. ``demo/`` contient
un CV fictif, recopié dans ``data/base`` au premier lancement. ``local/`` garde
les réglages de cette machine et le journal des appels à l'IA.

``CVB_DATA`` et ``CVB_LOCAL`` remplacent ces deux dossiers : les essais de
l'interface tournent ainsi sur une copie jetable, jamais sur tes données.
"""

import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("CVB_DATA") or ROOT / "data")
LOCAL_DIR = Path(os.environ.get("CVB_LOCAL") or ROOT / "local")


# Mode serveur (CVB_MODE=serveur) : plusieurs personnes, chacune dans data/users/<e-mail>.
# La connexion (app/access.py) range l'e-mail de la requête ici ; hors requête, ou en
# mode local, c'est data/ lui-même, comme avant.
_user: ContextVar[str | None] = ContextVar("cvb_user", default=None)


def server_mode() -> bool:
    return os.environ.get("CVB_MODE", "").strip().lower() == "serveur"


def current_user() -> str | None:
    """L'e-mail de la personne connectée (mode serveur, pendant une requête), sinon None."""
    return _user.get()


def user_root() -> Path:
    user = _user.get()
    return DATA_DIR / "users" / user if user else DATA_DIR


@contextmanager
def as_user(user: str) -> Iterator[None]:
    """Le temps d'une requête, les dossiers ci-dessous sont ceux de ``user``."""
    if not user or "/" in user or user.startswith("."):
        raise ValueError(f"Utilisateur invalide : {user!r}")
    token = _user.set(user)
    try:
        yield
    finally:
        _user.reset(token)


class UserDir(os.PathLike[str]):
    """Un dossier de data/ propre à la personne de la requête en cours.

    Se comporte comme un ``Path`` (``/``, ``mkdir``, ``iterdir``…), mais le chemin est
    recalculé à chaque usage : ``CVS_DIR / slug`` tombe dans le dossier de la bonne
    personne sans changer le reste du code.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def path(self) -> Path:
        return user_root() / self._name

    def __fspath__(self) -> str:
        return str(self.path())

    def __truediv__(self, other: str | os.PathLike[str]) -> Path:
        return self.path() / other

    def __getattr__(self, attr: str) -> object:
        return getattr(self.path(), attr)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, UserDir):
            return self.path() == other.path()
        if isinstance(other, os.PathLike):
            return self.path() == Path(other)
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._name)

    def __str__(self) -> str:
        return str(self.path())

    def __repr__(self) -> str:
        return f"UserDir({self._name!r} -> {self.path()})"


BASE_DIR = UserDir("base")
CVS_DIR = UserDir("cvs")
LIBRARY_DIR = UserDir("library")
THEMES_DIR = UserDir("themes")
TRASH_DIR = UserDir("corbeille")
# Propositions de ciblage en cours de relecture.
DRAFTS_DIR = UserDir("drafts")
IMPORTS_DIR = UserDir("imports")
RULES_DIR = UserDir("rules")
DEMO_DIR = ROOT / "demo"
FONTS_DIR = ROOT / "fonts"
# Polices ajoutées par le clonage d'un CV (téléchargées de Google Fonts), communes à tous.
EXTRA_FONTS_DIR = DATA_DIR / "polices"
PROMPTS_DIR = ROOT / "prompts"
# L'interface construite (npm run build), servie par le serveur avec « make start ».
WEB_DIR = Path(os.environ.get("CVB_WEB") or ROOT / "frontend" / "dist")

BASE_FILES = ("content.json", "style.json", "meta.json", "imgcv.jpg")


def ensure_base(base: Path | UserDir = BASE_DIR, demo: Path = DEMO_DIR) -> bool:
    """Recopie le CV fictif si aucune version classique n'existe encore."""
    base = Path(base)
    if (base / "content.json").exists():
        return False
    base.mkdir(parents=True, exist_ok=True)
    for name in BASE_FILES:
        shutil.copy(demo / name, base / name)
    return True
