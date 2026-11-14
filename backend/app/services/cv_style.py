"""Le style d'un CV PDF, pour que le CV de base importé lui ressemble. Sans IA.

La lecture commune des pages (pdfread.reading, ou pdfread.scan pour un scan) donne
chaque mot avec sa police, sa taille et sa couleur, les formes pleines (fonds de colonne,
en-tête sur fond coloré, bandeaux et filets des titres) et les images. pdfread.structure
y trouve les colonnes et les titres de rubrique.

guess rend ce qui a été repéré (une liste lisible, et les réglages) ;
apply_guess l'applique au style et au contenu, élément par élément.
"""

import colorsys
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from app import fonts
from app.models.content import CVContent, Section
from app.models.style import CVStyle, Palette

if TYPE_CHECKING:
    from app.services.pdfread import reading

Badge = Literal["identique", "proche", "approché"]
KEYS = ("font", "colors", "photo", "columns", "titles", "sizes", "header", "order", "bullets")


def _rgb(hex_: str) -> tuple[int, int, int]:
    return int(hex_[0:2], 16), int(hex_[2:4], 16), int(hex_[4:6], 16)


def _hex(rgb: tuple[float, float, float]) -> str:
    return "".join(f"{max(0, min(255, round(v))):02X}" for v in rgb)


def _hsl(hex_: str) -> tuple[float, float, float]:
    r, g, b = (v / 255 for v in _rgb(hex_))
    h, light, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, s * 100, light * 100


def _from_hsl(h: float, s: float, light: float) -> str:
    r, g, b = colorsys.hls_to_rgb(
        (h % 360) / 360, max(0, min(100, light)) / 100, max(0, min(100, s)) / 100
    )
    return _hex((r * 255, g * 255, b * 255))


