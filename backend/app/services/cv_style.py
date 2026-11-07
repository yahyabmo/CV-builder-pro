"""Le style d'un CV PDF, pour que le CV de base importé lui ressemble. Sans IA.

``pdftohtml`` (poppler) donne chaque morceau de texte de la première page avec
sa police, sa taille, sa couleur et sa place, et la place des images. Une image
de la page (``pdftoppm``) donne ce que le texte ne dit pas : les fonds colorés
des colonnes, les bandeaux et les filets des titres.

``guess`` rend ce qui a été repéré (une liste lisible, et les réglages) ;
``apply_guess`` l'applique au style et au contenu, élément par élément.
"""

import colorsys
import re
import shutil
import subprocess
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import BaseModel

from app import fonts
from app.models.content import CVContent, Section
from app.models.style import CVStyle, Palette

Badge = Literal["identique", "proche", "approché"]
KEYS = ("font", "colors", "photo", "columns", "titles", "sizes", "header", "order", "bullets")


# ─── Lecture de la page ──────────────────────────────────────────────────────


@dataclass
class Text:
    text: str
    top: float
    left: float
    width: float
    height: float
    size: float
    family: str
    color: str
    bold: bool
    italic: bool

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height

    @property
    def weight(self) -> int:
        return len(self.text.strip())


@dataclass
class Page:
    width: float
    height: float
    texts: list[Text] = field(default_factory=list)
    # (haut, gauche, largeur, hauteur) de chaque image, en points.
    images: list[tuple[float, float, float, float]] = field(default_factory=list)


def _family(raw: str) -> str:
    """« YLUSYM+PTSerif-Bold » → « PTSerif »."""
    name = re.sub(r"^[A-Z]{6}\+", "", raw)
    name = re.split(r"[-,]", name)[0]
    return re.sub(r"(PSMT|MT|PS)$", "", name)


def read_page(pdf: Path) -> Page | None:
    """Le PDF texte par texte, en points ; les pages suivantes à la suite de la première.

    Les dimensions et les images sont celles de la première page.
    """
    if shutil.which("pdftohtml") is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "cv.pdf"
        shutil.copyfile(pdf, copy)
        try:
            run = subprocess.run(
                ["pdftohtml", "-xml", "-stdout", "-q", "-l", "3", "-zoom", "1", copy.name],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
    xml = re.sub(r"<!DOCTYPE[^>]*>", "", run.stdout)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    nodes = root.findall("page")
    if not nodes:
        return None
    first = nodes[0]
    page = Page(width=float(first.get("width", 595)), height=float(first.get("height", 842)))
    # Les polices sont déclarées une fois, sur la page où elles apparaissent.
    specs = {
        spec.get("id"): (
            float(spec.get("size", 10)),
            _family(spec.get("family", "")),
            spec.get("color", "#000000"),
        )
        for spec in root.iter("fontspec")
    }
    for index, node in enumerate(nodes):
        _texts(node, specs, page, offset=index * page.height)
    for image in first.iter("image"):
        page.images.append(
            (
                float(image.get("top", 0)),
                float(image.get("left", 0)),
                float(image.get("width", 0)),
                float(image.get("height", 0)),
            )
        )
    return page


def _texts(node: ET.Element, specs: dict, page: Page, offset: float) -> None:
    for item in node.iter("text"):
        content = "".join(item.itertext())
        if not content.strip():
            continue
        size, family, color = specs.get(item.get("font"), (10.0, "", "#000000"))
        page.texts.append(
            Text(
                text=content,
                top=float(item.get("top", 0)) + offset,
                left=float(item.get("left", 0)),
                width=float(item.get("width", 0)),
                height=float(item.get("height", 0)),
                size=size,
                family=family,
                color=color.lstrip("#").upper().rjust(6, "0"),
                bold=item.find(".//b") is not None,
                italic=item.find(".//i") is not None,
            )
        )


def render_page(pdf: Path, dpi: int = 100) -> Image.Image | None:
    """La première page en image RGB."""
    if shutil.which("pdftoppm") is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "page"
        try:
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
                    str(out),
                ],
                capture_output=True,
                timeout=30,
                check=True,
            )
            return Image.open(out.with_suffix(".png")).convert("RGB")
        except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            return None


