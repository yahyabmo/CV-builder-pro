"""Une page de CV scanné, pour le clone : le texte lu par Tesseract et les formes de l'image.

Un scan n'a ni texte ni formes dans son PDF, seulement une image. Les lignes viennent de
Tesseract (``services/ocr.py``) ; leur couleur et leur graisse se lisent dans l'encre de
l'image ; la police se devine aux largeurs (Arial, Times et Calibri n'ont pas les mêmes) ;
les fonds de couleur et les filets se cherchent dans l'image, en basse résolution.
"""

import statistics
from collections import Counter
from pathlib import Path

from PIL import Image

from app import fonts
from app.services import ocr
from app.services.clone import fonts as clone_fonts
from app.services.clone.layout import _face
from app.services.clone.likeness import Word
from app.services.clone.page import Page, Run, Shape

# Les polices courantes des CV faits sous Word, par leurs équivalents aux mêmes largeurs.
CANDIDATES = ("Arimo", "Tinos", "Carlito")
GRID = 4  # 300 ppp / 4 = 75 ppp pour chercher les formes


def _pixels(image: Image.Image):
    """Les pixels, ligne par ligne (Pillow renomme getdata en get_flattened_data)."""
    getter = getattr(image, "get_flattened_data", None) or image.getdata
    return getter()


