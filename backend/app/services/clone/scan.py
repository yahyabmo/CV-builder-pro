"""Une page de CV scanné, pour le clone : le texte lu par Tesseract et les formes de l'image.

Un scan n'a ni texte ni formes dans son PDF, seulement une image. Les mots viennent de
Tesseract (``services/ocr.py``) ; leur couleur et leur graisse se lisent dans l'encre de
l'image ; la police se devine aux largeurs (Arial, Times et Calibri n'ont pas les mêmes) ;
les fonds de couleur et les filets se cherchent dans l'image, en basse résolution.
Le résultat a la forme d'une page lue (``reading.Page``) : la suite est la même.
"""

import statistics
from collections import Counter
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageFont

from app import fonts
from app.services import ocr
from app.services.clone import fonts as clone_fonts
from app.services.clone.likeness import Word as Seen
from app.services.clone.reading import Line, Page, Shape, Word

# Les polices courantes des CV faits sous Word, par leurs équivalents aux mêmes largeurs.
CANDIDATES = ("Arimo", "Tinos", "Carlito")
GRID = 4  # 300 ppp / 4 = 75 ppp pour chercher les formes
DESCENDERS = set("gjpqyQ,;()[]")


@lru_cache(maxsize=64)
def _face(font_id: str, style: str = "regular") -> ImageFont.FreeTypeFont | None:
    try:
        return ImageFont.truetype(str(fonts.get(font_id).file(style)), 100)
    except (OSError, fonts.UnknownFont):
        return None


def _pixels(image: Image.Image):
    """Les pixels, ligne par ligne (Pillow renomme getdata en get_flattened_data)."""
    getter = getattr(image, "get_flattened_data", None) or image.getdata
    return getter()


