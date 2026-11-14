"""Une page de CV scanné : le texte lu par Tesseract et les formes de l'image.

Un scan n'a ni texte ni formes dans son PDF, seulement une image. Les mots viennent de
Tesseract (``services/ocr.py``) ; leur couleur et leur graisse se lisent dans l'encre de
l'image ; la police se reconnaît au dessin des mots (chaque police candidate écrit les mêmes
mots, comparés à l'image) ;
les fonds de couleur et les filets se cherchent dans l'image, en basse résolution.
Le résultat a la forme d'une page lue (``reading.Page``) : la suite est la même.
"""

import statistics
from collections import Counter
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

from app import fonts
from app.services import ocr
from app.services.pdfread import fonts as pdf_fonts
from app.services.pdfread.reading import Line, Page, Shape, Word

# Les polices courantes des CV : Word (par leurs équivalents aux mêmes largeurs), puis Canva
# et les modèles en ligne (téléchargées de Google Fonts au besoin).
CANDIDATES = ("Arimo", "Tinos", "Carlito")
ONLINE = ("Montserrat", "Open Sans", "Roboto", "Raleway", "Nunito", "Inter")
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


def _ground(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int]:
    """La couleur du fond autour d'un mot : un anneau de pixels juste hors de sa boîte."""
    x0, y0, x1, y1 = box
    ring = []
    for x in range(max(0, x0 - 3), min(image.width, x1 + 3), 2):
        for y in (y0 - 4, y1 + 3):
            if 0 <= y < image.height:
                ring.append(image.getpixel((x, y)))
    for y in range(max(0, y0), min(image.height, y1), 2):
        for x in (x0 - 4, x1 + 3):
            if 0 <= x < image.width:
                ring.append(image.getpixel((x, y)))
    if not ring:
        return (255, 255, 255)
    return tuple(int(statistics.median(p[i] for p in ring)) for i in range(3))  # type: ignore[return-value]


