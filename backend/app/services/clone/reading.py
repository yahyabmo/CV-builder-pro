"""La lecture exacte d'un PDF, page par page : chaque mot, chaque forme, chaque image.

Les caractères viennent de pdfplumber, au centième de point : police, taille, couleur et
ligne de base de chacun (sa matrice), les liens posés sur la page. On les regroupe en
mots (un mot = des lettres collées, d'un même style), puis en segments de ligne (des mots
proches sur une même ligne de base ; un grand blanc, comme avant une date alignée à
droite ou entre deux colonnes, ouvre un autre segment).

Les formes et les images viennent de ``pdftocairo -svg`` : fonds, filets, pastilles,
icônes dessinées (chemins complets), images avec leurs octets et leur découpe.
Tout est en points, depuis le coin haut gauche de la page.
"""

import base64
import re
import statistics
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

SVG = "{http://www.w3.org/2000/svg}"
XLINK = "{http://www.w3.org/1999/xlink}"
# Un blanc plus large que SEGMENT fois la taille du texte ouvre un autre segment.
SEGMENT = 1.4


@dataclass
class Word:
    """Des lettres collées, d'un même style. ``glued`` : collé au mot d'avant (sans espace)."""

    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    baseline: float
    font: str  # famille sans préfixe de sous-ensemble ni graisse : « Poppins »
    raw_font: str
    size: float
    color: str  # RRGGBB
    bold: bool
    italic: bool
    tracking: float = 0.0  # blanc ajouté entre deux lettres, en points
    url: str | None = None
    glued: bool = False

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    def style(self) -> tuple:
        return (self.font, round(self.size, 1), self.color, self.bold, self.italic)


@dataclass
class Line:
    """Un segment de ligne : des mots proches, sur une même ligne de base."""

    words: list[Word]

    @property
    def text(self) -> str:
        out = ""
        for word in self.words:
            out += ("" if word.glued or not out else " ") + word.text
        return out

    @property
    def x0(self) -> float:
        return self.words[0].x0

    @property
    def x1(self) -> float:
        return max(w.x1 for w in self.words)

    @property
    def top(self) -> float:
        return min(w.top for w in self.words)

    @property
    def bottom(self) -> float:
        return max(w.bottom for w in self.words)

    @property
    def baseline(self) -> float:
        return statistics.median(w.baseline for w in self.words)

    @property
    def size(self) -> float:
        """La taille du texte le plus long de la ligne."""
        return max(self.words, key=lambda w: len(w.text)).size


@dataclass
class Shape:
    """Une forme pleine ou un trait. ``box`` = (x0, y0, x1, y1)."""

    box: tuple[float, float, float, float]
    fill: str | None
    stroke: str | None
    width: float
    # « rect », « line », « ellipse », « path » (forme libre, tracée par ``path``).
    kind: str
    radius: float = 0.0
    # Le tracé d'une forme libre, en commandes TikZ, aux coordonnées de la page.
    path: str = ""
    even_odd: bool = False
    # Un dégradé : son sens (« h », « v »), puis ses couleurs du début à la fin.
    shade: tuple[str, ...] | None = None

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
    data: bytes = b""
    ext: str = "png"

    @property
    def w(self) -> float:
        return self.box[2] - self.box[0]

    @property
    def h(self) -> float:
        return self.box[3] - self.box[1]


@dataclass
class Page:
    number: int
    width: float
    height: float
    lines: list[Line] = field(default_factory=list)
    shapes: list[Shape] = field(default_factory=list)
    pictures: list[Picture] = field(default_factory=list)
    # Les liens posés sur la page : (x0, y0, x1, y1, adresse).
    links: list[tuple[float, float, float, float, str]] = field(default_factory=list)
    # Un scan : l'image de la page (le clone la garde en fond, texte lu effacé).
    background: Path | None = None

    def words(self) -> list[Word]:
        return [w for line in self.lines for w in line.words]


# ─── Polices et couleurs ─────────────────────────────────────────────────────