def _ink(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[str, float]:
    """La couleur de l'encre d'un mot et l'épaisseur de ses traits (pour le gras).

    Le fond est la couleur la plus fréquente du mot (le papier, ou un bandeau de couleur) ;
    l'encre, ce qui s'en écarte nettement : du blanc sur un bandeau sombre aussi. L'épaisseur
    est la longueur moyenne des traits d'encre sur chaque rangée de pixels, rapportée à la
    hauteur du mot.
    """
    region = image.crop(box)
    width, height = region.size
    if width == 0 or height == 0:
        return "000000", 0.0
    px = region.load()
    ground = Counter(
        (px[x, y][0] // 16, px[x, y][1] // 16, px[x, y][2] // 16)
        for x in range(width)
        for y in range(height)
    ).most_common(1)[0][0]
    ground = tuple(c * 16 + 8 for c in ground)
    inked = []
    runs = 0
    for y in range(height):
        inside = False
        for x in range(width):
            p = px[x, y]
            on = sum(abs(p[i] - ground[i]) for i in range(3)) > 150
            if on:
                inked.append(p)
                if not inside:
                    runs += 1
            inside = on
    if not inked:
        return "000000", 0.0
    far = sorted(inked, key=lambda p: -sum(abs(p[i] - ground[i]) for i in range(3)))
    strongest = far[: max(1, len(far) // 2)]
    color = tuple(statistics.median(p[i] for p in strongest) for i in range(3))
    return "".join(f"{int(c):02X}" for c in color), len(inked) / runs / height


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
        face, bold = _face(font_id), _face(font_id, "bold")
        if face is None or len(words) < 8:
            continue
        pairs = [
            (
                w[3] / (face.getlength(w[0]) / 100),
                w[3] / (bold.getlength(w[0]) / 100) if bold else 0,
            )
            for w in words
            if face.getlength(w[0]) > 0
        ]
        middle = statistics.median(r for r, _ in pairs)
        # Un mot en gras est plus large : il compte avec le gras de la police, s'il colle mieux.
        spread = statistics.median(min(abs(r - middle), abs(b - middle)) / middle for r, b in pairs)
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
    return shapes + [
        s for s in _merge_lines(_rules(image, paper, scale)) if _clear(image, s, scale)
    ]


def _clear(image: Image.Image, line: Shape, scale: float) -> bool:
    """Un filet a un fond uni juste au-dessus et juste en dessous ; une ligne de texte, non."""
    x0, x1 = int(line.box[0] / scale), int(line.box[2] / scale)
    for y in (int(line.box[1] / scale) - 4, int(line.box[3] / scale) + 4):
        if not 0 <= y < image.height:
            continue
        row = [image.getpixel((x, y)) for x in range(max(0, x0), min(image.width, x1), 3)]
        if not row:
            continue
        middle = tuple(statistics.median(p[i] for p in row) for i in range(3))
        same = sum(1 for p in row if sum(abs(p[i] - middle[i]) for i in range(3)) < 60)
        if same < 0.9 * len(row):
            return False
    return True


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
            while (
                x < w
                and max(abs(rows[x, y][i] - p[i]) for i in range(3)) < 40
                and max(abs(rows[x, y][i] - paper[i]) for i in range(3)) >= 28
            ):
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


def page(scanned: ocr.ScannedPage, folder: Path, number: int = 1, online: bool = True) -> Page:
    """La page lue d'un scan (``ocr.load``), avec ses formes tirées de l'image."""
    with Image.open(folder / "scan" / scanned.image) as opened:
        image = opened.convert("RGB")
    scale = 72 / ocr.DPI
    paper = Counter(_pixels(image.resize((60, 85)))).most_common(1)[0][0]
    font_id = _font(scanned.lines, online)
    face = _face(font_id)
    family = fonts.get(font_id).name.replace(" ", "")
    lines: list[Line] = []
    measured = []
    for line in scanned.lines:
        # La taille : d'après la largeur des mots longs, avec la police devinée.
        sizes = []
        for text, _, _, w, _ in line.words:
            natural = face.getlength(text) / 100 if face else 0
            if len(text) >= 3 and natural > 0:
                sizes.append(w / natural)
        size = statistics.median(sizes) if sizes else line.h * 0.75
        for _text, x, y, w, h in line.words:
            box = (
                int(x / scale),
                int(y / scale),
                int((x + w) / scale) + 1,
                int((y + h) / scale) + 1,
            )
            color, stem = _ink(image, box)
            measured.append((color, stem, size))
    # Le gras : des traits nettement plus épais que ceux du texte courant.
    stems = [stem for _, stem, _ in measured if stem > 0]
    usual = statistics.median(stems) if stems else 0.0
    n = 0
    for line in scanned.lines:
        size = measured[n][2] if n < len(measured) else line.h * 0.75
        # La ligne de base : le bas des mots sans jambage.
        bottoms = [y + h for text, _, y, _, h in line.words if not set(text) & DESCENDERS]
        baseline = statistics.median(bottoms) if bottoms else line.y + line.h - 0.2 * size
        words = []
        for text, x, y, w, h in line.words:
            color, stem, _ = measured[n]
            n += 1
            heavy = usual > 0 and any(ch.isalnum() for ch in text) and stem > 1.15 * usual
            words.append(
                Word(
                    text=text,
                    x0=x,
                    x1=x + w,
                    top=y,
                    bottom=y + h,
                    baseline=baseline,
                    font=family,
                    raw_font="Scan",
                    size=round(size, 2),
                    color=color,
                    bold=heavy,
                    italic=False,
                )
            )
        # Un grand blanc (une date alignée à droite, une autre colonne) ouvre un segment.
        segment: list[Word] = []
        for w in words:
            if segment and w.x0 - segment[-1].x1 > 1.4 * size:
                lines.append(Line(segment))
                segment = []
            segment.append(w)
        if segment:
            lines.append(Line(segment))
    return Page(
        number=number,
        width=scanned.width,
        height=scanned.height,
        lines=sorted(lines, key=lambda line: (round(line.baseline, 1), line.x0)),
        shapes=_shapes(image, paper, scale),
    )


def pages(scanned: list[ocr.ScannedPage], folder: Path, online: bool = True) -> list[Page]:
    return [page(s, folder, n, online) for n, s in enumerate(scanned, 1)]


def words(scanned: ocr.ScannedPage) -> list[Seen]:
    """Les mots lus, pour mesurer la ressemblance du clone avec le scan."""
    return [Seen(text, x, y, w, h) for line in scanned.lines for text, x, y, w, h in line.words]