def _luminance(hex_: str) -> float:
    def channel(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in _rgb(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    x, y = _luminance(a), _luminance(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


def readable(color: str, background: str, ratio: float = 4.5) -> str:
    """La couleur assombrie jusqu'au contraste voulu sur ce fond."""
    h, s, light = _hsl(color)
    found = color
    while contrast(found, background) < ratio and light > 0:
        light -= 2
        found = _from_hsl(h, s, light)
    return found


def _colored(hex_: str) -> bool:
    """Une vraie couleur, pas un noir, un gris ou un blanc."""
    _, s, light = _hsl(hex_)
    return s > 25 and 12 < light < 90


def _near(a: tuple[int, int, int], b: tuple[int, int, int], tolerance: int = 40) -> bool:
    return sum(abs(x - y) for x, y in zip(a, b, strict=True)) <= tolerance


# ─── Polices ─────────────────────────────────────────────────────────────────

# Les polices courantes que l'appli n'a pas : la plus proche, et pourquoi.
_CLOSE: list[tuple[tuple[str, ...], str, str]] = [
    (
        (
            "montserrat",
            "raleway",
            "futura",
            "avenir",
            "gotham",
            "centurygothic",
            "nunito",
            "quicksand",
            "worksans",
            "dmsans",
            "manrope",
            "inter",
            "outfit",
        ),
        "Poppins",
        "sans empattement, géométrique",
    ),
    (
        (
            "calibri",
            "carlito",
            "opensans",
            "segoe",
            "sourcesans",
            "helveticaneue",
            "myriad",
            "verdana",
            "tahoma",
            "trebuchet",
            "ubuntu",
            "candara",
            "corbel",
        ),
        "Lato",
        "sans empattement, humaniste",
    ),
    (
        (
            "arial",
            "helvetica",
            "liberationsans",
            "arimo",
            "roboto",
            "nimbussans",
            "dejavusans",
            "freesans",
        ),
        "NotoSans",
        "sans empattement, neutre",
    ),
    (
        ("oswald", "rajdhani", "exo", "barlowcondensed", "robotocondensed", "archivonarrow"),
        "TitilliumWeb",
        "sans empattement, étroite",
    ),
    (
        (
            "garamond",
            "ebgaramond",
            "caslon",
            "baskerville",
            "minion",
            "palatino",
            "bookantiqua",
            "cormorant",
        ),
        "CrimsonText",
        "à empattement, élégante",
    ),
    (
        ("georgia", "cambria", "caladea", "merriweather", "charter", "droidserif", "bitter"),
        "PTSerif",
        "à empattement, robuste",
    ),
    (
        (
            "timesnewroman",
            "times",
            "liberationserif",
            "tinos",
            "nimbusroman",
            "cmu",
            "computermodern",
            "lmroman",
            "latinmodern",
            "texgyre",
        ),
        "NotoSerif",
        "à empattement, classique",
    ),
    (
        ("sourceserif", "lora", "playfair", "librebaskerville", "crimsonpro"),
        "Spectral",
        "à empattement, littéraire",
    ),
]
_ICONS = ("awesome", "icon", "symbol", "dingbat", "wingding", "material", "academicons", "fontello")


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def match_font(family: str) -> tuple[str, Badge, str]:
    """La police de l'appli pour une famille du PDF : (identifiant, badge, raison)."""
    name = _norm(family)
    available = {_norm(font_id): font_id for font_id in fonts.families()}
    if name in available:
        return available[name], "identique", "l’appli a la même police"
    for key, font_id in available.items():
        if name.startswith(key) and len(key) > 3:
            return font_id, "identique", "l’appli a la même police"
    for fragments, font_id, why in _CLOSE:
        if (
            any(name.startswith(fragment) or fragment in name for fragment in fragments)
            and font_id in fonts.families()
        ):
            return font_id, "approché", f"la plus proche : {why}"
    fallback = "NotoSerif" if "serif" in name and "sans" not in name else "Lato"
    return fallback, "approché", "la plus proche"


# ─── Rubriques ───────────────────────────────────────────────────────────────

_SECTION_WORDS: dict[str, tuple[str, ...]] = {
    "associative": (
        "associatif",
        "associative",
        "benevolat",
        "engagement",
        "volunteer",
        "vieassociative",
    ),
    "education": ("formation", "education", "etudes", "diplome", "cursus", "scolarite"),
    "experience": (
        "experience",
        "parcoursprofessionnel",
        "emploi",
        "stages",
        "employment",
        "workhistory",
    ),
    "projects": ("projet", "project", "realisation", "portfolio"),
    "grid": ("softskill", "qualite", "savoiretre", "atout", "personalskill"),
    "skills": ("competence", "skill", "outils", "technolog", "savoirfaire", "expertise"),
    "languages": ("langue", "language"),
    "interests": (
        "centresdinteret",
        "interet",
        "loisir",
        "hobbies",
        "hobby",
        "passion",
        "interest",
    ),
    "other": (
        "certification",
        "profil",
        "apropos",
        "summary",
        "references",
        "publication",
        "contact",
    ),
}


def section_kind(text: str) -> str | None:
    """Le type de rubrique d'un titre (« EXPÉRIENCE PROFESSIONNELLE » → experience)."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    name = _norm(folded)
    if not name or len(text.strip()) > 40 or len(text.split()) > 5:
        return None
    for kind, words in _SECTION_WORDS.items():
        if any(word in name for word in words):
            return kind
    return None


def _target(kind: str, sections: list[Section]) -> Section | None:
    """La rubrique du contenu qui correspond à un titre du PDF."""
    if kind == "associative":
        return next(
            (
                s
                for s in sections
                if s.kind == "experience" and "associat" in (s.id + s.title).lower()
            ),
            None,
        )
    if kind == "experience":
        return next(
            (
                s
                for s in sections
                if s.kind == "experience" and "associat" not in (s.id + s.title).lower()
            ),
            None,
        )
    wanted = {
        "education": "education",
        "projects": "projects",
        "skills": "skills",
        "languages": "languages",
        "grid": "grid",
        "interests": "bullets",
    }.get(kind)
    return next((s for s in sections if s.kind == wanted), None) if wanted else None


# ─── Ce qui a été repéré ─────────────────────────────────────────────────────


class Finding(BaseModel):
    key: str
    label: str
    found: str
    done: str
    badge: Badge


class Look(BaseModel):
    """La mise en forme d'une ligne repérée (le nom, le titre sous le nom)."""

    size: float
    bold: bool = False
    upper: bool = False
    # None : la couleur du rôle habituel (le texte posé sur un fond prend la sienne).
    color: str | None = None
    # Espace entre les lettres, en % de la taille.
    spacing: float = 0
    font: str | None = None


class Guess(BaseModel):
    """Le style repéré, prêt à appliquer clé par clé (voir ``KEYS``)."""

    findings: list[Finding] = []
    # Le nombre de pages du PDF : le nôtre n'en prend pas plus (voir ``tighter``).
    pages: int = 1
    font: str | None = None
    palette: dict[str, str] | None = None
    photo: tuple[bool, Literal["left", "right"]] | None = None
    photo_shape: Literal["square", "rounded", "circle"] | None = None
    photo_cm: float | None = None
    # (épaisseur en points, couleur) du tour de la photo.
    photo_border: tuple[float, str] | None = None
    layout: Literal["one", "two"] | None = None
    widths: tuple[float, float] | None = None
    margin_cm: float | None = None
    band: tuple[str, Literal["left", "right"]] | None = None
    # Le texte et les titres posés sur le fond de la colonne, s'ils changent de couleur.
    band_text: str | None = None
    band_title: str | None = None
    titles: Literal["rule", "band", "plain"] | None = None
    # Le texte des titres en bandeau, quand il n'est pas de la couleur principale (blanc).
    title_band_text: str | None = None
    title_look: Look | None = None
    sizes: tuple[float, float, int] | None = None
    # La taille du texte courant du PDF, quand elle est sous les 10 pt de l'appli.
    text_size: float | None = None
    centered: bool = False
    # (fond, texte) de l'en-tête posé sur un fond coloré.
    header_fill: tuple[str, str] | None = None
    placement: Literal["top", "left", "right"] = "top"
    summary_side: bool = False
    summary_title: str | None = None
    name_look: Look | None = None
    headline_look: Look | None = None
    # (identifiant de rubrique, colonne), dans l'ordre du PDF.
    order: list[tuple[str, Literal["left", "right"]]] | None = None
    bullet: Literal["bullet", "dash", "square", "chevron"] | None = None


def _mode(values: list[tuple[object, int]]) -> object | None:
    counter: Counter = Counter()
    for value, weight in values:
        counter[value] += weight
    return counter.most_common(1)[0][0] if counter else None


_BULLETS = {
    "•": "bullet",
    "◦": "bullet",
    "●": "bullet",
    "–": "dash",
    "-": "dash",
    "—": "dash",
    "▪": "square",
    "■": "square",
    "›": "chevron",
    "➢": "chevron",
    "▸": "chevron",
    "►": "chevron",
}
_CONTACT = re.compile(r"@|\+?\d[\d .]{7,}\d|linkedin|github|https?://|www\.", re.I)
_YEAR = re.compile(r"\b(19|20)\d{2}\b")


def _fold(text: str) -> str:
    return _norm(unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode())


def _light(hex_: str) -> bool:
    return _luminance(hex_) > 0.8


def _fill(shape: "reading.Shape") -> str | None:
    """La couleur d'une forme pleine ; celle du milieu pour un dégradé."""
    if shape.shade and len(shape.shade) > 1:
        colors = shape.shade[1:]
        return colors[len(colors) // 2]
    return shape.fill


def _first(line: "reading.Line") -> "reading.Word":
    """Le mot qui porte le style d'une ligne : le plus long."""
    return max(line.words, key=lambda w: len(w.text))


def _look(line: "reading.Line", family: str) -> Look:
    word = _first(line)
    letters = [c for c in line.text if c.isalpha()]
    font = None
    if word.font and _norm(word.font) != _norm(family):
        font_id, badge, _ = match_font(word.font)
        font = font_id if badge == "identique" else None
    return Look(
        size=round(word.size * 2) / 2,
        bold=word.bold,
        upper=bool(letters) and all(c.isupper() for c in letters),
        color=word.color,
        spacing=round(100 * word.tracking / word.size, 1) if word.size else 0,
        font=font,
    )


def _inside(line: "reading.Line", box: tuple[float, float, float, float], slack: float = 2) -> bool:
    return (
        line.x0 >= box[0] - slack
        and line.x1 <= box[2] + slack
        and line.top >= box[1] - slack
        and line.bottom <= box[3] + slack
    )


def _same_text(a: str, b: str) -> bool:
    x, y = _fold(a), _fold(b)
    if not x or not y:
        return False
    return x == y or SequenceMatcher(None, x, y).ratio() >= 0.8


def _section_for(title: str, sections: list[Section], used: set[str]) -> Section | None:
    """La rubrique du contenu qui porte ce titre du PDF (au mot près, sinon par son type)."""
    for section in sections:
        if section.id not in used and _same_text(section.title, title):
            return section
    kind = section_kind(title)
    target = _target(kind, sections) if kind else None
    return target if target and target.id not in used else None


def guess(source: "Path | list[reading.Page]", content: CVContent, has_photo: bool) -> Guess:
    """Le style du PDF : police, couleurs, photo, colonnes, en-tête, titres, tailles, ordre,
    puces. ``source`` : le PDF, ou ses pages déjà lues (un scan lu par Tesseract)."""
    from app.services.pdfread import reading, structure  # noqa: PLC0415 (import circulaire)

    pages = reading.read(source) if isinstance(source, Path) else source
    result = Guess()
    if not pages or not pages[0].lines:
        return result
    st = structure.analyse(pages, [s.title for s in content.sections])
    result.pages = len(pages)
    page = pages[0]
    width, height = page.width, page.height
    lines = page.lines
    for line in lines:
        for word in line.words:
            word.color = word.color.upper()
    for shape in page.shapes:
        shape.fill = shape.fill.upper() if shape.fill else None
        shape.stroke = shape.stroke.upper() if shape.stroke else None
        if shape.shade:
            shape.shade = tuple(c.upper() for c in shape.shade)
    words = [w for line in lines for w in line.words if w.text.strip()]
    lanes = st.lanes[0] if st.lanes else [(0.0, width)]

    def weighted(pick, among=words):  # noqa: ANN001, ANN202
        return [(pick(w), len(w.text)) for w in among]

    families = [
        (w.font, len(w.text))
        for w in words
        if w.font and not any(i in w.font.lower() for i in _ICONS)
    ]
    family = str(_mode(families) or "")
    body_size = float(_mode(weighted(lambda w: round(w.size * 2) / 2)) or 10.0)  # type: ignore[arg-type]
    left_margin = min(line.x0 for line in lines)
    right_margin = width - max(line.x1 for line in lines)

    # ── Le nom : le plus grand texte du haut de la page ──
    tops = [
        line for line in lines if line.top < height * 0.35 and any(c.isalpha() for c in line.text)
    ]
    name = max(tops, key=lambda line: _first(line).size, default=None)
    if name and _first(name).size < body_size * 1.4:
        name = None

    # ── Les fonds : une colonne colorée, un en-tête sur fond coloré ──
    filled = [(s, _fill(s)) for s in page.shapes]
    filled = [(s, c) for s, c in filled if c and not _near(_rgb(c), (255, 255, 255), 18)]
    header_box = None
    for shape, color in filled:
        if (
            shape.box[1] <= height * 0.03
            and shape.w >= width * 0.85
            and height * 0.05 <= shape.h <= height * 0.45
            and name
            and _inside(name, shape.box, 4)
        ):
            header_box = shape.box
            on = [w for line in lines if _inside(line, shape.box) for w in line.words]
            text = str(_mode(weighted(lambda w: w.color, on)) or "FFFFFF")
            result.header_fill = (color, text)
            break
    band_shape = None
    for shape, color in sorted(filled, key=lambda sc: -sc[0].h):
        if (
            shape.h >= height * 0.6
            and width * 0.12 <= shape.w <= width * 0.6
            and (shape.box[0] <= width * 0.03 or shape.box[2] >= width * 0.97)
        ):
            band_shape = shape
            side: Literal["left", "right"] = "left" if shape.box[0] <= width * 0.03 else "right"
            result.band = (color, side)
            break

    # ── Colonnes ──
    def lane(line):  # noqa: ANN001, ANN202
        found = st.lane_of(line) if id(line) in st.page_of else []
        return found[0] if len(found) == 1 else None

    titles = [
        t
        for t in st.titles
        if st.page_of.get(id(t)) == 1
        and not (header_box and _inside(t, header_box))
        and not (name and t.top <= name.bottom)
    ]
    title_lanes = sorted({lane(t) for t in titles if lane(t) is not None})
    split = width
    if len(title_lanes) >= 2:
        split = lanes[title_lanes[1]][0]
    elif band_shape is not None:
        split = band_shape.box[2] if result.band and result.band[1] == "left" else band_shape.box[0]
    two = split < width * 0.85 and split > width * 0.15

    def side_of(line) -> Literal["left", "right"]:  # noqa: ANN001
        return "right" if two and line.x0 >= split - 2 else "left"

    margin = (left_margin + right_margin) / 2
    if band_shape is None or not two:
        margin = max(margin, 14)
    result.margin_cm = round(max(0.6, min(2.5, margin / 72 * 2.54)), 2)
    margin = result.margin_cm / 2.54 * 72
    text_width = width - 2 * margin
    if two:
        result.layout = "two"
        right_lines = [line for line in lines if line.x0 >= split - 2]
        left_lines = [line for line in lines if line.x1 <= split + 2]
        if result.band and result.band[1] == "left" and band_shape is not None:
            left = (band_shape.box[2] - margin) / text_width
        else:
            left = (max((line.x1 for line in left_lines), default=split) - margin) / text_width
        if result.band and result.band[1] == "right" and band_shape is not None:
            right = (width - margin - band_shape.box[0]) / text_width
        else:
            right = (
                width - margin - min((line.x0 for line in right_lines), default=split)
            ) / text_width
        left, right = max(0.15, min(0.8, left)), max(0.15, min(0.8, right))
        if left + right > 0.96:
            excess = left + right - 0.96
            left, right = left - excess / 2, right - excess / 2
        result.widths = (round(left, 2), round(right, 2))
        result.findings.append(
            Finding(
                key="columns",
                label="Colonnes",
                found=f"Deux colonnes, {round(left * 100)} % et {round(right * 100)} %"
                + (", l’une sur fond coloré" if result.band else ""),
                done="Deux colonnes, aux mêmes largeurs" + (", même fond" if result.band else ""),
                badge="identique",
            )
        )
    elif titles:
        result.layout = "one"
        result.band = None
        result.findings.append(
            Finding(
                key="columns",
                label="Colonnes",
                found="Une seule colonne",
                done="Mise en page à une colonne",
                badge="identique",
            )
        )
    else:
        result.band = None
    band_side = result.band[1] if result.band else None

    # ── Le texte courant (hors fonds colorés) ──
    plain = [
        w
        for line in lines
        if not (header_box and _inside(line, header_box))
        and not (band_side and side_of(line) == band_side)
        for w in line.words
        if w.text.strip()
    ] or words
    body_color = str(
        _mode([(w.color, len(w.text)) for w in plain if abs(w.size - body_size) <= 1]) or "000000"
    )
    if _light(body_color):
        body_color = "000000"

    # ── En-tête : où vont la photo et les coordonnées, l'accroche ──
    contacts = [line for line in lines if _CONTACT.search(line.text) and line.top < height * 0.8]
    pictures = [
        p
        for p in page.pictures
        if p.w >= 30 and 0.7 < p.w / max(p.h, 1) < 1.45 and p.box[1] < height * 0.6
    ]
    picture = max(pictures, key=lambda p: p.w * p.h, default=None) if has_photo else None
    if two and name and not result.header_fill:
        name_side = side_of(name)
        sides = Counter(side_of(line) for line in contacts)
        other = "left" if name_side == "right" else "right"
        stacked = len({round(line.top) for line in contacts if side_of(line) == other}) >= 2
        photo_there = picture is not None and (
            ("right" if picture.box[0] >= split - 2 else "left") == other
        )
        # Une ligne de coordonnées à cheval sur les deux colonnes (« Ville | Tél | Email »,
        # coupée en morceaux) : l'en-tête est sur toute la largeur.
        across = any(
            abs(a.top - b.top) < 3
            for a in contacts
            if side_of(a) == name_side
            for b in contacts
            if side_of(b) == other
        )
        if not across and (
            (sides[other] > sides[name_side] and stacked)
            or (photo_there and (band_side == other or stacked))
        ):
            result.placement = other  # type: ignore[assignment]
    summary = content.header.summary.strip()
    if summary and result.placement != "top":
        start = _fold(summary)[:18]
        for line in lines:
            if start and _fold(line.text)[:18] and start.startswith(_fold(line.text)[:18]):
                if side_of(line) == result.placement:
                    result.summary_side = True
                    above = [
                        t
                        for t in titles
                        if side_of(t) == result.placement and t.bottom <= line.top + 1
                    ]
                    if above:
                        result.summary_title = max(above, key=lambda t: t.top).text.strip()
                break
    if name:
        middle = (name.x0 + name.x1) / 2
        result.centered = (
            result.placement == "top"
            and abs(middle - width / 2) < width * 0.05
            and name.x0 > left_margin + 20
        )
    parts = []
    if result.header_fill:
        parts.append(f"sur un fond #{result.header_fill[0]}")
    if result.placement != "top":
        where = "de gauche" if result.placement == "left" else "de droite"
        parts.append(f"photo et coordonnées dans la colonne {where}")
        if result.summary_side:
            parts.append("le profil aussi")
    if result.centered:
        parts.append("centré")
    if parts:
        text = ", ".join(parts)
        result.findings.append(
            Finding(
                key="header",
                label="En-tête",
                found=text[0].upper() + text[1:],
                done="Le même en-tête",
                badge="identique",
            )
        )

    # ── Le nom et le titre sous le nom ──
    if name:
        result.name_look = _look(name, family)
        below = [
            line
            for line in lines
            if line is not name
            and name.bottom - 1 <= line.top <= name.bottom + 2.5 * _first(name).size
            and min(line.x1, name.x1) - max(line.x0, name.x0) > -40
            and side_of(line) == side_of(name)
            and not _CONTACT.search(line.text)
        ]
        headline = min(below, key=lambda line: line.top, default=None)
        if headline and content.header.headline and _first(headline).size < _first(name).size:
            result.headline_look = _look(headline, family)

    # ── Police ──
    if family:
        font_id, badge, why = match_font(family)
        result.font = font_id
        shown = (
            fonts.get(font_id).name
            if badge == "identique"
            else re.sub(r"(?<=[a-z])(?=[A-Z])", " ", family)
        )
        result.findings.append(
            Finding(
                key="font",
                label="Police",
                found=shown,
                done=f"{fonts.get(font_id).name} : {why}",
                badge=badge,
            )
        )
    if any(any(i in w.font.lower() for i in _ICONS) for w in words if w.font):
        result.findings.append(
            Finding(
                key="icons",
                label="Icônes",
                found="Des pictogrammes devant les coordonnées",
                done="Pas d’icône : « Téléphone : » écrit en clair, mieux lu par les ATS",
                badge="approché",
            )
        )

    # ── Titres de rubrique ──
    main_titles = [t for t in titles if side_of(t) != band_side] or titles
    side_titles = [t for t in titles if band_side and side_of(t) == band_side]
    heading_color = str(
        _mode([(_first(t).color, 1) for t in main_titles])
        or (name and _first(name).color)
        or body_color
    )
    heading_size = float(
        _mode([(round(_first(t).size * 2) / 2, 1) for t in main_titles]) or body_size + 2
    )  # type: ignore[arg-type]
    rule_color: str | None = None
    title_band: str | None = None
    if main_titles:
        variants = []
        for t in main_titles:
            column = (
                (split, width - margin)
                if side_of(t) == "right" and two
                else (margin, split if two else width - margin)
            )
            kind = "plain"
            for shape, color in [(s, _fill(s) or s.stroke) for s in page.shapes]:
                if not color or shape is band_shape or (header_box and shape.box == header_box):
                    continue
                if (
                    shape.box[0] <= t.x0 + 2
                    and shape.box[2] >= t.x1 - 2
                    and shape.box[1] <= t.top + 2
                    and shape.box[3] >= t.bottom - 2
                    and shape.h <= 3 * t.size
                    and _fill(shape)
                ):
                    kind, title_band = "band", color
                    break
                thin = shape.h <= 3 or shape.kind == "line"
                below = t.top + 0.5 * t.size <= shape.box[1] <= t.bottom + 14
                beside = t.top <= shape.box[1] <= t.bottom and shape.box[0] >= t.x1
                overlap = min(shape.box[2], column[1]) - max(shape.box[0], column[0])
                if thin and (below or beside) and overlap >= 0.3 * (column[1] - column[0]):
                    kind, rule_color = "rule", color
                    break
            variants.append(kind)
        result.titles = Counter(variants).most_common(1)[0][0]  # type: ignore[assignment]
        if result.titles == "band" and _light(heading_color):
            result.title_band_text = heading_color
        result.title_look = _look(max(main_titles, key=lambda t: len(t.text)), family)
        result.title_look.upper = all(
            all(c.isupper() for c in t.text if c.isalpha()) for t in main_titles
        )
        result.title_look.bold = sum(_first(t).bold for t in main_titles) * 2 >= len(main_titles)
        what = {"rule": "un filet dessous", "band": "dans un bandeau coloré", "plain": "seuls"}[
            result.titles  # type: ignore[index]
        ]
        result.findings.append(
            Finding(
                key="titles",
                label="Titres de rubrique",
                found=f"{'En majuscules, ' if result.title_look.upper else ''}"
                f"{'en gras, ' if result.title_look.bold else ''}{what}",
                done={
                    "rule": "Titres avec filet",
                    "band": "Titres en bandeau",
                    "plain": "Titres seuls",
                }[result.titles],  # type: ignore[index]
                badge="identique",
            )
        )
    if band_side:
        band_words = [
            w
            for line in lines
            if side_of(line) == band_side and not any(line is t for t in titles)
            for w in line.words
            if w.text.strip()
        ]
        seen_text = str(_mode(weighted(lambda w: w.color, band_words)) or body_color)
        seen_title = str(_mode([(_first(t).color, 1) for t in side_titles]) or seen_text)
        if seen_text != body_color:
            result.band_text = seen_text
        # Sur le fond, les titres gardent leur couleur (même celle des autres titres).
        if seen_title != heading_color or result.band_text:
            result.band_title = seen_title

    # ── Couleurs ──
    muted = _mode(
        [
            (w.color, len(w.text))
            for w in plain
            if (w.italic or _YEAR.search(w.text)) and w.size <= body_size + 0.5
        ]
    )
    linked = _mode(
        [
            (w.color, len(w.text))
            for w in plain
            if w.url or re.search(r"@|https?://|linkedin|github", w.text, re.I)
        ]
    )
    bullets: list[tuple[str, str]] = []
    for line in lines:
        mark = line.words[0].text.strip()[:1]
        if mark in _BULLETS:
            bullets.append((_BULLETS[mark], line.words[0].color))
    for shape in page.shapes:
        if shape.fill and 1.5 <= shape.w <= 6 and 1.5 <= shape.h <= 6:
            for line in lines:
                if 0 <= line.x0 - shape.box[2] <= 12 and line.top <= shape.box[1] <= line.bottom:
                    bullets.append(
                        ("bullet" if shape.kind in ("ellipse", "path") else "square", shape.fill)
                    )
                    break
    bullet_color = _mode([(c, 1) for _, c in bullets])
    name_color = _first(name).color if name and not result.header_fill else None
    primary = (
        heading_color
        if _colored(heading_color)
        else (name_color if name_color and _colored(name_color) else heading_color)
    )
    if _light(primary):
        # Des titres blancs : sur un bandeau, ou sur le fond d'une colonne.
        if title_band and not _light(title_band):
            primary = title_band
        else:
            primary = name_color if name_color and not _light(name_color) else body_color
    h, s, light = _hsl(primary)
    palette = {
        "primary": readable(primary, "FFFFFF"),
        "text": readable(body_color, "FFFFFF"),
        "band": result.band[0] if result.band else _from_hsl(h, 40, 96),
        "title_band": title_band or _from_hsl(h, 40, 91),
        "secondary": rule_color
        if rule_color and rule_color != primary and not _light(rule_color)
        else _from_hsl(h, max(s - 20, 10), min(light + 18, 60)),
        "accent": str(bullet_color)
        if bullet_color and _colored(str(bullet_color))
        else _from_hsl(h, max(s - 20, 10), min(light + 18, 60)),
        "muted": str(muted)
        if muted and muted != body_color and not _light(str(muted))
        else _from_hsl(h, 10, 38),
        "link": str(linked) if linked and _colored(str(linked)) else readable(primary, "FFFFFF"),
    }
    palette["muted"] = readable(palette["muted"], "FFFFFF", 3.5)
    result.palette = palette
    shown = [f"titres #{heading_color}", f"texte #{body_color}"]
    if result.band:
        shown.append(f"fond de colonne #{result.band[0]}")
    if result.header_fill:
        shown.append(f"fond d’en-tête #{result.header_fill[0]}")
    result.findings.append(
        Finding(
            key="colors",
            label="Couleurs",
            found=", ".join(shown).capitalize(),
            done=f"Une palette en 8 rôles autour de #{palette['primary']}",
            badge="identique" if palette["primary"] == primary else "proche",
        )
    )

    # ── Photo ──
    if picture is not None:
        position: Literal["left", "right"] = (
            "right"
            if (picture.box[0] + picture.box[2]) / 2
            > ((name.x0 + name.x1) / 2 if name else width / 2)
            else "left"
        )
        result.photo = (True, position)
        result.photo_shape = (
            picture.shape if picture.shape in ("square", "rounded", "circle") else "square"
        )  # type: ignore[assignment]
        result.photo_cm = round(max(1.5, min(6.0, picture.w / 72 * 2.54)), 1)
        for shape in page.shapes:
            color = shape.stroke or _fill(shape)
            grow = (shape.w - picture.w) / 2
            if (
                color
                and 0.5 <= grow <= 8
                and abs((shape.box[0] + shape.box[2]) - (picture.box[0] + picture.box[2])) < 4
                and abs((shape.box[1] + shape.box[3]) - (picture.box[1] + picture.box[3])) < 4
            ):
                result.photo_border = (round(shape.width if shape.stroke else grow, 1), color)
                break
        shape_name = {"circle": "ronde", "rounded": "aux coins arrondis", "square": "carrée"}[
            result.photo_shape
        ]  # type: ignore[index]
        where = (
            "dans la colonne de côté"
            if result.placement != "top"
            else f"à {'droite' if position == 'right' else 'gauche'} de l’en-tête"
        )
        result.findings.append(
            Finding(
                key="photo",
                label="Photo",
                found=f"Trouvée, {shape_name}, {where}",
                done=f"Photo {shape_name}, {result.photo_cm:g} cm",
                badge="identique",
            )
        )
    else:
        result.photo = (False, "right")
        result.findings.append(
            Finding(
                key="photo", label="Photo", found="Aucune", done="Sans photo", badge="identique"
            )
        )

    # ── Tailles ──
    name_size = _first(name).size if name else 24.0
    base = min((10, 11, 12), key=lambda v: abs(v - body_size))
    result.sizes = (round(name_size * 2) / 2, round(heading_size * 2) / 2, base)
    if body_size < base - 0.25:
        result.text_size = max(8.0, body_size)
    result.findings.append(
        Finding(
            key="sizes",
            label="Tailles",
            found=f"Nom {name_size:.3g} pt · titres {heading_size:.3g} pt · texte {body_size:g} pt",
            done=f"Nom {result.sizes[0]:g} pt · titres {result.sizes[1]:g} pt · texte "
            f"{result.text_size or base:g} pt",
            badge="identique" if (result.text_size or base) == body_size else "proche",
        )
    )

    # ── Puces ──
    if bullets:
        kind = Counter(k for k, _ in bullets).most_common(1)[0][0]
        result.bullet = kind  # type: ignore[assignment]
        label = {"bullet": "Points", "dash": "Tirets", "square": "Carrés", "chevron": "Chevrons"}[
            kind
        ]
        result.findings.append(
            Finding(
                key="bullets",
                label="Puces",
                found=label,
                done=f"Puces en {label.lower()}",
                badge="identique",
            )
        )

    # ── Ordre des rubriques ──
    placed: list[tuple[str, Literal["left", "right"], int, float]] = []
    used: set[str] = set()
    for block in st.blocks:
        if block.title is None:
            continue
        if block.page == 1 and not any(block.title is t for t in titles):
            continue
        target = _section_for(block.title_text or block.title.text, content.sections, used)
        if target:
            used.add(target.id)
            placed.append((target.id, side_of(block.title), block.page, block.title.top))
    if placed and result.layout:
        placed.sort(key=lambda p: (0 if p[1] == "left" else 1, p[2], p[3]) if two else (p[2], p[3]))
        result.order = [(sid, col) for sid, col, _, _ in placed]
        parts = []
        for col, label in (("left", "À gauche"), ("right", "À droite")):
            names = [
                next(s.title for s in content.sections if s.id == sid).capitalize()
                for sid, c in result.order
                if c == col
            ]
            if names:
                parts.append(f"{label} : {', '.join(names)}" if two else ", ".join(names))
        result.findings.append(
            Finding(
                key="order",
                label="Ordre des rubriques",
                found=". ".join(parts) + ".",
                done="Le même ordre",
                badge="identique",
            )
        )
    return result


# ─── Application ─────────────────────────────────────────────────────────────

# Le rôle que prennent ces éléments quand leur couleur vient du PDF.
_ROLES = {
    "date": "muted",
    "date_in_place": "muted",
    "experience_place": "muted",
    "experience_tag": "muted",
    "project_tag": "muted",
}


def _color_for(color: str | None, palette: dict[str, str] | None) -> str | None:
    """Un rôle de la palette quand la couleur en est un, sinon l'hexadécimal (lisible)."""
    if color is None:
        return None
    for role in ("primary", "text"):
        if palette and palette.get(role) == color:
            return role
    if _light(color):
        return None
    return readable(color, "FFFFFF", 3)


def apply_guess(
    style: CVStyle, content: CVContent, found: Guess, keep: set[str]
) -> tuple[CVStyle, CVContent]:
    """Le style et le contenu, avec ce qui a été repéré pour chaque clé gardée."""
    style = style.model_copy(deep=True)
    content = content.model_copy(deep=True)
    if "font" in keep and found.font:
        style.fonts.main = found.font
        for block in style.blocks.__dict__.values():
            block.font = None
        if found.name_look and found.name_look.font:
            style.blocks.name.font = found.name_look.font
        if found.title_look and found.title_look.font:
            style.blocks.section_title.font = found.title_look.font
    if "colors" in keep and found.palette:
        style.palette = Palette(**found.palette)
        for name, role in _ROLES.items():
            block = getattr(style.blocks, name)
            if block.color is None:
                block.color = role
        if style.lists.bullet_color is None:
            style.lists.bullet_color = "accent"
        if style.links.color is None:
            style.links.color = "link"
        # Un PDF n'a pas de cadre autour de ses liens.
        style.links.hide_boxes = True
        style.blocks.section_title.color = "primary"
        if found.name_look and not found.header_fill:
            style.blocks.name.color = _color_for(found.name_look.color, found.palette) or "primary"
        if found.headline_look and not found.header_fill:
            style.blocks.headline.color = (
                _color_for(found.headline_look.color, found.palette) or "primary"
            )
        if found.band:
            style.band.text_color = found.band_text
            style.band.title_color = found.band_title
    if "photo" in keep and found.photo:
        style.photo.visible, style.photo.position = found.photo
        if found.photo_shape:
            style.photo.shape = found.photo_shape
        if found.photo_cm:
            style.photo.size_mode = "fixed"
            style.photo.size_cm = found.photo_cm
        if found.photo_border:
            style.photo.border_pt, style.photo.border_color = found.photo_border
    if "columns" in keep and found.layout:
        style.columns.layout = found.layout
        # Le PDF ne s'étire pas jusqu'en bas de la page : le nôtre non plus.
        style.columns.fill_page = False
        if found.margin_cm:
            style.page.margin_cm = found.margin_cm
        if found.widths:
            style.columns.left_width, style.columns.right_width = found.widths
        style.band.visible = found.band is not None
        if found.band:
            style.band.color = "band"
            style.band.column = found.band[1]
            style.band.top_offset_pt = 14 if found.placement == "top" else 0
    if "titles" in keep and found.titles:
        style.section_titles.variant = found.titles
        style.spacing.title_rule_visible = found.titles == "rule"
        if found.titles == "band":
            style.section_titles.band_color = "title_band"
            style.section_titles.band_text_color = found.title_band_text or "primary"
        elif found.titles == "rule":
            style.spacing.title_rule_color = (
                "secondary"
                if found.palette and found.palette["secondary"] != found.palette["primary"]
                else "primary"
            )
        if found.title_look:
            style.blocks.section_title.uppercase = found.title_look.upper
            style.blocks.section_title.bold = found.title_look.bold
            style.blocks.section_title.letter_spacing = max(0, min(30, found.title_look.spacing))
    if "sizes" in keep and found.sizes:
        name_size, title_size, base = found.sizes
        style.blocks.name.size, style.blocks.name.leading = name_size, round(name_size * 1.2, 1)
        style.blocks.section_title.size, style.blocks.section_title.leading = (
            title_size,
            round(title_size * 1.2, 1),
        )
        style.page.base_size = base  # type: ignore[assignment]
        if found.text_size:
            # Un texte plus petit que les 10 pt de l'appli : tous les blocs à proportion,
            # sauf le nom et les titres, déjà à leur taille.
            scale = found.text_size / base
            for key, block in style.blocks.__dict__.items():
                if key in ("name", "section_title"):
                    continue
                if block.size is None and key not in _TEXT_BLOCKS:
                    continue
                block.size = round((block.size or base) * scale, 2)
                block.leading = round(block.size * 1.2, 2)
        if found.name_look:
            style.blocks.name.bold = found.name_look.bold
            style.blocks.name.uppercase = found.name_look.upper
        if found.headline_look:
            look = found.headline_look
            style.blocks.headline.size, style.blocks.headline.leading = (
                look.size,
                round(look.size * 1.2, 1),
            )
            style.blocks.headline.bold = look.bold
            style.blocks.headline.uppercase = look.upper
            style.blocks.headline.letter_spacing = max(0, min(30, look.spacing))
    if "header" in keep:
        if found.centered:
            style.header.align = "center"
        if found.header_fill:
            style.header.fill_color, style.header.fill_text_color = found.header_fill
            style.header.rule_visible = False
        if found.placement != "top" and found.layout == "two":
            style.header.placement = found.placement
            style.header.summary_side = found.summary_side
            if found.summary_title:
                style.header.summary_title = found.summary_title[:60]
    if "bullets" in keep and found.bullet:
        style.lists.bullet = found.bullet
    if "order" in keep and found.order:
        by_id = {s.id: s for s in content.sections}
        ordered = []
        for section_id, side in found.order:
            if section_id not in by_id:
                continue
            section = by_id.pop(section_id)
            section.column = side
            ordered.append(section)
        rest = list(by_id.values())
        if found.layout == "one":
            content.sections = ordered + rest
        else:
            content.sections = [s for s in ordered if s.column == "left"] + [
                s for s in rest if s.column == "left"
            ]
            content.sections += [s for s in ordered if s.column == "right"] + [
                s for s in rest if s.column == "right"
            ]
    return style, content


# ─── Tenir sur autant de pages que le PDF ────────────────────────────────────

FIT_STEPS = 4
# Les blocs à la taille du texte courant tant qu'ils n'en ont pas une à eux.
_TEXT_BLOCKS = (
    "summary",
    "contact_label",
    "contact_strong",
    "contact_value",
    "entry_title",
    "skill_label",
    "language_name",
    "project_title",
    "date",
    "body",
)


def tighter(style: CVStyle, step: int) -> CVStyle:
    """Un cran plus serré, sans toucher au texte : 1 les espaces, 2 les marges, 3 et 4 les
    tailles. Les crans s'ajoutent : chacun part du style rendu par le précédent."""
    style = style.model_copy(deep=True)
    if step == 1:
        sp = style.spacing
        for name in ("section_gap_pt", "entry_gap_pt", "skill_gap_pt", "after_title_pt"):
            setattr(sp, name, round(getattr(sp, name) * 0.55, 1))
        sp.place_gap_pt = round(sp.place_gap_pt * 0.6, 1)
        sp.section_stretch = sp.entry_stretch = sp.skill_stretch = 0
        for spacing in (style.lists.left, style.lists.right):
            spacing.itemsep_pt = round(spacing.itemsep_pt * 0.5, 1)
            spacing.topsep_pt = round(spacing.topsep_pt * 0.5, 1)
            spacing.itemsep_stretch_pt = spacing.topsep_stretch_pt = 0
        style.page.parskip_pt = min(style.page.parskip_pt, 1)
        header = style.header
        header.name_gap_pt = round(header.name_gap_pt * 0.6, 1)
        header.headline_gap_pt = round(header.headline_gap_pt * 0.6, 1)
        header.after_contact_pt = round(header.after_contact_pt * 0.6, 1)
        header.fill_padding_pt = round(header.fill_padding_pt * 0.7, 1)
    elif step == 2:
        style.page.margin_cm = round(max(0.7, style.page.margin_cm * 0.75), 2)
        style.page.line_spread = round(max(0.92, style.page.line_spread * 0.96), 2)
    elif step in (3, 4):
        scale = 0.93 if step == 3 else 0.94
        base = float(style.page.base_size)
        for name, block in style.blocks.__dict__.items():
            if block.size is None and name not in _TEXT_BLOCKS:
                continue
            size = (block.size or base) * scale
            block.size = round(max(7.5, size), 2)
            block.leading = round(block.size * 1.2, 2)
        style.photo.size_cm = round(max(1.5, style.photo.size_cm * scale), 2)
    return style