_SUBSET = re.compile(r"^[A-Z]{6}\+")
_WEIGHT = re.compile(
    r"[-,_ ]?(Bold|Black|Heavy|Semi ?Bold|Demi ?Bold|Extra ?Bold|Medium|Regular|Book|Light|Thin"
    r"|Italic|Oblique|BoldItalic|BoldOblique|MT|PS|PSMT)+$",
    re.I,
)
_BOLD = re.compile(
    r"bold|black|heavy|semibold|demibold|extrabold|^CMBX|^CMB\d|^CMSSBX|^SF(?:BX|BI|BL|RB|XC|SX|XI|XL)\d",
    re.I,
)
_ITALIC = re.compile(
    r"italic|oblique|^CMTI|^CMSL|^CMBXTI|^CMBXSL|^CMSSI|^CMITT|^CMSLTT|^SF(?:TI|SL|BI|BL|RI|RL|SI|SO|IT|ST|XI|XL)\d",
    re.I,
)
# Les polices cm-super de LaTeX (« SFRM1000 », « SFBX1200 ») : du Computer Modern, en T1.
_SF = re.compile(
    r"^SF(RM|BX|TI|SL|BI|BL|RB|RI|RL|CC|XC|SC|SS|SX|SI|SO|TT|IT|ST|TC|XI|XL)\d+$", re.I
)


# Les polices de TeX : Computer Modern (une famille par graisse) → Latin Modern.
_CM = re.compile(r"^(?:CM|LM)(R|BX|TI|SL|BXTI|BXSL|B|SS|SSBX|SSI|TT|ITT|SLTT|CSC)(\d+)$", re.I)
_LM = re.compile(r"^LM(Roman|Sans|Mono)(Caps)?(?:Slant|Dunh|Demi|Quot)?\d+", re.I)


def family_name(raw: str) -> str:
    """« ABCDEF+Poppins-BoldItalic » → « Poppins » ; « ArialMT » → « Arial » ;
    « CMBX10 » ou « LMRoman12-Bold » → « LMRoman »."""
    name = _SUBSET.sub("", raw)
    cm = _CM.match(name.split("-")[0])
    if cm:
        kind = cm.group(1).upper()
        if kind == "CSC":
            return "LMRomanCaps"
        return "LMSans" if kind.startswith("SS") else "LMMono" if "TT" in kind else "LMRoman"
    sf = _SF.match(name.split("-")[0])
    if sf:
        kind = sf.group(1).upper()
        if kind in ("CC", "XC", "SC"):
            return "LMRomanCaps"
        if kind in ("SS", "SX", "SI", "SO"):
            return "LMSans"
        return "LMMono" if kind in ("TT", "IT", "ST", "TC") else "LMRoman"
    lm = _LM.match(name)
    if lm:
        return "LM" + lm.group(1).capitalize() + ("Caps" if lm.group(2) else "")
    name = name.split("-")[0].split(",")[0]
    previous = None
    while previous != name:
        previous = name
        name = _WEIGHT.sub("", name)
    return name or raw


def _hex(rgb: tuple[float, float, float]) -> str:
    return "".join(f"{max(0, min(255, round(c * 255))):02X}" for c in rgb)


def color_of(value: object) -> str:
    """La couleur d'un caractère (gris, RVB ou CMJN, de 0 à 1) en RRGGBB."""
    if not isinstance(value, (tuple, list)) or not value:
        return "000000"
    try:
        v = [float(x) for x in value]
    except (TypeError, ValueError):
        return "000000"
    if len(v) == 1:
        return _hex((v[0], v[0], v[0]))
    if len(v) == 3:
        return _hex((v[0], v[1], v[2]))
    if len(v) == 4:
        c, m, y, k = v
        return _hex(((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)))
    return "000000"


# ─── Le texte ────────────────────────────────────────────────────────────────


@dataclass
class _Char:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    baseline: float
    raw: str
    size: float
    color: str
    bold: bool
    italic: bool
    url: str | None
    # Le préfixe de sous-ensemble (« BAAAAA ») et la chasse de la lettre (largeur / taille).
    tag: str = ""
    advance: float = 0.0

    def style(self) -> tuple:
        return (self.raw, round(self.size, 1), self.color, self.bold, self.italic)