def _ink(
    image: Image.Image, box: tuple[int, int, int, int], paper: tuple[int, int, int]
) -> tuple[str, float]:
    """La couleur de l'encre d'une ligne et sa part de pixels encrés (pour le gras)."""
    region = image.crop(box)
    pixels = list(_pixels(region))
    if not pixels:
        return "000000", 0.0
    lum = sum(paper) / 3
    inked = [p for p in pixels if (sum(p[:3]) / 3) < lum - 60]
    if not inked:
        return "000000", 0.0
    darkest = sorted(inked, key=lambda p: sum(p[:3]))[: max(1, len(inked) // 2)]
    color = tuple(statistics.median(p[i] for p in darkest) for i in range(3))
    return "".join(f"{int(c):02X}" for c in color), len(inked) / len(pixels)


def _font(lines: list[ocr.Line], online: bool) -> str:
    """La police dont les largeurs collent le mieux aux mots lus.

    Avec la bonne police, chaque mot du texte courant donne la même taille (largeur lue /
    largeur à 1 pt) ; avec une autre, les lettres n'ont pas les mêmes largeurs relatives
    et la taille varie d'un mot à l'autre. On garde la police où elle varie le moins.
    """
    plain = [line for line in lines if len(line.text) >= 12 and not line.text.isupper()]
    heights = Counter(round(line.h * 2) / 2 for line in plain)
    usual = heights.most_common(1)[0][0] if heights else 0
    words = [
        w
        for line in plain
        if abs(line.h - usual) <= 0.6
        for w in line.words
        if len(w[0]) >= 4 and w[0].isalpha()
    ][:200]
    candidates = [clone_fonts.resolve(name, online)[0] for name in CANDIDATES]
    candidates += [f for f in fonts.families() if f not in candidates]
    best, best_spread = candidates[0], float("inf")
    for font_id in candidates:
        face = _face(font_id, "regular")
        if face is None or len(words) < 8:
            continue
        sizes = [w[3] / (face.getlength(w[0]) / 100) for w in words if face.getlength(w[0]) > 0]
        middle = statistics.median(sizes)
        spread = statistics.median(abs(x - middle) / middle for x in sizes)
        if spread < best_spread - 1e-4:
            best, best_spread = font_id, spread
    return best


def _shapes(image: Image.Image, paper: tuple[int, int, int], scale: float) -> list[Shape]:
    """Les fonds de couleur (grands rectangles pleins) et les filets (traits longs et fins)."""
    small = image.resize((image.width // GRID, image.height // GRID), Image.Resampling.BOX)
    w, h = small.size
    data = small.load()

    def quant(p: tuple[int, ...]) -> tuple[int, int, int]:
        return (p[0] // 24, p[1] // 24, p[2] // 24)

    background = quant(paper)
    counts = Counter(quant(data[x, y]) for x in range(0, w, 2) for y in range(0, h, 2))
    shapes: list[Shape] = []
    seen: set[tuple[int, int]] = set()
    for color, _ in counts.most_common(10):
        if color == background:
            continue
        for y0 in range(h):
            for x0 in range(w):
                if (x0, y0) in seen or quant(data[x0, y0]) != color:
                    continue
                # Une zone d'une même couleur, de proche en proche.
                stack, area, xs, ys, total = [(x0, y0)], 0, [x0, x0], [y0, y0], [0, 0, 0]
                seen.add((x0, y0))
                while stack:
                    x, y = stack.pop()
                    area += 1
                    p = data[x, y]
                    total = [total[i] + p[i] for i in range(3)]
                    xs = [min(xs[0], x), max(xs[1], x)]
                    ys = [min(ys[0], y), max(ys[1], y)]
                    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                        if (
                            0 <= nx < w
                            and 0 <= ny < h
                            and (nx, ny) not in seen
                            and quant(data[nx, ny]) == color
                        ):
                            seen.add((nx, ny))
                            stack.append((nx, ny))
                bw, bh = xs[1] - xs[0] + 1, ys[1] - ys[0] + 1
                fill = "".join(f"{round(c / area):02X}" for c in total)
                box = (
                    xs[0] * GRID * scale,
                    ys[0] * GRID * scale,
                    (xs[1] + 1) * GRID * scale,
                    (ys[1] + 1) * GRID * scale,
                )
                if area >= 0.004 * w * h and area / (bw * bh) >= 0.6:
                    shapes.append(Shape(box=box, fill=fill, stroke=None, width=0.0, kind="rect"))
    return shapes + _merge_lines(_rules(image, paper, scale))


def _rules(image: Image.Image, paper: tuple[int, int, int], scale: float) -> list[Shape]:
    """Les filets : sur chaque rangée de pixels (pleine hauteur, largeur réduite), une longue
    suite de pixels d'une même couleur qui n'est pas celle du papier."""
    narrow = image.resize((image.width // GRID, image.height), Image.Resampling.BOX)
    w, h = narrow.size
    rows = narrow.load()
    found: list[Shape] = []
    for y in range(h):
        x = 0
        while x < w:
            p = rows[x, y]
            if max(abs(p[i] - paper[i]) for i in range(3)) < 28:
                x += 1
                continue
            start, total = x, [0, 0, 0]
            while x < w and max(abs(rows[x, y][i] - p[i]) for i in range(3)) < 40:
                q = rows[x, y]
                total = [total[i] + q[i] for i in range(3)]
                x += 1
            if x - start >= 0.12 * w:
                n = x - start
                color = "".join(f"{round(c / n):02X}" for c in total)
                box = (start * GRID * scale, y * scale, x * GRID * scale, (y + 1) * scale)
                found.append(Shape(box=box, fill=None, stroke=color, width=scale, kind="line"))
    return found


def _merge_lines(shapes: list[Shape]) -> list[Shape]:
    """Un filet scanné donne plusieurs traits gris superposés (anticrénelage) : un seul, le
    plus foncé, sur toute leur épaisseur."""
    lines = sorted(
        (s for s in shapes if s.kind == "line"), key=lambda s: (round(s.box[0]), s.box[1])
    )
    merged: list[Shape] = []
    for line in lines:
        last = merged[-1] if merged else None
        if (
            last is not None
            and abs(last.box[0] - line.box[0]) <= 3
            and abs(last.box[2] - line.box[2]) <= 3
            and line.box[1] - last.box[3] <= 2
        ):
            darker = min(
                (last, line),
                key=lambda s: sum(int((s.stroke or "FFFFFF")[i : i + 2], 16) for i in (0, 2, 4)),
            )
            box = (
                min(last.box[0], line.box[0]),
                last.box[1],
                max(last.box[2], line.box[2]),
                max(last.box[3], line.box[3]),
            )
            merged[-1] = Shape(
                box=box, fill=None, stroke=darker.stroke, width=box[3] - box[1], kind="line"
            )
        else:
            merged.append(line)
    return [s for s in shapes if s.kind != "line"] + merged


def page(scanned: ocr.ScannedPage, folder: Path, online: bool = True) -> Page:
    """La page du clone tirée d'un scan lu (``ocr.load``) et de son image."""
    with Image.open(folder / "scan" / scanned.image) as opened:
        image = opened.convert("RGB")
    scale = 72 / ocr.DPI
    paper = Counter(_pixels(image.resize((60, 85)))).most_common(1)[0][0]
    font_id = _font(scanned.lines, online)
    face = _face(font_id, "regular")
    inks = []
    for line in scanned.lines:
        box = (
            int(line.x / scale),
            int(line.y / scale),
            int((line.x + line.w) / scale) + 1,
            int((line.y + line.h) / scale) + 1,
        )
        inks.append(_ink(image, box, paper))
    coverage = statistics.median([c for _, c in inks]) if inks else 0.0
    # La taille : d'après la largeur, avec la police devinée ; sinon d'après la hauteur.
    ratios = []
    for line in scanned.lines:
        natural = face.getlength(line.text) / 100 if face else 0
        if len(line.text) >= 12 and natural > 0:
            ratios.append((line.w / natural) / max(line.h, 1))
    ratio = statistics.median(ratios) if ratios else 0.75
    runs = []
    for line, (color, ink) in zip(scanned.lines, inks, strict=True):
        natural = face.getlength(line.text) / 100 if face else 0
        size = line.w / natural if len(line.text) >= 6 and natural > 0 else line.h * ratio
        runs.append(
            Run(
                text=line.text,
                x=line.x,
                y=line.y,
                w=line.w,
                h=line.h,
                font=font_id,
                raw_font="Scan",
                size=round(size, 2),
                color=color,
                bold=coverage > 0 and ink > coverage * 1.35,
                italic=False,
            )
        )
    return Page(
        width=scanned.width, height=scanned.height, runs=runs, shapes=_shapes(image, paper, scale)
    )


def words(scanned: ocr.ScannedPage) -> list[Word]:
    """Les mots lus, pour mesurer la ressemblance du clone avec le scan."""
    return [Word(text, x, y, w, h) for line in scanned.lines for text, x, y, w, h in line.words]
