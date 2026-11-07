"""Photo importée : redressée, recadrée en carré au centre, réduite, en JPEG.

L'interface envoie déjà un carré recadré par l'utilisateur ; le recadrage
centré ne sert que si une image d'une autre forme arrive quand même.
"""

import io
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_SIDE = 900
MAX_BYTES = 15 * 1024 * 1024
PHOTO = "photo.jpg"


class BadImage(ValueError):
    pass


def store(folder: Path, data: bytes) -> str:
    """Enregistre la photo dans le dossier du CV ; rend le nom du fichier."""
    if len(data) > MAX_BYTES:
        raise BadImage("Image trop lourde (15 Mo au plus).")
    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise BadImage("Ce fichier n'est pas une image lisible (JPEG, PNG ou WebP).") from None
    side = min(image.size)
    left, top = (image.width - side) // 2, (image.height - side) // 2
    image = image.crop((left, top, left + side, top + side))
    if side > MAX_SIDE:
        image = image.resize((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    image.save(folder / PHOTO, "JPEG", quality=90, optimize=True)
    return PHOTO
