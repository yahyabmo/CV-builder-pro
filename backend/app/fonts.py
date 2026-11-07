"""Le registre des polices (dossier fonts/).

Chaque famille a son dossier ``fonts/<Id>/`` (identifiant en lettres seules,
qui sert aussi de nom de commande LaTeX) avec quatre fichiers
``<prefix>-Regular.ttf``, ``-Bold``, ``-Italic``, ``-BoldItalic``, une licence
et ``font.json`` :

    {"name": "Fira Sans", "category": "sans", "prefix": "FiraSans", ...}
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.paths import FONTS_DIR

STYLES = {"regular": "Regular", "bold": "Bold", "italic": "Italic", "bold_italic": "BoldItalic"}
_ID = re.compile(r"^[A-Za-z]+$")


@dataclass(frozen=True)
class FontFamily:
    id: str
    name: str
    category: str
    prefix: str
    folder: Path

    def file(self, style: str) -> Path:
        return self.folder / f"{self.prefix}-{STYLES[style]}.ttf"


class UnknownFont(ValueError):
    pass


def families() -> dict[str, FontFamily]:
    """Les familles complètes (quatre styles présents), par identifiant."""
    found: dict[str, FontFamily] = {}
    for manifest in sorted(FONTS_DIR.glob("*/font.json")):
        folder = manifest.parent
        if not _ID.match(folder.name):
            continue
        data = json.loads(manifest.read_text(encoding="utf-8"))
        family = FontFamily(
            id=folder.name,
            name=data["name"],
            category=data.get("category", "sans"),
            prefix=data["prefix"],
            folder=folder,
        )
        if all(family.file(style).is_file() for style in STYLES):
            found[family.id] = family
    return found


def get(font_id: str) -> FontFamily:
    family = families().get(font_id)
    if family is None:
        raise UnknownFont(f"police inconnue : {font_id!r}")
    return family
