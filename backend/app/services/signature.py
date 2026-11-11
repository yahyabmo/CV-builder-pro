"""L'image de signature, une par personne, pour le bas de ses lettres.

Une signature photographiée sur papier blanc perd son fond (le papier devient
transparent, les bords du trait restent doux), puis l'image est recadrée au
trait. Un PNG déjà transparent garde sa transparence.
"""

import io
import json
import os
from pathlib import Path
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError

from app import paths

FILE = "signature.png"
PREFS = "signature.json"
MAX_BYTES = 5 * 1024 * 1024
MAX_WIDTH, MAX_HEIGHT = 1200, 600
Size = Literal["small", "medium", "large"]
# Hauteur de l'image dans la lettre, en centimètres.
HEIGHTS: dict[str, float] = {"small": 1.2, "medium": 1.6, "large": 2.0}


class BadImage(ValueError):
    pass


def path() -> Path:
    return paths.user_root() / FILE


def exists() -> bool:
    return path().is_file()


def size() -> Size:
    try:
        found = json.loads((paths.user_root() / PREFS).read_text(encoding="utf-8")).get("size")
    except (OSError, ValueError, AttributeError):
        return "medium"
    return found if found in HEIGHTS else "medium"


def set_size(value: Size) -> None:
    file = paths.user_root() / PREFS
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps({"size": value}) + "\n", encoding="utf-8")


def _percentile(histogram: list[int], share: float) -> int:
    """La valeur de gris sous laquelle se trouve ``share`` des pixels."""
    total = sum(histogram)
    seen = 0
    for value, count in enumerate(histogram):
        seen += count
        if seen >= share * total:
            return value
    return 255


def _clear_paper(image: Image.Image) -> Image.Image:
    """Le papier (le gris le plus courant, clair) devient transparent ; le trait reste."""
    gray = image.convert("L")
    paper = _percentile(gray.histogram(), 0.6)
    # Au-dessus de « clear » : papier, transparent. Sous « ink » : trait, opaque. Entre : doux.
    clear = max(paper - 18, 40)
    ink = max(clear - 70, 0)

    def alpha(value: int) -> int:
        if value >= clear:
            return 0
        if value <= ink:
            return 255
        return round(255 * (clear - value) / (clear - ink))

    image.putalpha(gray.point(alpha))
    return image


def process(data: bytes) -> Image.Image:
    if len(data) > MAX_BYTES:
        raise BadImage("Image trop lourde (5 Mo au plus).")
    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
        image.load()
    except (UnidentifiedImageError, OSError):
        raise BadImage("Ce fichier n'est pas une image lisible (PNG, JPEG ou WebP).") from None
    image = image.convert("RGBA")
    # Sans transparence (photo, scan) : on retire le papier.
    if image.getchannel("A").getextrema()[0] >= 250:
        image = _clear_paper(image)
    box = image.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
    if box is None:
        raise BadImage("Aucun trait trouvé : l'image est vide ou toute blanche.")
    left, top, right, bottom = box
    margin = max(2, round(0.02 * max(right - left, bottom - top)))
    image = image.crop(
        (
            max(left - margin, 0),
            max(top - margin, 0),
            min(right + margin, image.width),
            min(bottom + margin, image.height),
        )
    )
    image.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.Resampling.LANCZOS)
    return image


def store(data: bytes) -> None:
    image = process(data)
    file = path()
    file.parent.mkdir(parents=True, exist_ok=True)
    tmp = file.with_suffix(".tmp")
    image.save(tmp, "PNG", optimize=True)
    os.replace(tmp, file)


def delete() -> None:
    path().unlink(missing_ok=True)


def version() -> int | None:
    file = path()
    return file.stat().st_mtime_ns if file.is_file() else None