# ─── Couleurs ────────────────────────────────────────────────────────────────


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


class Guess(BaseModel):
    """Le style repéré, prêt à appliquer clé par clé (voir ``KEYS``)."""

    findings: list[Finding] = []
    font: str | None = None
    palette: dict[str, str] | None = None
    photo: tuple[bool, Literal["left", "right"]] | None = None
    layout: Literal["one", "two"] | None = None
    widths: tuple[float, float] | None = None
    band: tuple[str, Literal["left", "right"]] | None = None
    titles: Literal["rule", "band", "plain"] | None = None
    sizes: tuple[float, float, int] | None = None
    centered: bool = False
    # (identifiant de rubrique, colonne), dans l'ordre du PDF.
    order: list[tuple[str, Literal["left", "right"]]] | None = None
    bullet: Literal["bullet", "dash", "square", "chevron"] | None = None


def _mode(values: list[tuple[object, int]]) -> object | None:
    counter: Counter = Counter()
    for value, weight in values:
        counter[value] += weight
    return counter.most_common(1)[0][0] if counter else None


def _sample_box(
    image: Image.Image, scale: float, box: tuple[float, float, float, float]
) -> list[tuple[int, int, int]]:
    """Les pixels d'un rectangle (gauche, haut, droite, bas en points), un sur deux."""
    left, top, right, bottom = (round(v * scale) for v in box)
    pixels = image.load()
    width, height = image.size
    out = []
    for y in range(max(0, top), min(height, bottom), 2):
        for x in range(max(0, left), min(width, right), 2):
            out.append(pixels[x, y])
    return out