def _ink(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[str, float]:
    """La couleur de l'encre d'un mot et l'épaisseur de ses traits (pour le gras).

    Le fond se lit autour du mot (le papier, ou un bandeau de couleur) ; l'encre, ce qui s'en
    écarte nettement dans la boîte : du blanc sur un bandeau sombre aussi. L'épaisseur est la
    longueur médiane des traits d'encre sur chaque rangée de pixels, rapportée à la hauteur.
    """
    region = image.crop(box)
    width, height = region.size
    if width == 0 or height == 0:
        return "000000", 0.0
    px = region.load()
    ground = _ground(image, box)
    inked = []
    runs: list[int] = []
    for y in range(height):
        length = 0
        for x in range(width):
            p = px[x, y]
            if sum(abs(p[i] - ground[i]) for i in range(3)) > 150:
                inked.append(p)
                length += 1
            elif length:
                runs.append(length)
                length = 0
        if length:
            runs.append(length)
    if not inked:
        return "000000", 0.0
    far = sorted(inked, key=lambda p: -sum(abs(p[i] - ground[i]) for i in range(3)))
    strongest = far[: max(1, len(far) // 2)]
    color = tuple(statistics.median(p[i] for p in strongest) for i in range(3))
    # La médiane des traits : celle des fûts verticaux (les barres horizontales, plus longues,
    # sont plus rares).
    return "".join(f"{int(c):02X}" for c in color), statistics.median(runs) / height


def _glyph(words: list[tuple], n: int) -> str | None:
    """Le premier « mot » d'une ligne lu par erreur : une puce (« e », « o ») ou une icône
    (« GC » devant un téléphone). Une petite boîte presque carrée, suivie d'un grand blanc."""
    if n != 0 or len(words) < 2:
        return None
    text, x, _, w, h = words[0]
    if len(text) > 2 or w <= 0 or h <= 0 or not 0.65 <= w / h <= 1.5:
        return None
    gap = words[1][1] - (x + w)
    others = [b[1] - (a[1] + a[3]) for a, b in zip(words[1:], words[2:], strict=False)]
    usual = statistics.median(others) if others else 0.0
    rest = statistics.median(word[4] for word in words[1:])
    if usual and gap < 1.6 * usual:
        return None
    if not usual and gap < 0.5 * max(h, rest):
        return None
    # Plus petite que les lettres : une puce. Plus grande : une icône.
    return "marker" if h < 0.6 * rest else "icon"


def _ink_of(image: Image.Image, box: tuple[float, float, float, float]) -> Image.Image | None:
    """L'encre d'un mot de l'image, en gris (encre = blanc), recadrée sur ses lettres."""
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    crop = image.crop((x0 - 2, y0 - 2, x1 + 2, y1 + 2)).convert("L")
    w, h = crop.size
    if w < 8 or h < 6:
        return None
    border = [crop.getpixel((x, 0)) for x in range(w)] + [
        crop.getpixel((x, h - 1)) for x in range(w)
    ]
    ground = statistics.median(border)
    low, high = crop.getextrema()
    ink = low if ground > 128 else high
    span = abs(ground - ink)
    if span < 40:
        return None
    soft = crop.point(lambda v: max(0, min(255, int(abs(v - ground) * 255 / span))))
    letters = soft.point(lambda v: 255 if v > 90 else 0).getbbox()
    return soft.crop(letters) if letters else None


def _likeness(face: ImageFont.FreeTypeFont, text: str, seen: Image.Image) -> float:
    """Le mot écrit dans la police, ramené à la boîte de ses lettres sur l'image : 1 = pareil."""
    canvas = Image.new("L", (int(face.getlength(text)) + 60, 260), 0)
    ImageDraw.Draw(canvas).text((30, 60), text, font=face, fill=255)
    letters = canvas.point(lambda v: 255 if v > 90 else 0).getbbox()
    if not letters:
        return 0.0
    drawn = canvas.crop(letters).resize(seen.size, Image.Resampling.BILINEAR)
    return 1 - ImageStat.Stat(ImageChops.difference(drawn, seen)).mean[0] / 255


def _candidates(online: bool) -> list[str]:
    found = [pdf_fonts.resolve(name, online)[0] for name in CANDIDATES]
    for name in ONLINE:
        font_id = pdf_fonts.known(name) or (pdf_fonts.download(name) if online else None)
        if font_id and font_id not in found:
            found.append(font_id)
    return found + [f for f in fonts.families() if f not in found]


def _font(
    lines: list[ocr.Line], online: bool, image: Image.Image | None = None, k: float = 1.0
) -> str:
    """La police du texte courant : celle qui dessine le mieux les mots lus (chaque mot, écrit
    dans la police candidate et ramené à la boîte de ses lettres, est comparé à l'image ; le
    gras compte aussi). Sans image ou trop peu de mots : par les largeurs."""
    if image is not None:
        plain = [line for line in lines if len(line.text) >= 12]
        heights = Counter(round(line.h * 2) / 2 for line in plain)
        usual = heights.most_common(1)[0][0] if heights else 0
        words = [
            w
            for line in plain
            if abs(line.h - usual) <= 0.6
            for w in line.words
            if len(w[0]) >= 5 and w[0].isalpha()
        ]
        words = sorted(words, key=lambda w: -len(w[0]))[:24]
        seen = [
            (w[0], _ink_of(image, (w[1] * k, w[2] * k, (w[1] + w[3]) * k, (w[2] + w[4]) * k)))
            for w in words
        ]
        seen = [(t, s) for t, s in seen if s is not None and s.size[0] > 10 and s.size[1] > 6]
        if len(seen) >= 6:
            best, best_score = "", -1.0
            for font_id in _candidates(online):
                face, bold = _face(font_id), _face(font_id, "bold")
                if face is None:
                    continue
                score = statistics.mean(
                    max(_likeness(face, t, s), _likeness(bold, t, s) if bold else 0.0)
                    for t, s in seen
                )
                if score > best_score:
                    best, best_score = font_id, score
            if best:
                return best
    return _font_by_widths(lines, online)


def _font_by_widths(lines: list[ocr.Line], online: bool) -> str:
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
    candidates = _candidates(online)
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
    font_id = _font(scanned.lines, online, image, image.width / scanned.width)
    face = _face(font_id)
    family = fonts.get(font_id).name.replace(" ", "")
    _unglue_icons(scanned)
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
    bold_of = _weights(measured, _all_words(scanned))
    n = 0
    for line in scanned.lines:
        size = measured[n][2] if n < len(measured) else line.h * 0.75
        # La ligne de base : le bas des mots sans jambage.
        bottoms = [y + h for text, _, y, _, h in line.words if not set(text) & DESCENDERS]
        baseline = statistics.median(bottoms) if bottoms else line.y + line.h - 0.2 * size
        words = []
        for k, (text, x, y, w, h) in enumerate(line.words):
            color, stem, _ = measured[n]
            n += 1
            glyph = _glyph(line.words, k)
            if glyph == "icon":
                continue  # l'icône reste dans l'image de fond
            if glyph == "marker":
                text = "•"
            heavy = bold_of[n - 1] and any(ch.isalnum() for ch in text)
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
        # Une boîte lue qui empiète sur le mot suivant (une virgule comptée trop large) : rognée.
        for word, after in zip(words, words[1:], strict=False):
            if word.x1 > after.x0 - 0.8 and after.x0 - 0.8 > word.x0:
                word.x1 = after.x0 - 0.8
        # Sur un scan, le gras se décide par segment entier (un titre, un libellé) : mot à mot,
        # de petites lettres le trahissent.
        for segment_words in _segments_of(words, size):
            letters = sum(len(w.text) for w in segment_words) or 1
            heavy_share = sum(len(w.text) for w in segment_words if w.bold) / letters
            for w in segment_words:
                w.bold = heavy_share > 0.6
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
        background=folder / "scan" / scanned.image,
    )


def _weights(measured: list[tuple], words: list[tuple]) -> list[bool]:
    """Le gras de chaque mot, d'après l'épaisseur de ses traits.

    On compare des mots comparables : même taille, même encre (claire ou foncée). Dans un
    groupe, le gras n'existe que s'il y a deux épaisseurs nettement distinctes ; un groupe
    entier plus épais que le texte courant (des titres) est gras en bloc.
    """

    def lum(color: str) -> int:
        return sum(int(color[i : i + 2], 16) for i in (0, 2, 4)) // 3

    groups: dict[tuple, list[int]] = {}
    for n, ((color, stem, size), word) in enumerate(zip(measured, words, strict=True)):
        if stem > 0 and len(word[0]) >= 3:
            groups.setdefault((round(size), lum(color) > 128), []).append(n)
    out = [False] * len(measured)
    if not groups:
        return out
    body = max(groups.values(), key=len)
    body_stem = statistics.median(measured[n][1] for n in body)
    for members in groups.values():
        stems = sorted(measured[n][1] for n in members)
        split = None
        if len(stems) >= 4:
            # La coupure qui sépare le mieux deux épaisseurs (Otsu).
            best = 0.0
            for k in range(1, len(stems)):
                lo, hi = stems[:k], stems[k:]
                m_lo, m_hi = statistics.mean(lo), statistics.mean(hi)
                score = len(lo) * len(hi) * (m_hi - m_lo) ** 2
                if score > best and m_hi >= 1.3 * m_lo and min(len(lo), len(hi)) >= 2:
                    best, split = score, (stems[k - 1] + stems[k]) / 2
        if split is not None:
            for n in members:
                out[n] = measured[n][1] > split
        elif statistics.median(stems) >= 1.25 * body_stem:
            for n in members:
                out[n] = True
    return out


def _unglue_icons(scanned: ocr.ScannedPage) -> None:
    """Une icône lue comme une lettre collée au mot qui la suit (« d » devant une adresse) :
    le mot commence à la place des icônes des lignes voisines, et dépasse sur la colonne où
    commence leur texte. Sa première lettre est retirée."""
    icons = []
    for line in scanned.lines:
        if _glyph(line.words, 0) == "icon":
            icons.append((line.words[0][1], line.words[1][1], line.y))
    if not icons:
        return
    for line in scanned.lines:
        if not line.words or _glyph(line.words, 0) is not None:
            continue
        text, x, y, w, h = line.words[0]
        near = [i for i in icons if abs(i[0] - x) < 3 and abs(i[2] - line.y) < 80]
        if not near or len(text) < 6:
            continue
        start = statistics.median(i[1] for i in near)
        if x + w <= start:
            continue
        line.words[0] = (text[1:], start, y, x + w - start, h)
        line.text = " ".join(word[0] for word in line.words)
        line.x = min(word[1] for word in line.words)
        line.w = max(word[1] + word[3] for word in line.words) - line.x


def _segments_of(words: list[Word], size: float) -> list[list[Word]]:
    out: list[list[Word]] = []
    for w in words:
        if out and w.x0 - out[-1][-1].x1 <= 1.4 * size:
            out[-1].append(w)
        else:
            out.append([w])
    return out


def _all_words(scanned: ocr.ScannedPage) -> list[tuple]:
    return [w for line in scanned.lines for w in line.words]


def pages(scanned: list[ocr.ScannedPage], folder: Path, online: bool = True) -> list[Page]:
    return [page(s, folder, n, online) for n, s in enumerate(scanned, 1)]