def _chars(page, links: list[tuple[float, float, float, float, str]]) -> list[_Char]:
    out = []
    for c in page.chars:
        if not c.get("upright", True):
            continue
        text = c.get("text") or ""
        m = c.get("matrix") or (1, 0, 0, 1, 0, 0)
        full = c.get("fontname") or ""
        raw = _SUBSET.sub("", full)
        # La ligne de base : le haut de la boîte, moins sa hauteur au-dessus de l'origine.
        baseline = c["top"] + (c["y1"] - m[5])
        cx, cy = (c["x0"] + c["x1"]) / 2, (c["top"] + c["bottom"]) / 2
        url = next((u for x0, y0, x1, y1, u in links if x0 <= cx <= x1 and y0 <= cy <= y1), None)
        out.append(
            _Char(
                text=text,
                x0=c["x0"],
                x1=c["x1"],
                top=c["top"],
                bottom=c["bottom"],
                baseline=baseline,
                raw=raw,
                size=float(c.get("size") or 10),
                color=color_of(c.get("non_stroking_color")),
                bold=bool(_BOLD.search(raw)),
                italic=bool(_ITALIC.search(raw)) or abs(m[2]) > 0.05 * abs(m[0] or 1),
                url=url,
                tag=full[:6] if _SUBSET.match(full) else "",
                advance=float(c.get("adv") or 0) / max(float(c.get("size") or 1), 0.1),
            )
        )
    _hidden_bold(out)
    return out


def _hidden_bold(chars: list[_Char]) -> None:
    """Un gras qui ne dit pas son nom : deux sous-ensembles d'une même police (police
    variable, gras simulé), l'un aux lettres nettement plus larges que l'autre."""
    by_font: dict[str, dict[str, dict[str, list[float]]]] = {}
    for c in chars:
        if c.bold or not c.tag or not c.text.isalpha():
            continue
        by_font.setdefault(c.raw, {}).setdefault(c.tag, {}).setdefault(c.text, []).append(c.advance)
    for raw, tags in by_font.items():
        if len(tags) < 2:
            continue
        widths = {
            tag: {ch: statistics.median(v) for ch, v in letters.items()}
            for tag, letters in tags.items()
        }
        names = list(widths)
        bold: set[str] = set()
        for a in names:
            for b in names:
                if a == b:
                    continue
                shared = [ch for ch in widths[a] if ch in widths[b] and widths[b][ch] > 0]
                if len(shared) < 3:
                    continue
                ratio = statistics.median(widths[a][ch] / widths[b][ch] for ch in shared)
                if ratio > 1.025:
                    bold.add(a)
        if bold and len(bold) < len(names):
            for c in chars:
                if c.raw == raw and c.tag in bold:
                    c.bold = True


def _rows(chars: list[_Char]) -> list[list[_Char]]:
    """Les caractères d'une même ligne de base, de gauche à droite (un exposant ou un
    indice rejoint la ligne qu'il accompagne)."""
    rows: list[list[_Char]] = []
    for c in sorted(chars, key=lambda c: (c.baseline, c.x0)):
        if rows and abs(rows[-1][-1].baseline - c.baseline) <= max(0.12 * c.size, 0.8):
            rows[-1].append(c)
        else:
            rows.append([c])
    merged: list[list[_Char]] = []
    for row in rows:
        size = statistics.median(c.size for c in row)
        x0, x1 = min(c.x0 for c in row), max(c.x1 for c in row)
        host = None
        for other in (merged[-1] if merged else None,):
            if other is None:
                continue
            big = statistics.median(c.size for c in other)
            base = statistics.median(c.baseline for c in other)
            near = abs(statistics.median(c.baseline for c in row) - base) <= 0.6 * big
            inside = (
                min(c.x0 for c in other) - 2 * big <= x0
                and x1 <= max(c.x1 for c in other) + 2 * big
            )
            if size <= 0.8 * big and near and inside:
                host = other
        if host is not None:
            host.extend(row)
        else:
            merged.append(row)
    # Un exposant lu avant sa ligne (il est plus haut) : la ligne suivante l'accueille.
    out: list[list[_Char]] = []
    for row in merged:
        if out:
            prev = out[-1]
            small = statistics.median(c.size for c in prev)
            big = statistics.median(c.size for c in row)
            base = statistics.median(c.baseline for c in row)
            if (
                small <= 0.8 * big
                and len(prev) <= 4
                and abs(statistics.median(c.baseline for c in prev) - base) <= 0.6 * big
                and min(c.x0 for c in row) - 2 * big <= min(c.x0 for c in prev)
                and max(c.x1 for c in prev) <= max(c.x1 for c in row) + 2 * big
            ):
                out[-1] = prev + row
                continue
        out.append(row)
    return [sorted(row, key=lambda c: c.x0) for row in out]