def _dominant(pixels: list[tuple[int, int, int]]) -> tuple[tuple[int, int, int], float] | None:
    """La couleur la plus présente (arrondie) et sa part."""
    if not pixels:
        return None
    counter = Counter((r // 8 * 8, g // 8 * 8, b // 8 * 8) for r, g, b in pixels)
    color, count = counter.most_common(1)[0]
    near = [p for p in pixels if _near(p, color, 24)]
    average = tuple(sum(c[i] for c in near) / len(near) for i in range(3))
    return (round(average[0]), round(average[1]), round(average[2])), count / len(pixels)


WHITE = (255, 255, 255)


def _rule_below(
    image: Image.Image,
    scale: float,
    heading: Text,
    left: float,
    right: float,
    background: tuple[int, int, int],
) -> tuple[tuple[int, int, int], float] | None:
    """Un filet sous le titre : une ligne de pixels encrée sur presque toute la colonne."""
    pixels = image.load()
    width, height = image.size
    x0, x1 = max(0, round(left * scale)), min(width, round(right * scale))
    start = round((heading.top + heading.height * 0.6) * scale)
    for y in range(max(0, start), min(height, round((heading.bottom + 8) * scale))):
        row = [pixels[x, y] for x in range(x0, x1, 2)]
        inked = [p for p in row if not _near(p, background, 45)]
        if row and len(inked) / len(row) > 0.7:
            return _dominant(inked)
    return None


def guess(pdf: Path, content: CVContent, has_photo: bool) -> Guess:
    """Le style du PDF : police, couleurs, photo, colonnes, titres, tailles, ordre, puces."""
    page = read_page(pdf)
    result = Guess()
    if page is None or not page.texts:
        return result
    texts = page.texts
    body_size = _mode([(round(t.size * 2) / 2, t.weight) for t in texts]) or 10.0
    body_color = (
        _mode([(t.color, t.weight) for t in texts if abs(t.size - body_size) <= 1]) or "000000"
    )
    families = [
        (t.family, t.weight) for t in texts if not any(i in t.family.lower() for i in _ICONS)
    ]
    family = str(_mode(families) or "")
    margin = min(t.left for t in texts)

    # Le nom : le plus grand texte du haut de la page.
    top_texts = [t for t in texts if t.top < page.height * 0.3]
    name = max(top_texts, key=lambda t: t.size, default=None)
    if name and name.size < body_size * 1.4:
        name = None
    if name:
        middle = name.left + name.width / 2
        result.centered = (
            abs(middle - page.width / 2) < page.width * 0.05 and name.left > margin + 20
        )

    # Les titres de rubrique : un mot connu, court, plus grand, gras ou en couleur ;
    # puis seulement ceux qui ont le style le plus courant parmi eux (un intitulé
    # « Diplôme d'ingénieur » en gras n'est pas un titre).
    candidates = [
        t
        for t in texts
        if (name is None or t.top > name.bottom)
        and section_kind(t.text)
        and t.text.strip()[:1].isalpha()
        and t.size >= body_size
        and (t.size >= body_size + 0.8 or t.bold or t.color != body_color)
    ]
    look = _mode([((round(t.size), t.color), 1) for t in candidates])
    headings = [
        t for t in candidates if look and abs(t.size - look[0]) <= 0.6 and t.color == look[1]
    ]  # type: ignore[index]
    heading_color = str(
        _mode([(t.color, t.weight) for t in headings]) or (name.color if name else body_color)
    )
    heading_size = float(_mode([(t.size, 1) for t in headings]) or body_size + 2)

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
    if any(any(i in t.family.lower() for i in _ICONS) for t in texts):
        result.findings.append(
            Finding(
                key="icons",
                label="Icônes",
                found="Des pictogrammes devant les coordonnées",
                done="Pas d’icône : « Téléphone : » écrit en clair, mieux lu par les ATS",
                badge="approché",
            )
        )

    # ── Colonnes et ordre ──
    two = bool(headings) and any(t.left > page.width * 0.33 for t in headings)
    split = min((t.left for t in headings if t.left > page.width * 0.33), default=page.width)
    content_width = page.width - 2 * margin
    if headings:
        result.layout = "two" if two else "one"
        if two:
            left = max(0.15, min(0.8, (split - margin - 12) / content_width))
            right = max(0.15, min(0.8, (page.width - margin - split) / content_width))
            result.widths = (round(left, 2), round(min(right, 0.97 - left), 2))
            result.findings.append(
                Finding(
                    key="columns",
                    label="Colonnes",
                    found=f"Deux colonnes, {round(left * 100)} % et {round(right * 100)} %",
                    done="Deux colonnes, aux mêmes largeurs",
                    badge="identique",
                )
            )
        else:
            result.findings.append(
                Finding(
                    key="columns",
                    label="Colonnes",
                    found="Une seule colonne",
                    done="Mise en page à une colonne",
                    badge="identique",
                )
            )
        placed: list[tuple[str, Literal["left", "right"]]] = []
        seen: set[str] = set()
        side_of = lambda t: "right" if two and t.left >= split - 4 else "left"  # noqa: E731
        for heading in sorted(headings, key=lambda t: (side_of(t), t.top)):
            target = _target(section_kind(heading.text) or "", content.sections)
            if target and target.id not in seen:
                seen.add(target.id)
                placed.append((target.id, side_of(heading)))
        if placed:
            result.order = placed
            parts = []
            for side, label in (("left", "À gauche"), ("right", "À droite")):
                titles = [
                    next(s.title for s in content.sections if s.id == sid).capitalize()
                    for sid, col in placed
                    if col == side
                ]
                if titles:
                    parts.append(f"{label} : {', '.join(titles)}" if two else ", ".join(titles))
            result.findings.append(
                Finding(
                    key="order",
                    label="Ordre des rubriques",
                    found=". ".join(parts) + ".",
                    done="Le même ordre",
                    badge="identique",
                )
            )

    # ── Image de la page : fonds, bandeaux, filets ──
    image = render_page(pdf)
    scale = image.size[0] / page.width if image else 1.0
    band: tuple[str, Literal["left", "right"]] | None = None
    title_band: str | None = None
    rule_color: str | None = None
    if image and headings:
        first = (
            min(t.top for t in headings if t.top < page.height)
            if any(t.top < page.height for t in headings)
            else page.height * 0.3
        )
        regions: list[tuple[Literal["left", "right"], tuple[float, float, float, float]]] = (
            [
                ("left", (0, first, split - 8, page.height * 0.92)),
                ("right", (split, first, page.width, page.height * 0.92)),
            ]
            if two
            else [("left", (0, first, page.width, page.height * 0.92))]
        )
        found_bands = []
        for side, box in regions:
            seen_color = _dominant(_sample_box(image, scale, box))
            if seen_color and seen_color[1] > 0.45 and not _near(seen_color[0], WHITE, 18):
                found_bands.append((_hex(seen_color[0]), side))
        if len(found_bands) == 1:
            band = found_bands[0]
        variants: list[str] = []
        for heading in (h for h in headings if h.bottom < page.height):
            in_band = band is not None and (side_of(heading) == band[1])
            background = _rgb(band[0]) if in_band and band else WHITE
            beside = _sample_box(
                image,
                scale,
                (heading.right + 3, heading.top + 2, heading.right + 40, heading.bottom - 2),
            )
            around = _dominant(beside)
            if around and around[1] > 0.6 and not _near(around[0], background, 30):
                variants.append("band")
                title_band = _hex(around[0])
                continue
            column_left = split if two and side_of(heading) == "right" else margin
            column_right = (
                page.width - margin if not two or side_of(heading) == "right" else split - 12
            )
            ruled = _rule_below(image, scale, heading, column_left, column_right, background)
            if ruled:
                variants.append("rule")
                rule_color = _hex(ruled[0])
            else:
                variants.append("plain")
        result.titles = Counter(variants).most_common(1)[0][0] if variants else None  # type: ignore[assignment]
    if band:
        result.band = band
    if result.titles:
        upper = all(t.text.strip() == t.text.strip().upper() for t in headings)
        bold = any(t.bold for t in headings)
        what = {"rule": "un filet dessous", "band": "dans un bandeau coloré", "plain": "seuls"}[
            result.titles
        ]
        result.findings.append(
            Finding(
                key="titles",
                label="Titres de rubrique",
                found=f"{'En majuscules, ' if upper else ''}{'en gras, ' if bold else ''}{what}",
                done={
                    "rule": "Titres avec filet",
                    "band": "Titres en bandeau",
                    "plain": "Titres seuls",
                }[result.titles],
                badge="identique",
            )
        )

    # ── Couleurs ──
    dated = [
        (t.color, t.weight)
        for t in texts
        if (t.italic or re.search(r"\b(19|20)\d{2}\b", t.text)) and t.size <= body_size + 0.5
    ]
    muted = _mode(dated)
    linked = _mode(
        [
            (t.color, t.weight)
            for t in texts
            if re.search(r"@|https?://|linkedin|github", t.text, re.I)
        ]
    )
    bullets = [t for t in texts if t.text.strip()[:1] in "•–-▪■›➢◦"]
    bullet_color = _mode([(t.color, 1) for t in bullets if t.text.strip()[:1] in "•▪■›➢◦"])
    primary = (
        heading_color
        if _colored(heading_color)
        else (name.color if name and _colored(name.color) else heading_color)
    )
    h, s, light = _hsl(primary)
    text = readable(body_color, band[0] if band else "FFFFFF")
    palette = {
        "primary": readable(primary, "FFFFFF"),
        "text": text,
        "band": band[0] if band else _from_hsl(h, 40, 96),
        "title_band": title_band or _from_hsl(h, 40, 91),
        "secondary": rule_color
        if rule_color and rule_color != primary and _colored(rule_color)
        else _from_hsl(h, max(s - 20, 10), min(light + 18, 60)),
        "accent": str(bullet_color)
        if bullet_color and _colored(str(bullet_color))
        else _from_hsl(h, max(s - 20, 10), min(light + 18, 60)),
        "muted": str(muted) if muted and muted != body_color else _from_hsl(h, 10, 38),
        "link": str(linked) if linked and _colored(str(linked)) else readable(primary, "FFFFFF"),
    }
    palette["muted"] = readable(palette["muted"], palette["band"])
    result.palette = palette
    swatches = ", ".join(f"#{palette[k]}" for k in ("primary", "text", "band"))
    result.findings.append(
        Finding(
            key="colors",
            label="Couleurs",
            found=f"Titres #{heading_color}, texte #{body_color}"
            + (f", fond de colonne #{band[0]}" if band else ""),
            done=f"Une palette en 8 rôles autour de #{palette['primary']} ({swatches})",
            badge="identique" if palette["primary"] == primary else "proche",
        )
    )

    # ── Photo ──
    photos = [
        img
        for img in page.images
        if img[0] < page.height * 0.35 and img[2] > 40 and 0.6 < img[2] / max(img[3], 1) < 1.7
    ]
    if has_photo and photos:
        top, left, width, _ = max(photos, key=lambda img: img[2] * img[3])
        position: Literal["left", "right"] = (
            "right" if left + width / 2 > page.width / 2 else "left"
        )
        result.photo = (True, position)
        result.findings.append(
            Finding(
                key="photo",
                label="Photo",
                found=f"Trouvée, à {'droite' if position == 'right' else 'gauche'} de l’en-tête",
                done=f"Photo à {'droite' if position == 'right' else 'gauche'}",
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
    name_size = name.size if name else 24.0
    base = min((10, 11, 12), key=lambda v: abs(v - body_size))
    result.sizes = (round(name_size * 2) / 2, round(heading_size * 2) / 2, base)
    result.findings.append(
        Finding(
            key="sizes",
            label="Tailles",
            found=f"Nom {name_size:g} pt · titres {heading_size:g} pt · texte {body_size:g} pt",
            done=f"Nom {result.sizes[0]:g} pt · titres {result.sizes[1]:g} pt · texte {base} pt",
            badge="identique" if base == body_size else "proche",
        )
    )
    if result.centered:
        result.findings.append(
            Finding(
                key="header",
                label="En-tête",
                found="Centré",
                done="En-tête centré",
                badge="identique",
            )
        )

    # ── Puces ──
    if bullets:
        symbol = Counter(t.text.strip()[:1] for t in bullets).most_common(1)[0][0]
        kind = {
            "•": "bullet",
            "◦": "bullet",
            "–": "dash",
            "-": "dash",
            "▪": "square",
            "■": "square",
            "›": "chevron",
            "➢": "chevron",
        }[symbol]
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
    if "photo" in keep and found.photo:
        style.photo.visible, style.photo.position = found.photo
    if "columns" in keep and found.layout:
        style.columns.layout = found.layout
        if found.widths:
            style.columns.left_width, style.columns.right_width = found.widths
        style.band.visible = found.band is not None
        if found.band:
            style.band.color = "band"
            style.band.column = found.band[1]
    if "titles" in keep and found.titles:
        style.section_titles.variant = found.titles
        style.spacing.title_rule_visible = found.titles == "rule"
        if found.titles == "band":
            style.section_titles.band_color = "title_band"
            style.section_titles.band_text_color = "primary"
        elif found.titles == "rule":
            style.spacing.title_rule_color = (
                "secondary"
                if found.palette and found.palette["secondary"] != found.palette["primary"]
                else "primary"
            )
    if "sizes" in keep and found.sizes:
        name_size, title_size, base = found.sizes
        style.blocks.name.size, style.blocks.name.leading = name_size, round(name_size * 1.2, 1)
        style.blocks.section_title.size, style.blocks.section_title.leading = (
            title_size,
            round(title_size * 1.2, 1),
        )
        style.page.base_size = base  # type: ignore[assignment]
    if "header" in keep and found.centered:
        style.header.align = "center"
    if "bullets" in keep and found.bullet:
        style.lists.bullet = found.bullet
    if "order" in keep and found.order:
        by_id = {s.id: s for s in content.sections}
        ordered = []
        for section_id, side in found.order:
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
