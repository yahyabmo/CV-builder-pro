"""Les thèmes : des ensembles de réglages de style nommés (themes/<slug>.json)."""

import json
import re
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.models.meta import now
from app.models.style import CVStyle
from app.paths import THEMES_DIR
from app.text import slugify

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")


class Theme(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    created_at: datetime = Field(default_factory=now)
    style: CVStyle


class UnknownTheme(LookupError):
    pass


def _path(slug: str) -> Path:
    if not _SLUG.match(slug):
        raise UnknownTheme(slug)
    return THEMES_DIR / f"{slug}.json"


def list_all() -> list[tuple[str, Theme]]:
    if not THEMES_DIR.is_dir():
        return []
    found = [
        (file, Theme.model_validate_json(file.read_text(encoding="utf-8")))
        for file in THEMES_DIR.glob("*.json")
        if _SLUG.match(file.stem)
    ]
    # Le plus récent d'abord ; deux thèmes de la même seconde, d'après l'écriture du fichier.
    found.sort(key=lambda item: (item[1].created_at, item[0].stat().st_mtime_ns), reverse=True)
    return [(file.stem, theme) for file, theme in found]


def create(name: str, style: CVStyle) -> tuple[str, Theme]:
    THEMES_DIR.mkdir(parents=True, exist_ok=True)
    base = slugify(name, "theme")
    slug, n = base, 2
    while _path(slug).exists():
        slug, n = f"{base}-{n}", n + 1
    theme = Theme(name=name.strip(), style=style)
    _path(slug).write_text(
        json.dumps(theme.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return slug, theme


def delete(slug: str) -> None:
    path = _path(slug)
    if not path.exists():
        raise UnknownTheme(slug)
    path.unlink()