# Les ligatures : les polices de remplacement ne les ont pas toujours.
_LIGATURES = str.maketrans(
    {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
)


def _word(chars: list[_Char], glued: bool) -> Word:
    first = chars[0]
    gaps = [b.x0 - a.x1 for a, b in zip(chars, chars[1:], strict=False)]
    tracking = statistics.median(gaps) if len(gaps) >= 2 else 0.0
    return Word(
        text="".join(c.text for c in chars).translate(_LIGATURES),
        x0=first.x0,
        x1=chars[-1].x1,
        top=min(c.top for c in chars),
        bottom=max(c.bottom for c in chars),
        baseline=statistics.median(c.baseline for c in chars),
        font=family_name(first.raw),
        raw_font=first.raw,
        size=statistics.median(c.size for c in chars),
        color=first.color,
        bold=first.bold,
        italic=first.italic,
        tracking=round(tracking, 3) if tracking > 0.25 else 0.0,
        url=first.url,
        glued=glued,
    )


def _segments(row: list[_Char]) -> list[Line]:
    """Une ligne de caractères → ses segments, chacun en mots."""
    visible = [c for c in row if c.text.strip()]
    if not visible:
        return []
    # Le blanc habituel entre deux lettres (espacement des lettres compris).
    small = [b.x0 - a.x1 for a, b in zip(visible, visible[1:], strict=False)]
    inner = statistics.median(small) if small else 0.0
    inner = max(min(inner, 0.4 * visible[0].size), 0.0)
    lines: list[Line] = []
    words: list[Word] = []
    current: list[_Char] = []
    glued = False
    space = False
    previous: _Char | None = None
    for c in row:
        if not c.text.strip():
            space = True
            continue
        if previous is not None:
            gap = c.x0 - previous.x1
            size = max(c.size, previous.size)
            if gap > SEGMENT * size + inner:
                if current:
                    words.append(_word(current, glued))
                if words:
                    lines.append(Line(words))
                words, current, glued, space = [], [], False, False
            elif space or gap > inner + 0.1 * size:
                if current:
                    words.append(_word(current, glued))
                current, glued = [], False
            elif c.style() != previous.style() or c.url != previous.url:
                if current:
                    words.append(_word(current, glued))
                current, glued = [], True
        current.append(c)
        space = False
        previous = c
    if current:
        words.append(_word(current, glued))
    if words:
        lines.append(Line(words))
    return lines


def _links(page) -> list[tuple[float, float, float, float, str]]:
    out = []
    for link in getattr(page, "hyperlinks", []) or []:
        uri = link.get("uri")
        if uri:
            out.append((link["x0"] - 1, link["top"] - 1, link["x1"] + 1, link["bottom"] + 1, uri))
    return out


def read_text(pdf: Path) -> list[tuple[float, float, list[Line], list]]:
    """Chaque page : sa largeur, sa hauteur, ses segments de ligne (de haut en bas) et ses
    liens."""
    import logging

    import pdfplumber

    # pdfminer se plaint des polices sans boîte (FontBBox) : sans conséquence ici.
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    out = []
    with pdfplumber.open(pdf) as doc:
        for page in doc.pages:
            links = _links(page)
            chars = _chars(page, links)
            lines = [segment for row in _rows(chars) for segment in _segments(row)]
            lines.sort(key=lambda line: (round(line.baseline, 1), line.x0))
            out.append((float(page.width), float(page.height), lines, links))
    return out


# ─── Les formes et les images ────────────────────────────────────────────────


def _svg_color(value: str | None, gradients: dict[str, str]) -> str | None:
    if not value or value == "none":
        return None
    ref = re.match(r"url\(#([^)]+)\)", value)
    if ref:
        return gradients.get(ref.group(1))
    if value.startswith("#"):
        v = value[1:]
        if len(v) == 3:
            v = "".join(ch * 2 for ch in v)
        return v.upper()
    m = re.match(r"rgb\(\s*([\d.]+)%,\s*([\d.]+)%,\s*([\d.]+)%\s*\)", value)
    if m:
        return "".join(f"{round(float(g) * 2.55):02X}" for g in m.groups())
    m = re.match(r"rgb\(\s*(\d+),\s*(\d+),\s*(\d+)\s*\)", value)
    if m:
        return "".join(f"{int(g):02X}" for g in m.groups())
    return None


def _matrix(value: str | None) -> tuple[float, ...]:
    m = re.match(r"matrix\(([^)]*)\)", value or "")
    if m:
        a, b, c, d, e, f = (float(x) for x in re.split(r"[\s,]+", m.group(1).strip()))
        return (a, b, c, d, e, f)
    t = re.match(r"translate\(([^)]*)\)", value or "")
    if t:
        parts = [float(x) for x in re.split(r"[\s,]+", t.group(1).strip())]
        return (1.0, 0.0, 0.0, 1.0, parts[0], parts[1] if len(parts) > 1 else 0.0)
    return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


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


def _apply(m: tuple[float, ...], x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


_TOKEN = re.compile(r"[MLCZHVmlczhv]|-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?")


def _commands(d: str) -> list[tuple[str, list[float]]]:
    out: list[tuple[str, list[float]]] = []
    for token in _TOKEN.findall(d):
        if token.isalpha():
            out.append((token, []))
        elif out:
            out[-1][1].append(float(token))
    return out


def _trace(d: str, m: tuple[float, ...]) -> tuple[str, list[tuple[float, float]]]:
    """Le tracé SVG (M, L, C, H, V, Z absolus) en TikZ, et ses points, sur la page."""
    parts: list[str] = []
    points: list[tuple[float, float]] = []
    x = y = 0.0
    for op, nums in _commands(d):
        op_up = op.upper()
        if op_up == "Z":
            parts.append("-- cycle")
            continue
        step = {"M": 2, "L": 2, "C": 6, "H": 1, "V": 1}.get(op_up, 2)
        for i in range(0, len(nums) - step + 1, step):
            chunk = nums[i : i + step]
            if op_up == "H":
                chunk = [chunk[0], y]
            elif op_up == "V":
                chunk = [x, chunk[0]]
            pts = [_apply(m, chunk[j], chunk[j + 1]) for j in range(0, len(chunk), 2)]
            points += pts
            coords = [f"({px:.2f},{py:.2f})" for px, py in pts]
            if op_up == "M" and i == 0:
                parts.append(coords[0])
            elif op_up == "C":
                parts.append(f".. controls {coords[0]} and {coords[1]} .. {coords[2]}")
            else:
                parts.append(f"-- {coords[0]}")
            x, y = chunk[-2], chunk[-1]
    return " ".join(parts), points


def _kind(d: str, w: float, h: float, stroke: bool) -> tuple[str, float]:
    ops = [op.upper() for op, _ in _commands(d)]
    # Les sous-tracés qui dessinent (cairo finit par un « M » seul après « Z »).
    subpaths = sum(
        1 for i, op in enumerate(ops) if op == "M" and i + 1 < len(ops) and ops[i + 1] in "LCHV"
    )
    curves, straight = ops.count("C"), sum(1 for op in ops if op in "LHV")
    if subpaths <= 1 and curves == 0:
        if stroke and (w < 1.5 or h < 1.5):
            return "line", 0.0
        if straight <= 4:
            return ("line" if min(w, h) < 1.5 else "rect"), 0.0
        return "path", 0.0
    if subpaths == 1 and curves >= 4 and straight <= 1 and abs(w - h) < 0.6 * max(w, h):
        return "ellipse", 0.0
    if subpaths == 1 and curves == 4 and 3 <= straight <= 4:
        # Coins arrondis : la taille d'un coin ≈ ce qui dépasse des segments droits.
        return "rect", min(w, h) / 4
    return "path", 0.0


def _clip_shape(d: str) -> str:
    """La découpe d'une image : ronde (tous les points à la même distance du centre, à
    l'ellipse près), aux coins arrondis, ou carrée."""
    if d.count("C") < 4:
        return "square"
    ends = []
    for _, nums in _commands(d):
        if len(nums) >= 2:
            ends.append((nums[-2], nums[-1]))
    if len(ends) < 4:
        return "rounded"
    xs, ys = [p[0] for p in ends], [p[1] for p in ends]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    rx, ry = (max(xs) - min(xs)) / 2 or 1, (max(ys) - min(ys)) / 2 or 1
    radii = [((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 for x, y in ends]
    return "circle" if all(0.9 <= r <= 1.1 for r in radii) else "rounded"


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
    ids = {el.get("id"): el for el in root.iter() if el.get("id")}
    gradients: dict[str, str] = {}
    shades: dict[str, tuple[str, ...]] = {}
    for tag in ("linearGradient", "radialGradient"):
        for g in root.iter(SVG + tag):
            stops = [s for s in g.iter(SVG + "stop")]
            colors = [_svg_color(s.get("stop-color") or "", {}) for s in stops]
            colors = [c for c in colors if c]
            if colors:
                gid = g.get("id") or ""
                gradients[gid] = colors[len(colors) // 2]
                if tag == "linearGradient" and len(colors) >= 2:
                    dx = float(g.get("x2") or 1) - float(g.get("x1") or 0)
                    dy = float(g.get("y2") or 0) - float(g.get("y1") or 0)
                    way = "h" if abs(dx) >= abs(dy) else "v"
                    ordered = colors if (dx if way == "h" else dy) >= 0 else colors[::-1]
                    step = max(1, len(ordered) // 48)
                    sample = ordered[::step]
                    if sample[-1] != ordered[-1]:
                        sample.append(ordered[-1])
                    shades[gid] = (way, *sample)
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
            fill = _svg_color(el.get("fill", "#000000"), gradients)
            ref = re.match(r"url\(#([^)]+)\)", el.get("fill") or "")
            shade = shades.get(ref.group(1)) if ref else None
            stroke = _svg_color(el.get("stroke"), gradients)
            if el.get("fill-opacity") == "0" or el.get("opacity") == "0":
                fill = None
            if fill is None and stroke is None:
                return
            trace, pts = _trace(d, m)
            if not pts:
                return
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            box = (min(xs), min(ys), max(xs), max(ys))
            width = float(el.get("stroke-width") or 1) * (abs(m[0]) + abs(m[3])) / 2
            kind, radius = _kind(d, box[2] - box[0], box[3] - box[1], stroke is not None)
            shapes.append(
                Shape(
                    box=box,
                    fill=fill,
                    stroke=stroke,
                    width=width if stroke else 0.0,
                    kind=kind,
                    radius=radius,
                    path=trace if kind == "path" else "",
                    even_odd=el.get("fill-rule") == "evenodd",
                    shade=shade,
                )
            )
        elif tag == "image":
            w, h = float(el.get("width") or 0), float(el.get("height") or 0)
            corners = [_apply(m, 0, 0), _apply(m, w, 0), _apply(m, 0, h), _apply(m, w, h)]
            xs, ys = [p[0] for p in corners], [p[1] for p in corners]
            shape = "square"
            ref = re.match(r"url\(#([^)]+)\)", clip or "")
            if ref and ref.group(1) in clips:
                d = " ".join(p.get("d") or "" for p in clips[ref.group(1)].iter(SVG + "path"))
                shape = _clip_shape(d)
            href = el.get(XLINK + "href") or el.get("href") or ""
            data, ext = b"", "png"
            found = re.match(r"data:image/(png|jpe?g);base64,(.*)", href, re.S)
            if found:
                ext = "jpg" if found.group(1).startswith("j") else "png"
                data = base64.b64decode(found.group(2))
            pictures.append(
                Picture(box=(min(xs), min(ys), max(xs), max(ys)), shape=shape, data=data, ext=ext)
            )
        elif tag == "use":
            # Une image peut être appelée par <use> depuis <defs> (les lettres aussi : ignorées).
            ref = (el.get(XLINK + "href") or el.get("href") or "").lstrip("#")
            target = ids.get(ref)
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


def read(pdf: Path) -> list[Page]:
    """Toutes les pages du PDF."""
    pages = []
    for number, (width, height, lines, links) in enumerate(read_text(pdf), 1):
        shapes, pictures = read_shapes(pdf, number)
        # Ce qui couvre presque toute la page en blanc (le fond du document) n'est pas une forme.
        shapes = [
            s
            for s in shapes
            if not (
                s.fill == "FFFFFF" and s.w > width * 0.9 and s.h > height * 0.9 and not s.stroke
            )
        ]
        pages.append(Page(number, width, height, lines, shapes, pictures, links))
    return pages
