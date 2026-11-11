"""Ce que contient une page de PDF : morceaux de texte stylés, formes dessinées, images.

``pdftohtml -xml`` donne chaque morceau de texte (police, taille, couleur, place) ;
``pdftocairo -svg`` donne les formes (fonds, filets, pastilles) et les images avec leur
découpe. Tout est en points, depuis le coin haut gauche de la page.
"""

import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

SVG = "{http://www.w3.org/2000/svg}"
ZOOM = 3
XLINK = "{http://www.w3.org/1999/xlink}"


@dataclass
class Run:
    """Un morceau de texte d'une ligne, d'un seul style."""

    text: str
    x: float
    y: float
    w: float
    h: float
    font: str  # famille sans préfixe de sous-ensemble ni graisse : « Poppins »
    raw_font: str
    size: float
    color: str  # RRGGBB
    bold: bool
    italic: bool
    # Petites capitales : la taille des petites lettres (0 : pas de petites capitales).
    small: float = 0.0

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h


@dataclass
class Shape:
    """Une forme pleine ou un trait. ``box`` = (x0, y0, x1, y1)."""

    box: tuple[float, float, float, float]
    fill: str | None
    stroke: str | None
    width: float
    # « rect », « line », « ellipse », « path » (forme libre).
    kind: str
    radius: float = 0.0

    @property
    def w(self) -> float:
        return self.box[2] - self.box[0]

    @property
    def h(self) -> float:
        return self.box[3] - self.box[1]


@dataclass
class Picture:
    box: tuple[float, float, float, float]
    # « circle », « rounded », « square ».
    shape: str


@dataclass
class Page:
    width: float
    height: float
    runs: list[Run] = field(default_factory=list)
    shapes: list[Shape] = field(default_factory=list)
    pictures: list[Picture] = field(default_factory=list)


_SUBSET = re.compile(r"^[A-Z]{6}\+")
_WEIGHT = re.compile(
    r"[-,_ ]?(Bold|Black|Heavy|Semi ?Bold|Demi ?Bold|Medium|Regular|Book|Light|Thin|Italic|Oblique"
    r"|BoldItalic|BoldOblique|MT|PS|PSMT)+$",
    re.I,
)


def family_name(raw: str) -> str:
    """« ABCDEF+Poppins-BoldItalic » → « Poppins » ; « ArialMT » → « Arial »."""
    name = _SUBSET.sub("", raw)
    name = name.split("-")[0].split(",")[0]
    previous = None
    while previous != name:
        previous = name
        name = _WEIGHT.sub("", name)
    return name or raw


def _hex(value: str | None) -> str | None:
    if not value or value == "none":
        return None
    if value.startswith("#"):
        return value[1:].upper()
    m = re.match(r"rgb\(\s*([\d.]+)%,\s*([\d.]+)%,\s*([\d.]+)%\s*\)", value)
    if not m:
        return None
    return "".join(f"{round(float(g) * 2.55):02X}" for g in m.groups())


