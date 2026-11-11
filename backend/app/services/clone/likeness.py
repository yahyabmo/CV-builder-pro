"""La ressemblance entre le PDF d'origine et son clone, de 0 à 100.

Deux mesures : la place de chaque mot (``pdftotext -bbox`` donne la boîte de chaque mot,
au centième de point) et l'image de la page (couleurs et formes, à basse résolution).
"""

import math
import re
import subprocess
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

# Un mot à moins de NEAR points de sa place compte entier ; au-delà de FAR, il ne compte plus.
NEAR, FAR = 2.0, 30.0
DPI = 40
TEXT_SHARE = 0.6


@dataclass
class Word:
    text: str
    x: float
    y: float
    w: float
    h: float

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2


def _key(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", plain)


def words(pdf: Path, page: int = 1) -> list[Word]:
    out = subprocess.run(
        ["pdftotext", "-bbox", "-f", str(page), "-l", str(page), str(pdf), "-"],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    ).stdout
    root = ET.fromstring(
        re.sub(r"<!DOCTYPE[^>]*>", "", out).replace('xmlns="http://www.w3.org/1999/xhtml"', "")
    )
    found = []
    for w in root.iter("word"):
        text = (w.text or "").strip()
        if not _key(text):
            continue
        x0, y0, x1, y1 = (float(w.get(k)) for k in ("xMin", "yMin", "xMax", "yMax"))
        found.append(Word(text, x0, y0, x1 - x0, y1 - y0))
    return found


def text_score(original: list[Word], clone: list[Word]) -> tuple[float, list[tuple[Word, float]]]:
    """La part des mots d'origine retrouvés à leur place ; et l'écart de chacun (inf : absent)."""
    # Un signe seul (« | », « : ») ne compte pas : seuls les mots avec lettres ou chiffres.
    original = [w for w in original if _key(w.text)]
    pool: dict[str, list[Word]] = {}
    for w in clone:
        pool.setdefault(_key(w.text), []).append(w)
    total, gaps = 0.0, []
    for w in original:
        candidates = pool.get(_key(w.text), [])
        if not candidates:
            gaps.append((w, math.inf))
            continue
        cx, cy = w.center
        best = min(candidates, key=lambda c: math.dist(c.center, (cx, cy)))
        candidates.remove(best)
        d = math.dist(best.center, (cx, cy))
        gaps.append((w, d))
        total += 1.0 if d <= NEAR else max(0.0, 1 - (d - NEAR) / (FAR - NEAR))
    return (total / len(original) if original else 1.0), gaps


def render(pdf: Path, dpi: int = DPI) -> Image.Image:
    with tempfile.TemporaryDirectory() as tmp:
        stem = Path(tmp) / "page"
        subprocess.run(
            [
                "pdftoppm",
                "-png",
                "-r",
                str(dpi),
                "-f",
                "1",
                "-l",
                "1",
                "-singlefile",
                str(pdf),
                str(stem),
            ],
            capture_output=True,
            timeout=60,
            check=True,
        )
        return Image.open(stem.with_suffix(".png")).convert("RGB")


def image_score(original: Image.Image, clone: Image.Image) -> float:
    """1 - l'écart moyen de couleur, là où l'une ou l'autre page n'est pas blanche."""
    if clone.size != original.size:
        clone = clone.resize(original.size)
    a = original.filter(ImageFilter.GaussianBlur(1.5))
    b = clone.filter(ImageFilter.GaussianBlur(1.5))
    diff = ImageChops.difference(a, b).convert("L")
    ink = ImageChops.lighter(ImageChops.invert(a.convert("L")), ImageChops.invert(b.convert("L")))
    mask = ink.point(lambda v: 255 if v > 12 else 0)
    hist = diff.histogram(mask)
    count = sum(hist)
    if count == 0:
        return 1.0
    mean = sum(i * n for i, n in enumerate(hist)) / count
    return max(0.0, 1 - mean / 128)


@dataclass
class Likeness:
    score: int
    text: float
    image: float
    # Les mots les plus loin de leur place (texte, écart en points).
    worst: list[tuple[str, float]]


def measure(original: Path, clone: Path, original_words: list[Word] | None = None) -> Likeness:
    """``original_words`` : les mots d'un scan, lus par Tesseract (son PDF n'en a pas)."""
    t, gaps = text_score(
        original_words if original_words is not None else words(original), words(clone)
    )
    i = image_score(render(original), render(clone))
    worst = sorted(((w.text, d) for w, d in gaps if d > NEAR), key=lambda x: -x[1])[:12]
    return Likeness(
        score=round(100 * (TEXT_SHARE * t + (1 - TEXT_SHARE) * i)), text=t, image=i, worst=worst
    )
