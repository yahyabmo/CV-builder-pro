"""La mise en page ancrée, tirée de la page lue et des champs retrouvés (sans IA).

Chaque segment de ligne porte des mots ; chaque mot appartient à un champ du contenu ou
reste un texte fixe (séparateur, titre sans rubrique). Les segments qui partagent un
champ forment une unité (une puce sur trois lignes, une ligne de coordonnées) ; une
unité garde ses lignes exactes, sa boîte pour couler si le texte change, sa colonne et
l'écart qui la sépare de l'unité d'avant.
"""

import re
import statistics
import subprocess
import tempfile
from collections import Counter
from functools import lru_cache
from pathlib import Path

from app import fonts as app_fonts
from app.models.content import CVContent
from app.services.clone import fields as F
from app.services.clone import fonts as clone_fonts
from app.services.clone.plan import (
    AnchoredLayout,
    Glyph,
    Ink,
    ItemPlan,
    Link,
    PageSize,
    Paint,
    Part,
    Photo,
    Picture,
    Row,
    SectionPlan,
    Unit,
)
from app.services.clone.reading import Line, Page, Word
from app.services.clone.structure import PRIVATE_BULLETS, Structure, is_marker, lanes_of

ASSETS = "clone-images"


@lru_cache(maxsize=64)
def _resolved(family: str, online: bool) -> tuple[str, str]:
    return clone_fonts.resolve(family, online)


def _style(bold: bool, italic: bool) -> str:
    return {(False, False): "regular", (True, False): "bold", (False, True): "italic"}.get(
        (bold, italic), "bold_italic"
    )


@lru_cache(maxsize=128)
def _cmap(font_id: str, style: str) -> frozenset[int]:
    try:
        from fontTools.ttLib import TTFont

        with TTFont(str(app_fonts.get(font_id).file(style)), lazy=True) as font:
            return frozenset(font.getBestCmap() or {})
    except Exception:  # noqa: BLE001 — une police illisible : on n'en sait rien
        return frozenset()


def missing(font_id: str, bold: bool, italic: bool, text: str) -> bool:
    """La police de l'appli n'a pas toutes les lettres de ``text`` (une icône de police)."""
    cmap = _cmap(font_id, _style(bold, italic))
    return bool(cmap) and any(ord(ch) not in cmap for ch in text if not ch.isspace())


class Inks:
    def __init__(self, online: bool) -> None:
        self.online = online
        self.items: list[Ink] = []
        self.index: dict[tuple, int] = {}
        self.fonts: dict[str, tuple[str, str]] = {}

    def of(self, w: Word, upper: bool = False) -> int:
        font_id, badge = _resolved(w.font, self.online)
        self.fonts[w.font] = (font_id, badge)
        ink = Ink(
            font=font_id,
            size=round(w.size, 2),
            color=w.color,
            bold=w.bold,
            italic=w.italic,
            tracking=round(w.tracking, 2),
            upper=upper,
        )
        k = tuple(ink.model_dump().values())
        if k not in self.index:
            self.index[k] = len(self.items)
            self.items.append(ink)
        return self.index[k]


def _dominant(words: list[Word]) -> Word:
    """Le mot qui donne le style d'un champ : le style du plus de lettres, hors mots mis en
    valeur (un gras au milieu d'un texte courant)."""
    count: Counter = Counter()
    for w in words:
        count[w.style()] += len(w.text)
    style = count.most_common(1)[0][0]
    return next(w for w in words if w.style() == style)


def _upper(words: list[Word], text: str) -> bool:
    letters = "".join(ch for w in words for ch in w.text if ch.isalpha())
    return bool(letters) and letters.isupper() and any(ch.islower() for ch in text)