def read_runs(pdf: Path, page: int = 1) -> tuple[float, float, list[Run]]:
    # Zoom 3 (le plus fort que pdftohtml accepte) : places et tailles au tiers de point.
    out = subprocess.run(
        [
            "pdftohtml",
            "-xml",
            "-i",
            "-zoom",
            str(ZOOM),
            "-f",
            str(page),
            "-l",
            str(page),
            "-stdout",
            str(pdf),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    ).stdout
    root = ET.fromstring(out)
    fonts = {f.get("id"): f.attrib for f in root.iter("fontspec")}
    sheet = root.find("page")
    width = float(sheet.get("width")) / ZOOM if sheet is not None else 595.0
    height = float(sheet.get("height")) / ZOOM if sheet is not None else 842.0
    runs = []
    for t in root.iter("text"):
        # Les espaces du bord restent : ils disent s'il faut une espace en recollant.
        text = re.sub(r"\s+", " ", "".join(t.itertext()))
        if not text.strip():
            continue
        spec = fonts[t.get("font")]
        raw = spec["family"]
        markup = ET.tostring(t, encoding="unicode")
        runs.append(
            Run(
                text=text,
                x=float(t.get("left")) / ZOOM,
                y=float(t.get("top")) / ZOOM,
                w=float(t.get("width")) / ZOOM,
                h=float(t.get("height")) / ZOOM,
                font=family_name(raw),
                raw_font=_SUBSET.sub("", raw),
                size=float(spec["size"]) / ZOOM,
                color=_hex(spec.get("color")) or "000000",
                bold="<b>" in markup or bool(re.search(r"bold|black|heavy|semibold", raw, re.I)),
                italic="<i>" in markup or bool(re.search(r"italic|oblique", raw, re.I)),
            )
        )
    return width, height, runs


def _matrix(value: str | None) -> tuple[float, ...]:
    m = re.match(r"matrix\(([^)]*)\)", value or "")
    if not m:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    a, b, c, d, e, f = (float(x) for x in re.split(r"[\s,]+", m.group(1).strip()))
    return (a, b, c, d, e, f)


def _compose(m: tuple[float, ...], n: tuple[float, ...]) -> tuple[float, ...]:
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a * a2 + c * b2,
        b * a2 + d * b2,
        a * c2 + c * d2,
        b * c2 + d * d2,
        a * e2 + c * f2 + e,
        b * e2 + d * f2 + f,
    )


def _points(d: str, m: tuple[float, ...]) -> list[tuple[float, float]]:
    nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?(?:e-?\d+)?", d)]
    a, b, c, dd, e, f = m
    return [
        (a * nums[i] + c * nums[i + 1] + e, b * nums[i] + dd * nums[i + 1] + f)
        for i in range(0, len(nums) - 1, 2)
    ]


def _kind(d: str, w: float, h: float, stroke: bool) -> tuple[str, float]:
    curves = d.count("C")
    if curves == 0:
        if stroke and (w < 1.5 or h < 1.5):
            return "line", 0.0
        return "rect", 0.0
    if curves >= 4 and d.count("L") <= 1:
        return "ellipse", 0.0
    if curves >= 4:
        # Coins arrondis : la taille d'un coin ≈ ce qui dépasse des segments droits.
        return "rect", min(w, h) / 4
    return "path", 0.0


def read_shapes(pdf: Path, page: int = 1) -> tuple[list[Shape], list[Picture]]:
    with tempfile.TemporaryDirectory() as tmp:
        svg = Path(tmp) / "page.svg"
        subprocess.run(
            ["pdftocairo", "-svg", "-f", str(page), "-l", str(page), str(pdf), str(svg)],
            capture_output=True,
            timeout=60,
            check=True,
        )
        root = ET.parse(svg).getroot()
    clips = {c.get("id"): c for c in root.iter(SVG + "clipPath")}
    defs = {id(el) for d in root.iter(SVG + "defs") for el in d.iter()}
    shapes: list[Shape] = []
    pictures: list[Picture] = []

    def walk(el: ET.Element, m: tuple[float, ...], clip: str | None) -> None:
        if id(el) in defs:
            return
        m = _compose(m, _matrix(el.get("transform")))
        clip = el.get("clip-path") or clip
        tag = el.tag.replace(SVG, "")
        if tag == "path":
            d = el.get("d") or ""
            pts = _points(d, m)
            if not pts:
                return
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            box = (min(xs), min(ys), max(xs), max(ys))
            fill, stroke = _hex(el.get("fill")), _hex(el.get("stroke"))
            if fill is None and stroke is None:
                return
            width = float(el.get("stroke-width") or 0) * (abs(m[0]) + abs(m[3])) / 2
            kind, radius = _kind(d, box[2] - box[0], box[3] - box[1], stroke is not None)
            shapes.append(
                Shape(box=box, fill=fill, stroke=stroke, width=width, kind=kind, radius=radius)
            )
        elif tag == "image":
            w, h = float(el.get("width") or 0), float(el.get("height") or 0)
            pts = _points(f"0 0 {w} {h}", m)
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            shape = "square"
            ref = re.match(r"url\(#([^)]+)\)", clip or "")
            if ref and ref.group(1) in clips:
                d = " ".join(p.get("d") or "" for p in clips[ref.group(1)].iter(SVG + "path"))
                if d.count("C") >= 4:
                    shape = "circle" if d.count("L") <= 1 else "rounded"
            pictures.append(Picture(box=(min(xs), min(ys), max(xs), max(ys)), shape=shape))
        elif tag == "use":
            # Une image peut être appelée par <use> depuis <defs>.
            ref = (el.get(XLINK + "href") or el.get("href") or "").lstrip("#")
            target = next((x for x in root.iter() if x.get("id") == ref), None)
            if target is not None and target.tag == SVG + "image":
                defs.discard(id(target))
                walk(
                    target,
                    _compose(m, (1, 0, 0, 1, float(el.get("x") or 0), float(el.get("y") or 0))),
                    clip,
                )
                defs.add(id(target))
            return
        for child in el:
            walk(child, m, clip)

    walk(root, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0), None)
    return shapes, pictures


def merge(runs: list[Run]) -> list[Run]:
    """Recolle les morceaux d'une même ligne et d'un même style que pdftohtml a séparés
    (il coupe parfois un mot en lettres de « tailles » différentes)."""
    # Les lignes d'abord : deux morceaux qui se chevauchent en hauteur sont sur la même.
    lines: list[list[Run]] = []
    for run in sorted(runs, key=lambda r: r.y):
        for line in lines:
            top, bottom = min(r.y for r in line), max(r.bottom for r in line)
            if min(bottom, run.bottom) - max(top, run.y) > 0.5 * min(bottom - top, run.h):
                line.append(run)
                break
        else:
            lines.append([run])
    ordered = [run for line in lines for run in sorted(line, key=lambda r: r.x)]
    out: list[Run] = []
    for run in ordered:
        last = out[-1] if out else None
        if last is not None:
            same = (last.font, last.color, last.bold, last.italic) == (
                run.font,
                run.color,
                run.bold,
                run.italic,
            )
            overlap = min(last.bottom, run.bottom) - max(last.y, run.y)
            gap = run.x - last.right
            size = max(last.size, run.size)
            if same and overlap > 0.5 * min(last.h, run.h) and -1.0 <= gap <= size * 0.45:
                bounded = last.text.endswith(" ") or run.text.startswith(" ")
                space = "" if bounded or gap < size * 0.12 else " "
                y = min(last.y, run.y)
                # Une grande lettre puis des petites de la même police : petites capitales.
                small = last.small
                lo, hi = min(last.size, run.size), max(last.size, run.size)
                if lo < hi * 0.88 and (last.text + run.text).replace(" ", "").isupper():
                    small = lo
                out[-1] = Run(
                    text=last.text + space + run.text,
                    x=last.x,
                    y=y,
                    w=run.right - last.x,
                    h=max(last.bottom, run.bottom) - y,
                    font=last.font,
                    raw_font=last.raw_font,
                    size=size,
                    color=last.color,
                    bold=last.bold,
                    italic=last.italic,
                    small=small,
                )
                continue
        out.append(run)
    for run in out:
        run.text = run.text.strip()
    return out


def read(pdf: Path, page: int = 1) -> Page:
    width, height, runs = read_runs(pdf, page)
    runs = merge(runs)
    shapes, pictures = read_shapes(pdf, page)
    # Les glyphes du texte ne sont pas des formes ; ce qui couvre presque toute la page
    # (fond blanc du document) non plus.
    shapes = [
        s for s in shapes if not (s.fill == "FFFFFF" and s.w > width * 0.9 and s.h > height * 0.9)
    ]
    return Page(width=width, height=height, runs=runs, shapes=shapes, pictures=pictures)