class _Snapshots:
    """Les mots qu'aucune police de l'appli ne sait écrire (icônes de police) : leur image,
    découpée dans la page d'origine."""

    def __init__(self, pdf: Path | None, folder: Path | None) -> None:
        self.pdf, self.folder = pdf, folder
        self.count = 0

    def take(self, page: int, box: tuple[float, float, float, float]) -> str | None:
        if self.pdf is None or self.folder is None:
            return None
        dpi = 600
        scale = dpi / 72
        x0, y0, x1, y1 = box
        self.count += 1
        name = f"glyph-{self.count}"
        target = self.folder / ASSETS
        target.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            stem = Path(tmp) / "g"
            run = subprocess.run(
                [
                    "pdftoppm", "-png", "-r", str(dpi), "-f", str(page), "-l", str(page),
                    "-x", str(int(x0 * scale)), "-y", str(int(y0 * scale)),
                    "-W", str(max(1, int((x1 - x0) * scale) + 1)),
                    "-H", str(max(1, int((y1 - y0) * scale) + 1)),
                    "-singlefile", str(self.pdf), str(stem),
                ],
                capture_output=True,
                timeout=30,
            )  # fmt: skip
            if run.returncode != 0 or not stem.with_suffix(".png").is_file():
                return None
            (target / f"{name}.png").write_bytes(stem.with_suffix(".png").read_bytes())
        return f"{ASSETS}/{name}.png"


def _mark(path: str | None, content: CVContent) -> str:
    if path is None:
        return "none"
    parts = path.split(".")
    if parts[0] in ("name", "headline", "summary"):
        return "header"
    if parts[0] == "contact":
        i = int(parts[1])
        seen = 0
        for number, line in enumerate(content.header.contact_lines):
            if i < seen + len(line):
                return f"contact {number}"
            seen += len(line)
        return "contact 0"
    if parts[1] == "title":
        return f"section {parts[0]}"
    if len(parts) >= 4 and parts[2] == "bullets":
        return f"bullet {parts[0]} {parts[1]} {parts[3]}"
    return f"item {parts[0]} {parts[1]}"


def _role(path: str | None, content: CVContent) -> str:
    if path is None:
        return "label"
    parts = path.split(".")
    if parts[0] in ("name", "headline", "summary"):
        return "header"
    if parts[0] == "contact":
        return "contact"
    if parts[1] == "title":
        return "title"
    if len(parts) >= 4 and parts[2] == "bullets":
        return "bullet"
    section = next((s for s in content.sections if s.id == parts[0]), None)
    if section is not None and section.kind in ("bullets", "grid", "skills", "languages"):
        return "list"
    return "field"


def _join(words: list[Word]) -> str:
    out = ""
    for w in words:
        out += ("" if w.glued or not out else " ") + w.text
    return out


def _background(page: Page, folder: Path | None) -> str | None:
    """L'image d'un scan, gardée telle quelle en fond de page : le texte lu y est posé en
    invisible (il se copie, un logiciel de recrutement le lit) ; seul ce qui change est effacé
    de l'image et réécrit."""
    if page.background is None or folder is None or not Path(page.background).is_file():
        return None
    from PIL import Image

    with Image.open(page.background) as opened:
        image = opened.convert("RGB")
    target = folder / ASSETS
    target.mkdir(exist_ok=True)
    name = f"{ASSETS}/fond-{page.number}.jpg"
    image.save(folder / name, "JPEG", quality=90)
    return name


def _ink_below(image, scale: float, left: float, right: float, bottom: float, high: float) -> float:
    """Le bas de l'encre qui suit une ligne de près (un filet, un trait), sans aller jusqu'au
    bloc suivant : 0 s'il n'y en a pas."""
    from app.services.clone.scan import _ground

    x0, x1 = max(0, int(left * scale)), min(image.width, int(right * scale))
    if x1 - x0 < 6:
        return 0.0
    ground = _ground(image, (x0, int((bottom - high) * scale), x1, int(bottom * scale)))

    def inked(y: int) -> bool:
        hits = 0
        for x in range(x0, x1, 3):
            pixel = image.getpixel((x, y))
            if sum(abs(pixel[i] - ground[i]) for i in range(3)) > 90:
                hits += 1
        return hits >= max(3, (x1 - x0) // 300)

    start = int((bottom + 1.0) * scale)
    reach = min(image.height, int((bottom + 1.2 * high) * scale))
    first = next((y for y in range(start, reach) if inked(y)), None)
    if first is None:
        return 0.0
    last, y, blank = first, first, 0
    stop = min(image.height, first + int(2.0 * high * scale))
    while y < stop and blank <= 2:
        if inked(y):
            last, blank = y, 0
        else:
            blank += 1
        y += 1
    if y >= stop:
        return 0.0  # un bloc qui continue : ce n'est pas un filet
    return (last + 1) / scale + 0.6


def _punctuation(parts: list[Part], groups: list[list[Word]], content: CVContent) -> list[Part]:
    """Les signes collés à un champ sur la page mais absents de son texte (« discrétion, »)
    vont dans le séparateur qui le suit ; un séparateur que le champ d'avant contient déjà
    (« Qualités : » puis « : ») ne se répète pas. Pour le texte qui coule quand l'unité change."""
    out: list[Part] = []
    for i, (part, group) in enumerate(zip(parts, groups, strict=True)):
        if part.path is None:
            previous = out[-1] if out else None
            core = part.text.strip()
            if previous is not None and previous.path and core:
                value = (F.get(content, previous.path) or "").rstrip()
                if value.endswith(core):
                    part = part.model_copy(
                        update={"text": " " if part.text != part.text.strip() else ""}
                    )
                    if not part.text:
                        continue
            out.append(part)
            continue
        out.append(part)
        if not group:
            continue
        tail = re.search(r"[,;:.]+$", group[-1].text)
        value = (F.get(content, part.path) or "").rstrip()
        if tail is None or value.endswith(tail.group()):
            continue
        following = parts[i + 1] if i + 1 < len(parts) else None
        if following is not None and following.path is None:
            if not following.text.lstrip().startswith(tail.group()):
                parts[i + 1] = following.model_copy(update={"text": tail.group() + following.text})
        else:
            out.append(Part(text=tail.group(), ink=part.ink))
    return out


def _erasers(page: Page, units: list[Unit], structure: Structure, folder: Path) -> None:
    """Pour chaque unité d'un scan : sa bande d'image (ses mots, et ce qui l'accompagne au-dessus
    jusqu'à l'unité précédente : une puce, une icône, une étiquette que la lecture a manquée),
    à déplacer telle quelle si l'unité descend ; et les boîtes de ses mots, à couvrir si son
    texte change."""
    from PIL import Image, ImageChops

    from app.services.clone.scan import _ground

    with Image.open(page.background) as opened:  # type: ignore[arg-type]
        image = opened.convert("RGB")
    scale = image.width / page.width
    mine = [u for u in units if u.page == page.number and getattr(u, "_boxes", None)]
    extent = {}
    for u in mine:
        boxes = u._all  # type: ignore[attr-defined]
        extent[u.id] = (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )
    target = folder / ASSETS
    target.mkdir(exist_ok=True)
    for u in mine:
        x0, top, x1, bottom = extent[u.id]
        own = set(u.lanes)
        # Les bords du texte de sa colonne (pas le couloir : un fond de couleur peut le border).
        column = [extent[o.id] for o in mine if own & set(o.lanes)]
        left_edge = min(b[0] for b in column) - 2
        right_edge = max(b[2] for b in column) + 2
        row = [
            extent[o.id]
            for o in mine
            if o is not u
            and own & set(o.lanes)
            and extent[o.id][1] < bottom
            and extent[o.id][3] > top
        ]
        # Jusqu'aux bords de la colonne, sauf s'il y a une autre unité sur la même ligne.
        left = max([b[2] + 1 for b in row if b[2] <= x0 + 1] or [left_edge + 1])
        right = min([b[0] - 1 for b in row if b[0] >= x1 - 1] or [right_edge - 1])
        left, right = min(left, x0 - 2), max(right, x1 + 2)
        above = [
            extent[o.id][3]
            for o in mine
            if o is not u
            and own & set(o.lanes)
            and extent[o.id][3] <= top + 0.5
            and extent[o.id][0] < right
            and extent[o.id][2] > left
        ]
        upper = max(above) + 0.6 if above else top - 3
        # Vers le bas : les jambages (p, g, j) que la boîte lue n'a pas toujours, sans toucher
        # l'unité d'en dessous.
        below = [
            extent[o.id][1]
            for o in mine
            if o is not u
            and own & set(o.lanes)
            and extent[o.id][1] >= bottom - 0.5
            and extent[o.id][0] < right
            and extent[o.id][2] > left
        ]
        high = statistics.median(b[3] - b[1] for b in u._all)  # type: ignore[attr-defined]
        lower = bottom + 0.35 * high
        if below:
            lower = min(lower, min(below) - 0.6)
        else:
            # La dernière ligne de sa colonne : l'encre juste dessous (un filet de fin de
            # rubrique) descend avec elle, plutôt que de rester sous le texte décalé.
            lower = max(lower, _ink_below(image, scale, left, right, bottom, high))
        lower = max(lower, bottom + 1.0)
        box_px = (
            max(0, int(left * scale)),
            max(0, int(upper * scale)),
            min(image.width, int(right * scale) + 1),
            min(image.height, int(lower * scale) + 1),
        )
        if box_px[2] - box_px[0] < 2 or box_px[3] - box_px[1] < 2:
            continue
        crop = image.crop(box_px)
        border = [crop.getpixel((x, 0)) for x in range(0, crop.width, 3)] + [
            crop.getpixel((x, crop.height - 1)) for x in range(0, crop.width, 3)
        ]
        color = tuple(int(statistics.median(p[i] for p in border)) for i in range(3))
        # Seulement l'encre : le fond devient transparent, la bande ne cache jamais rien.
        alpha = (
            ImageChops.difference(crop, Image.new("RGB", crop.size, color))
            .convert("L")
            .point(lambda v: 0 if v < 14 else min(255, (v - 14) * 255 // 56))
        )
        name = f"{ASSETS}/bande-{page.number}-{u.id}.png"
        inked = crop.copy()
        inked.putalpha(alpha)
        inked.save(folder / name, "PNG", optimize=True)
        # Le signe de puce (ou l'icône) seul, sans les mots : pour une unité qui change.
        sign_alpha = alpha.copy()
        for bx0, btop, bx1, bbottom in u._boxes:  # type: ignore[attr-defined]
            pad = max(1.0, 0.1 * (bbottom - btop))
            sign_alpha.paste(
                0,
                (
                    int((bx0 - pad) * scale) - box_px[0],
                    int((btop - pad) * scale) - box_px[1],
                    int((bx1 + pad) * scale) + 1 - box_px[0],
                    int((bbottom + pad) * scale) + 1 - box_px[1],
                ),
            )
        sign = ""
        mark = sign_alpha.point(lambda v: 255 if v > 100 else 0).getbbox()
        if mark is not None and (mark[2] - mark[0]) * (mark[3] - mark[1]) >= 4:
            sign = f"{ASSETS}/signe-{page.number}-{u.id}.png"
            alone = crop.copy()
            alone.putalpha(sign_alpha)
            alone.save(folder / sign, "PNG", optimize=True)
        u.strip = [
            round(box_px[0] / scale, 2),
            round(box_px[1] / scale, 2),
            round(box_px[2] / scale, 2),
            round(box_px[3] / scale, 2),
            "".join(f"{c:02X}" for c in color),
            name,
            sign,
        ]
        # Les boîtes à effacer : le signe de puce d'abord (s'il y en a un), puis les mots.
        marker_box = [b for b in u._all if b not in u._boxes]  # type: ignore[attr-defined]
        for bx0, btop, bx1, bbottom in (marker_box[:1] if u.marker is not None else []) + u._boxes:  # type: ignore[attr-defined]
            # Large sur les côtés, à peine en hauteur : la ligne d'au-dessus garde ses jambages.
            pad = max(1.5, 0.12 * (bbottom - btop))
            box = (bx0 - pad, btop - 0.7, bx1 + pad, bbottom + 0.7)
            r, g, b = _ground(image, tuple(int(v * scale) for v in box))  # type: ignore[arg-type]
            u.erase.append([round(v, 2) for v in box] + [f"{r:02X}{g:02X}{b:02X}"])


def infer(
    pages: list[Page],
    structure: Structure,
    hits: dict[str, F.Hit],
    content: CVContent,
    folder: Path | None = None,
    pdf: Path | None = None,
    online: bool = True,
) -> AnchoredLayout:
    inks = Inks(online)
    snapshots = _Snapshots(pdf, folder)
    word_path = {id(w): path for path, hit in hits.items() for w in hit.words}
    page_of = structure.page_of

    # ─── Les unités : les segments qui partagent un champ ───
    segments = [line for page in pages for line in page.lines]
    parent = list(range(len(segments)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    first: dict[tuple[int, str], int] = {}
    for i, line in enumerate(segments):
        for w in line.words:
            path = word_path.get(id(w))
            if path is None:
                continue
            slot = (page_of[id(line)], path)
            if slot in first:
                parent[find(i)] = find(first[slot])
            else:
                first[slot] = i
    # Un signe de puce seul (loin de son texte) rejoint le texte à sa droite.
    for i, line in enumerate(segments):
        if all(word_path.get(id(w)) is None for w in line.words) and all(
            is_marker(w.text) for w in line.words
        ):
            right = [
                (j, other)
                for j, other in enumerate(segments)
                if other is not line
                and page_of[id(other)] == page_of[id(line)]
                and abs(other.baseline - line.baseline) < 2
                and 0 <= other.x0 - line.x1 < 4 * line.size
            ]
            if right:
                j, _ = min(right, key=lambda r: r[1].x0)
                parent[find(i)] = find(j)
    groups: dict[int, list[Line]] = {}
    for i, line in enumerate(segments):
        groups.setdefault(find(i), []).append(line)

    # Les bords du texte de chaque colonne (lignes d'une seule colonne).
    extents: dict[tuple[int, int], tuple[float, float]] = {}
    for line in segments:
        lanes = structure.lane_of(line)
        if len(lanes) != 1:
            continue
        slot = (page_of[id(line)], lanes[0])
        a, b = extents.get(slot, (line.x0, line.x1))
        extents[slot] = (min(a, line.x0), max(b, line.x1))

    # L'interligne habituel, par taille de texte.
    steps: dict[float, list[float]] = {}
    for lines in groups.values():
        ordered = sorted(lines, key=lambda line: line.baseline)
        for a, b in zip(ordered, ordered[1:], strict=False):
            if b.baseline - a.baseline > 0.5 * a.size:
                steps.setdefault(round(a.size * 2) / 2, []).append(b.baseline - a.baseline)
    leadings = {size: statistics.median(v) for size, v in steps.items()}

    units: list[Unit] = []
    for lines in groups.values():
        lines.sort(key=lambda line: (line.baseline, line.x0))
        page = page_of[id(lines[0])]
        words = [w for line in lines for w in line.words]
        top_line = lines[0]
        marker_word = (
            top_line.words[0]
            if (is_marker(top_line.words[0].text) and word_path.get(id(top_line.words[0])) is None)
            else None
        )
        body = [w for w in words if w is not marker_word]
        if not body:
            body = words
            marker_word = None
        y0 = top_line.baseline
        # Les morceaux : champ par champ, et les textes fixes entre eux.
        parts: list[Part] = []
        groups_of: list[list[Word]] = []
        previous: Word | None = None
        for w in body:
            path = word_path.get(id(w))
            space = previous is not None and not w.glued
            if path is None:
                text = (" " if space else "") + w.text
                if parts and parts[-1].path is None:
                    parts[-1].text += text
                else:
                    parts.append(Part(text=text, ink=inks.of(w)))
                    groups_of.append([w])
            elif parts and parts[-1].path == path:
                groups_of[-1].append(w)
            else:
                if space:
                    if parts and parts[-1].path is None:
                        parts[-1].text += " "
                    elif parts:
                        parts.append(Part(text=" ", ink=parts[-1].ink))
                        groups_of.append([])
                parts.append(Part(path=path))
                groups_of.append([w])
            previous = w
        for part, group in zip(parts, groups_of, strict=True):
            if part.path is None or not group:
                continue
            dominant = _dominant(group)
            part.ink = inks.of(dominant, _upper(group, F.get(content, part.path) or ""))
            part.url = next((w.url for w in group if w.url), None)
        parts = _punctuation(parts, groups_of, content)
        paths = [p.path for p in parts if p.path]
        first_path = paths[0] if paths else None
        # Les lignes exactes, mot par mot (les icônes de police deviennent des images).
        rows: list[Row] = []
        snaps: list[tuple[str, tuple[float, float, float, float]]] = []
        for line in lines:
            row = Row(y=round(line.baseline - y0, 3))
            for w in line.words:
                font_id, _ = _resolved(w.font, online)
                text = w.text
                if missing(font_id, w.bold, w.italic, text):
                    mapped = text.translate(str.maketrans(PRIVATE_BULLETS))
                    if mapped != text and not missing(font_id, w.bold, w.italic, mapped):
                        text = mapped
                    else:
                        snap = snapshots.take(page, (w.x0, w.top, w.x1, w.bottom))
                        if snap:
                            snaps.append((snap, (w.x0, w.top, w.x1, w.bottom)))
                        continue
                row.words.append(
                    Glyph(
                        t=text,
                        x=round(w.x0, 3),
                        w=round(w.w, 3),
                        i=inks.of(w),
                        dy=round(w.baseline - line.baseline, 3),
                        u=w.url,
                    )
                )
            rows.append(row)
        x_text = min(w.x0 for w in body)
        x_first = (
            min(w.x0 for w in top_line.words if w is not marker_word)
            if any(w is not marker_word for w in top_line.words)
            else x_text
        )
        right = max(w.x1 for w in body)
        lanes = sorted({n for line in lines for n in structure.lane_of(line)})
        # Le bord droit : le segment voisin à droite, sinon le bord du texte de la colonne.
        top = min(w.top for w in words)
        bottom = max(w.bottom for w in words)
        neighbours = [
            other.x0
            for other in segments
            if page_of[id(other)] == page
            and other not in lines
            and other.x0 >= right - 1
            and other.bottom > top + 1
            and other.top < bottom - 1
        ]
        lane_right = max((extents.get((page, n), (0, right))[1] for n in lanes), default=right)
        size = max(w.size for w in body)
        # Jusqu'au milieu du blanc qui la sépare de sa voisine (l'autre moitié est à elle : une
        # date alignée à droite qui s'allonge vient vers la gauche).
        limit = min([lane_right, *[(right + x) / 2 - 0.2 * size for x in neighbours]])
        x1 = max(right, limit)
        lefts = [
            other.x1
            for other in segments
            if page_of[id(other)] == page
            and other not in lines
            and other.x1 <= x_text + 1
            and other.bottom > top + 1
            and other.top < bottom - 1
        ]
        lane_left = min((extents.get((page, n), (x_text, 0))[0] for n in lanes), default=x_text)
        # L'alignement : à droite, au centre ou à gauche de sa colonne.
        align = "left"
        lo = max([lane_left, *[(x + x_text) / 2 + 0.2 * size for x in lefts]])
        width_lane = max(lane_right - lane_left, 1)
        xs1 = [line.x1 for line in lines]
        xs0 = [
            min(w.x0 for w in line.words if w is not marker_word)
            for line in lines
            if any(w is not marker_word for w in line.words)
        ]
        centers = [(a + b) / 2 for a, b in zip(xs0, xs1, strict=False)]
        if all(abs(x - lane_right) < 2.5 for x in xs1) and x_text - lane_left > 0.25 * width_lane:
            align = "right"
        elif (
            all(abs(c - (lane_left + lane_right) / 2) < 3 for c in centers)
            and x_text - lane_left > 8
        ):
            align = "center"
        if align == "right":
            box0, box1 = lo, right
        elif align == "center":
            half = max((lane_right - lane_left) / 2, (right - x_text) / 2)
            middle = (x_text + right) / 2
            box0, box1 = middle - half, middle + half
        else:
            box0, box1 = x_text, x1
        ordered = [line.baseline for line in lines]
        steps_here = [
            b - a for a, b in zip(ordered, ordered[1:], strict=False) if b - a > 0.5 * size
        ]
        dominant = _dominant(body)
        leading = (
            statistics.median(steps_here)
            if steps_here
            else leadings.get(round(dominant.size * 2) / 2, round(dominant.size * 1.25, 2))
        )
        # Jamais moins que la taille du texte : deux lignes qui coulent ne se recouvrent pas.
        leading = max(leading, round(1.05 * size, 2))
        ascent = max(max(w.baseline - w.top for w in top_line.words), 0.8 * size)
        marker = None
        if marker_word is not None:
            font_id, _ = _resolved(marker_word.font, online)
            text = marker_word.text
            if missing(font_id, marker_word.bold, marker_word.italic, text):
                mapped = text.translate(str.maketrans(PRIVATE_BULLETS))
                text = (
                    mapped
                    if not missing(font_id, marker_word.bold, marker_word.italic, mapped)
                    else "•"
                )
            marker = Glyph(
                t=text,
                x=round(marker_word.x0, 3),
                w=round(marker_word.w, 3),
                i=inks.of(marker_word),
            )
        role = _role(first_path, content)
        items: list[int] = []
        joiner = ", "
        if role == "list" and len({p.split(".")[0] for p in paths}) > 1:
            # Une ligne qui mêle deux rubriques : reprise telle quelle, pas comme une liste.
            role = "field"
        if role == "list":
            indexes = []
            for p in paths:
                bits = p.split(".")
                if bits[1].isdigit():
                    indexes.append(int(bits[1]))
            items = sorted(set(indexes))
            if len(items) >= 2:
                # Le texte fixe entre le premier élément et le second.
                seen_first = False
                for part in parts:
                    if part.path and int(part.path.split(".")[1]) == items[0]:
                        seen_first = True
                    elif seen_first and part.path is None:
                        joiner = part.text or ", "
                        break
                    elif seen_first and part.path and int(part.path.split(".")[1]) != items[0]:
                        break
        bits = first_path.split(".") if first_path else []
        section = (
            bits[0] if bits and bits[0] not in ("name", "headline", "summary", "contact") else None
        )
        item = int(bits[1]) if len(bits) >= 2 and bits[1].isdigit() and section else None
        bullet = int(bits[3]) if len(bits) >= 4 and bits[2] == "bullets" else None
        unit = Unit(
            id=len(units),
            page=page,
            y=round(y0, 3),
            end=round(lines[-1].baseline - y0, 3),
            x0=round(box0, 3),
            x1=round(max(box1, box0 + 10), 3),
            indent=round(x_first - x_text, 3) if align == "left" else 0.0,
            align=align,
            leading=round(leading, 3),
            ascent=round(ascent, 3),
            rows=rows,
            parts=parts,
            marker=marker,
            original={p: F.get(content, p) or "" for p in paths},
            lanes=lanes,
            role=role,
            section=section,
            item=item,
            bullet=bullet,
            items=items,
            joiner=joiner,
            mark=_mark(first_path, content),
        )
        unit._snaps = snaps  # type: ignore[attr-defined]
        # Un scan : les boîtes des mots (sans le signe de puce, qui reste dans l'image), et
        # toutes, signe compris (les bords de sa bande d'image).
        unit._boxes = [(w.x0, w.top, w.x1, w.bottom) for w in words if w is not marker_word]  # type: ignore[attr-defined]
        unit._all = [(w.x0, w.top, w.x1, w.bottom) for w in words]  # type: ignore[attr-defined]
        units.append(unit)

    # ─── Les écarts : depuis l'unité précédente de la même colonne ───
    for page in pages:
        mine = sorted((u for u in units if u.page == page.number), key=lambda u: (u.y, u.x0))
        for u in mine:
            before = [
                o
                for o in mine
                if o is not u and set(o.lanes) & set(u.lanes) and o.y + o.end < u.y - 0.5
            ]
            if before:
                prev = max(before, key=lambda o: o.y + o.end)
                u.gap = round(u.y - (prev.y + prev.end), 3)
            else:
                u.gap = round(u.y, 3)

    for page in pages:
        if page.background is not None and folder is not None:
            _erasers(page, units, structure, folder)
    layout = AnchoredLayout(
        pages=[
            PageSize(width=p.width, height=p.height, background=_background(p, folder))
            for p in pages
        ],
        lanes=[[(round(a, 2), round(b, 2)) for a, b in lanes] for lanes in structure.lanes],
        snapshot={path: text for path, text, _ in F.paths(content)},
    )

    # ─── Formes, images, liens : fixes, ou attachés à une unité ───
    def attach(page: int, box: tuple[float, float, float, float]) -> tuple[int | None, bool]:
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        size = pages[page - 1]
        if w * h > 0.05 * size.width * size.height or (h > 60 and w > 0.4 * size.width):
            return None, False
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        lanes = set(lanes_of(structure.lanes[page - 1], x0, x1))
        mine = [u for u in units if u.page == page and set(u.lanes) & lanes]
        inside = [u for u in mine if u.y - u.ascent - 2 <= cy <= u.y + u.end + 0.35 * u.ascent + 2]
        unit = None
        if inside:
            unit = min(
                inside,
                key=lambda u: (
                    0 if u.x0 - 20 <= cx <= u.x1 + 20 else min(abs(cx - u.x0), abs(cx - u.x1))
                ),
            )
        else:
            above = [
                u
                for u in mine
                if 0 <= y0 - (u.y + u.end) <= 16 and x0 < u.x1 + 4 and x1 > u.x0 - 20
            ]
            if above:
                unit = max(above, key=lambda u: u.y + u.end)
        if unit is None:
            return None, False
        text = [g for row in unit.rows for g in row.words]
        if not text:
            return unit.id, False
        tx0, tx1 = min(g.x for g in text), max(g.x + g.w for g in text)
        thin = h <= 3.5 and w > 15
        wraps = x0 <= tx0 + 1 and x1 >= tx1 - 1
        exact = not thin and not wraps and x0 >= tx0 - 1 and x1 <= tx1 + 1
        return unit.id, exact

    for page in pages:
        if page.background is not None:
            continue  # un scan : ses formes sont dans l'image de fond
        for s in page.shapes:
            unit, exact = attach(page.number, s.box)
            layout.paints.append(
                Paint(
                    page=page.number,
                    kind=s.kind if s.kind in ("rect", "ellipse", "line", "path") else "path",
                    box=tuple(round(v, 3) for v in s.box),  # type: ignore[arg-type]
                    fill=s.fill,
                    stroke=s.stroke,
                    width=round(s.width, 3),
                    radius=round(s.radius, 3),
                    path=s.path,
                    even_odd=s.even_odd,
                    shade=list(s.shade) if s.shade else None,
                    unit=unit,
                    exact=exact,
                )
            )
    # La photo : la plus grande image à peu près carrée de la première page.
    candidates = (
        [p for p in pages[0].pictures if min(p.w, p.h) >= 40 and 0.6 <= p.w / max(p.h, 1) <= 1.7]
        if pages
        else []
    )
    photo_pic = max(candidates, key=lambda p: p.w * p.h, default=None)
    if photo_pic is not None:
        layout.photo = Photo(
            page=1,
            box=tuple(round(v, 3) for v in photo_pic.box),
            shape=photo_pic.shape,  # type: ignore[arg-type]
        )
    count = 0
    for page in pages:
        for pic in page.pictures:
            if pic is photo_pic or not pic.data or folder is None:
                continue
            count += 1
            name = f"{ASSETS}/image-{count}.{pic.ext}"
            (folder / ASSETS).mkdir(exist_ok=True)
            (folder / name).write_bytes(pic.data)
            unit, exact = attach(page.number, pic.box)
            layout.pictures.append(
                Picture(
                    page=page.number,
                    box=tuple(round(v, 3) for v in pic.box),  # type: ignore[arg-type]
                    file=name,
                    shape=pic.shape,  # type: ignore[arg-type]
                    unit=unit,
                    exact=exact,
                )
            )
    for u in units:
        for snap, box in getattr(u, "_snaps", []):
            layout.pictures.append(Picture(page=u.page, box=box, file=snap, unit=u.id))
    for page in pages:
        for x0, y0, x1, y1, url in page.links:
            covered = any(
                w.url == url
                and x0 <= (w.x0 + w.x1) / 2 <= x1
                and y0 <= (w.top + w.bottom) / 2 <= y1
                for w in page.words()
            )
            if covered:
                continue
            unit, _ = attach(page.number, (x0, y0, x1, y1))
            layout.links.append(
                Link(
                    page=page.number,
                    box=(round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)),
                    url=url,
                    unit=unit,
                )
            )

    # ─── Les rubriques et l'en-tête : leurs unités ───
    for s in content.sections:
        plan = SectionPlan(items=[ItemPlan() for _ in s.items])
        for u in units:
            for path in u.original:
                bits = path.split(".")
                if bits[0] != s.id:
                    continue
                if bits[1] == "title":
                    plan.title = u.id
                    continue
                n = int(bits[1])
                if n >= len(plan.items):
                    continue
                target = plan.items[n]
                if len(bits) >= 4 and bits[2] == "bullets":
                    if u.id not in target.bullets:
                        target.bullets.append(u.id)
                elif u.id not in target.units:
                    target.units.append(u.id)
        for target in plan.items:
            target.units.sort(key=lambda i: (units[i].page, units[i].y, units[i].x0))
            target.bullets.sort(key=lambda i: (units[i].page, units[i].y))
        layout.sections[s.id] = plan
    for u in units:
        for path in u.original:
            bits = path.split(".")
            if bits[0] in ("name", "headline", "summary"):
                layout.header.setdefault(bits[0], u.id)
            elif bits[0] == "contact":
                layout.header["contact"] = max(layout.header.get("contact", -1), u.id)

    layout.units = units
    layout.inks = inks.items
    layout.fonts = inks.fonts
    # Le style courant et celui des titres : pour ce qui n'était pas sur la page.
    body_count: Counter = Counter()
    for u in units:
        for part in u.parts:
            if part.path:
                body_count[part.ink] += len(u.original.get(part.path, ""))
    layout.body = body_count.most_common(1)[0][0] if body_count else 0
    title_units = [u for u in units if u.role == "title"]
    if title_units:
        layout.title_ink = Counter(u.parts[0].ink for u in title_units if u.parts).most_common(1)[
            0
        ][0]
    return layout
