"""La mise en page d'un CV, tirée de son PDF et de son contenu lu (sans IA).

On retrouve chaque champ du contenu (nom, titres, intitulés, dates, puces…) parmi les
morceaux de texte de la page ; leurs places donnent les colonnes et les écarts, leurs
styles donnent les encres ; les formes proches des titres et des puces deviennent leurs
décors, les autres restent des formes fixes de la page.
"""

import re
import statistics
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

from PIL import ImageFont

from app import fonts as app_fonts
from app.models.content import CVContent
from app.services.clone import fonts as clone_fonts
from app.services.clone.model import (
    Block,
    Bullet,
    Chip,
    CloneLayout,
    Deco,
    Frame,
    Ink,
    Look,
    Paint,
    Photo,
    Row,
)
from app.services.clone.page import Page, Run, Shape


def key(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", plain)


# ─── Retrouver un texte sur la page ──────────────────────────────────────────


@dataclass
class Hit:
    runs: list[Run]
    # Une partie d'un seul morceau : début et fin, en fraction de sa largeur.
    part: tuple[float, float] | None = None

    @property
    def x0(self) -> float:
        if self.part:
            return self.runs[0].x + self.runs[0].w * self.part[0]
        return min(r.x for r in self.runs)

    @property
    def x1(self) -> float:
        if self.part:
            return self.runs[0].x + self.runs[0].w * self.part[1]
        return max(r.right for r in self.runs)

    @property
    def top(self) -> float:
        return min(r.y for r in self.runs)

    @property
    def bottom(self) -> float:
        return max(r.bottom for r in self.runs)

    @property
    def main(self) -> Run:
        return max(self.runs, key=lambda r: len(r.text))


class Matcher:
    def __init__(self, runs: list[Run]) -> None:
        self.runs = sorted(runs, key=lambda r: (round(r.y), r.x))
        self.keys = [key(r.text) for r in self.runs]
        self.used: set[int] = set()

    def find(
        self,
        text: str,
        exact_only: bool = False,
        region: tuple[float, float, float, float] | None = None,
        near: tuple[float, float] | None = None,
    ) -> Hit | None:
        """Le texte sur la page. Parmi plusieurs candidats : dans ``region`` (x0, y0, x1, y1)
        d'abord, puis le plus proche de ``near``, l'égalité exacte avant les morceaux."""
        k = key(text)
        if not k:
            return None
        found = self._candidates(k, exact_only, region, near)
        if not found and region is not None:
            found = self._candidates(k, exact_only, None, near)
        if not found:
            return None
        _, hit, used = min(found, key=lambda c: c[0])
        self.used.update(used)
        return hit

    def _candidates(self, k, exact_only, region, near) -> list[tuple[float, Hit, list[int]]]:
        def inside(hit: Hit) -> bool:
            if region is None:
                return True
            x0, y0, x1, y1 = region
            return y0 - 2 <= hit.top < y1 and x0 - 4 <= hit.x0 <= x1

        def distance(hit: Hit) -> float:
            if near is None:
                return hit.top / 1000
            return abs(hit.top - near[1]) + 0.3 * abs(hit.x0 - near[0])

        out: list[tuple[float, Hit, list[int]]] = []
        for i, rk in enumerate(self.keys):
            if i not in self.used and rk == k:
                hit = Hit([self.runs[i]])
                if inside(hit):
                    out.append((distance(hit), hit, [i]))
        if exact_only:
            return out
        for sequence in self._sequences(k):
            hit = Hit([self.runs[i] for i in sequence])
            if inside(hit):
                out.append((distance(hit) + 5, hit, sequence))
        for i, rk in enumerate(self.keys):
            start = rk.find(k)
            if start >= 0 and len(k) >= 2 and len(k) < len(rk):
                hit = Hit([self.runs[i]], (start / len(rk), (start + len(k)) / len(rk)))
                if inside(hit):
                    out.append((distance(hit) + 15, hit, []))
        return out

    def _sequences(self, k: str):
        """Des morceaux qui, à la suite (lignes coupées), forment ``k``."""
        for i, rk in enumerate(self.keys):
            if i in self.used or len(rk) < 2 or not k.startswith(rk) or len(rk) == len(k):
                continue
            pos, chosen, last = len(rk), [i], self.runs[i]
            for j in range(i + 1, min(i + 80, len(self.runs))):
                run, rj = self.runs[j], self.keys[j]
                if j in self.used or not rj or not k.startswith(rj, pos):
                    continue
                same_line = abs(run.bottom - last.bottom) < 2.5 and run.x >= last.x
                next_line = (
                    0 < run.y - last.y < 2.6 * max(last.h, 4) and abs(run.x - self.runs[i].x) < 40
                )
                if not (same_line or next_line):
                    continue
                chosen.append(j)
                pos += len(rj)
                last = run
                if pos == len(k):
                    yield chosen
                    break

    def leftovers(self) -> list[Run]:
        return [r for i, r in enumerate(self.runs) if i not in self.used and self.keys[i]]


# ─── Encres ──────────────────────────────────────────────────────────────────


@lru_cache(maxsize=64)
def _resolved(family: str, online: bool) -> tuple[str, str]:
    return clone_fonts.resolve(family, online)


@lru_cache(maxsize=256)
def _face(font_id: str, style: str) -> ImageFont.FreeTypeFont | None:
    try:
        return ImageFont.truetype(str(app_fonts.get(font_id).file(style)), 100)
    except (OSError, app_fonts.UnknownFont):
        return None


def _style(bold: bool, italic: bool) -> str:
    return {(False, False): "regular", (True, False): "bold", (False, True): "italic"}.get(
        (bold, italic), "bold_italic"
    )


def ink_of(hit: Hit, content_text: str = "", online: bool = True, ratio: float = 1.2) -> Ink:
    # Le style du texte courant, pas celui des mots mis en **gras** dans le contenu.
    marked = [key(m) for m in re.findall(r"\*\*(.+?)\*\*|__(.+?)__", content_text) for m in m if m]
    plain = [r for r in hit.runs if not any(key(r.text) and key(r.text) in mk for mk in marked)]
    run = max(plain, key=lambda r: len(r.text)) if plain and marked else hit.main
    content_text = re.sub(r"\*\*|__", "", content_text)
    font_id, _ = _resolved(run.font, online)
    size, tracking = run.size, 0.0
    text = run.text.strip()
    # Lettres espacées : pdftohtml les sépare (« C H E F F E ») ; le contenu dit le vrai texte.
    if content_text and key(content_text) == key(text) and len(text) > len(content_text) + 2:
        text = content_text.upper() if text.isupper() else content_text
    face = _face(font_id, _style(run.bold, run.italic))
    if face is not None and len(text) >= 4 and not hit.part:
        natural = face.getlength(text) / 100
        expected = run.h / HEIGHT.get(run.font, 1.4)
        if natural > 0:
            guess = run.w / natural
            if abs(guess - expected) / expected <= 0.1:
                size = guess
            elif len(text) > 1:
                size = expected
                tracking = (run.w - natural * size) / (len(text) - 1) / size * 100
    lines = sorted({round(r.y, 1) for r in hit.runs})
    steps = [b - a for a, b in zip(lines, lines[1:], strict=False) if b - a > 0.5]
    leading = statistics.median(steps) if steps else size * ratio
    upper = text.isupper() and bool(re.search(r"[a-zà-ÿ]", content_text))
    small = 0.0
    if run.small and upper:
        # Petites capitales : la grande lettre à la taille estimée, les petites au même rapport.
        size = run.h / HEIGHT.get(run.font, 1.4)
        small = round(size * run.small / run.size, 2)
        tracking = 0.0
    return Ink(
        small=small,
        font=font_id,
        size=round(size, 2),
        leading=round(leading, 2),
        color=run.color,
        bold=run.bold,
        italic=run.italic,
        upper=upper,
        tracking=round(max(min(tracking, 60), -10), 1) if abs(tracking) > 1.5 else 0.0,
    )


# Hauteur d'une ligne de pdftohtml / taille, par police (calculée dans ``infer``).
HEIGHT: dict[str, float] = {}


def _heights(runs: list[Run], online: bool) -> None:
    """Pour chaque police, le rapport hauteur / taille, mesuré sur des lignes ordinaires."""
    ratios: dict[str, list[float]] = {}
    for run in runs:
        text = run.text.strip()
        if len(text) < 8 or text.isupper() or "  " in text:
            continue
        font_id, _ = _resolved(run.font, online)
        face = _face(font_id, _style(run.bold, run.italic))
        if face is None:
            continue
        natural = face.getlength(text) / 100
        if natural > 0:
            ratios.setdefault(run.font, []).append(run.h / (run.w / natural))
    HEIGHT.clear()
    HEIGHT.update({font: statistics.median(values) for font, values in ratios.items()})


def _same_ink(a: Run, b: Run) -> bool:
    return (
        a.font == b.font and abs(a.size - b.size) < 0.2 and a.color == b.color and a.bold == b.bold
    )


# ─── Les champs du contenu sur la page ───────────────────────────────────────


@dataclass
class Found:
    """Ce qui a été retrouvé d'une rubrique : son titre et, par entrée, ses champs."""

    title: Hit | None
    items: list[dict[str, Hit | list[Hit]]] = field(default_factory=list)

    def hits(self) -> list[Hit]:
        out: list[Hit] = []
        for item in self.items:
            for value in item.values():
                out += value if isinstance(value, list) else [value]
        return out


def _fields(section) -> list[dict[str, str | list[str]]]:
    kind = section.kind
    out: list[dict[str, str | list[str]]] = []
    for it in section.items:
        if kind == "experience":
            out.append(
                {
                    "title": it.title,
                    "tag": it.tag,
                    "place": it.place,
                    "dates": it.dates,
                    "bullets": it.bullets,
                }
            )
        elif kind == "education":
            out.append(
                {
                    "title": it.title,
                    "place": it.place,
                    "dates": it.dates,
                    "description": it.description,
                }
            )
        elif kind == "projects":
            out.append(
                {"title": it.title, "tag": it.tag, "dates": it.date, "description": it.description}
            )
        elif kind == "skills":
            out.append({"label": it.label, "text": it.text})
        elif kind == "languages":
            out.append({"label": it.name, "text": it.level})
        elif kind == "grid":
            out.append({"text": it.text})
        else:
            out.append({"text": it})
    return out


def _strip_marks(text: str) -> str:
    return text.replace("**", "").replace("__", "")


def locate(
    page: Page, content: CVContent
) -> tuple[Matcher, dict[str, Hit], dict[str, Found], list[Hit | None]]:
    m = Matcher(page.runs)
    header: dict[str, Hit] = {}
    found: dict[str, Found] = {}
    sections = [s for s in content.sections if s.visible]
    # Les titres d'abord (texte exact), puis le nom et le titre du CV.
    for s in sections:
        found[s.id] = Found(title=m.find(s.title, exact_only=True))
    # La bande de chaque rubrique : de son titre au titre suivant de la même colonne.
    titles = [(sid, f.title) for sid, f in found.items() if f.title]
    bands: dict[str, tuple[float, float, float, float]] = {}
    for sid, t in titles:
        below = [
            o.top
            for other, o in titles
            if other != sid and o.top > t.top + 2 and o.x0 < t.x1 + 40 and o.x1 > t.x0 - 40
        ]
        bands[sid] = (t.x0 - 12, t.top, page.width, min(below, default=page.height))
    name = m.find(content.header.name)
    if name:
        header["name"] = name
    anchor = (name.x0, name.bottom) if name else None
    headline = m.find(content.header.headline, near=anchor)
    if headline:
        header["headline"] = headline
        anchor = (headline.x0, headline.bottom)
    # Les textes longs avant les courts : une date ne doit pas prendre un morceau de puce.
    jobs: list[tuple[int, str, int, str, str | None]] = []
    for s in sections:
        for n, item in enumerate(_fields(s)):
            found[s.id].items.append({})
            for name, value in item.items():
                values = value if isinstance(value, list) else [value]
                for v in values:
                    if v and v.strip():
                        jobs.append((len(v), s.id, n, name, _strip_marks(v)))
    if content.header.summary.strip():
        jobs.append(
            (len(content.header.summary), "", -1, "summary", _strip_marks(content.header.summary))
        )
    for _, sid, n, field_name, text in sorted(jobs, key=lambda j: -j[0]):
        hit = m.find(text, region=bands.get(sid), near=anchor if sid == "" else None)
        if hit is None:
            continue
        if sid == "":
            header[field_name] = hit
            continue
        slot = found[sid].items[n]
        if field_name in ("bullets",):
            slot.setdefault(field_name, [])
            slot[field_name].append(hit)  # type: ignore[union-attr]
        else:
            slot[field_name] = hit
    contacts: list[Hit | None] = []
    for line in content.header.contact_lines:
        for item in line:
            contacts.append(m.find(item.text, near=anchor))
    return m, header, found, contacts


# ─── La mise en page ─────────────────────────────────────────────────────────


def _cluster(values: list[float], tolerance: float) -> list[list[float]]:
    groups: list[list[float]] = []
    for v in sorted(values):
        if groups and v - groups[-1][-1] <= tolerance:
            groups[-1].append(v)
        else:
            groups.append([v])
    return groups


def _box(hits: list[Hit]) -> tuple[float, float, float, float]:
    return (
        min(h.x0 for h in hits),
        min(h.top for h in hits),
        max(h.x1 for h in hits),
        max(h.bottom for h in hits),
    )


def _align(
    x0: float, x1: float, fx0: float, fx1: float, default: str | None = "left"
) -> str | None:
    if abs(x0 - fx0) <= 6 or (default == "left" and x0 < fx0):
        return "left"
    if abs((x0 + x1) / 2 - (fx0 + fx1) / 2) <= 6:
        return "center"
    if abs(x1 - fx1) <= 6:
        return "right"
    return default


def _title_deco(
    title: Hit, shapes: list[Shape], frame_x0: float, frame_x1: float, taken: set[int]
) -> Deco:
    for i, s in enumerate(shapes):
        if i in taken:
            continue
        overlaps = s.box[0] < title.x1 and s.box[2] > title.x0
        thin = s.h <= 3.5 and s.w > 15
        # Un filet sous le titre (ou une bordure basse).
        if thin and overlaps and title.bottom - 3 <= s.box[1] <= title.bottom + 14:
            taken.add(i)
            width = s.w if abs(s.box[2] - frame_x1) > 6 else None
            align = (
                "center"
                if width and abs((s.box[0] + s.box[2]) / 2 - (frame_x0 + frame_x1) / 2) < 6
                else "left"
            )
            return Deco(
                kind="rule",
                color=s.stroke or s.fill or "000000",
                thickness=max(s.width, s.h, 0.3),
                gap=round(s.box[1] - title.bottom, 2),
                width=width,
                align=align,
            )
        # Un bandeau derrière le titre.
        if (
            s.fill
            and s.box[0] <= title.x0 + 1
            and s.box[2] >= title.x1 - 1
            and s.box[1] <= title.top + 1
            and s.box[3] >= title.bottom - 1
            and s.h < 40
        ):
            taken.add(i)
            baseline = title.top + title.main.h * 0.8
            return Deco(
                kind="band",
                color=s.fill,
                gap=round(title.x0 - s.box[0], 2),
                pad_y=round(max(title.top - s.box[1], 0.5), 2),
                width=round(s.w, 2),
                radius=s.radius,
                height=round(s.h, 2),
                above=round(baseline - s.box[1], 2),
                offset=round(s.box[0] - frame_x0, 2),
            )
    return Deco()


def _bullet(
    hits: list[Hit], shapes: list[Shape], frame_x0: float, taken: set[int], ink: Ink
) -> Bullet:
    if not hits:
        return Bullet()
    first = min(hits[0].runs, key=lambda r: (r.y, r.x))
    for i, s in enumerate(shapes):
        if i in taken:
            continue
        cx, cy = (s.box[0] + s.box[2]) / 2, (s.box[1] + s.box[3]) / 2
        if (
            s.w <= 7
            and s.h <= 7
            and 0 < first.x - cx < 18
            and first.y - 1 <= cy <= first.bottom + 1
        ):
            # Toutes les pastilles de cette forme sont des puces.
            for j, t in enumerate(shapes):
                if abs(t.w - s.w) < 0.3 and abs(t.h - s.h) < 0.3 and abs(t.box[0] - s.box[0]) < 0.5:
                    taken.add(j)
            baseline = first.y + first.h * 0.8
            return Bullet(
                kind="dot",
                size=round(s.w, 2),
                color=s.fill or s.stroke or "000000",
                indent=round(first.x - frame_x0, 2),
                offset=round(first.x - cx, 2),
                raise_=round(baseline - cy, 2),
            )
    glyph = re.match(r"^\s*([•·▪■◦●‣–—-])\s*", first.text)
    if glyph:
        return Bullet(
            kind="char",
            char=glyph.group(1),
            color=first.color,
            indent=round(first.x - frame_x0 + ink.size * 0.8, 2),
            offset=round(ink.size * 0.8, 2),
        )
    return Bullet(indent=round(first.x - frame_x0, 2))


def _between(a: Hit, b: Hit, runs: list[Run]) -> str | None:
    """Le texte qui sépare deux champs d'une même ligne (« · », « | », « — »), s'il y en a un."""
    if a.runs[0] is b.runs[0] and a.part and b.part:
        run = a.runs[0]
        return run.text[round(a.part[1] * len(run.text)) : round(b.part[0] * len(run.text))] or None
    marks = [
        r for r in runs if not key(r.text) and abs(r.y - a.top) < 4 and a.x1 - 2 <= r.x <= b.x0 + 2
    ]
    if marks:
        return " " + " ".join(r.text.strip() for r in sorted(marks, key=lambda r: r.x)) + " "
    return None


def _rows(item: dict, frame_x1: float, runs: list[Run] | None = None) -> list[Row]:
    fields = [
        (name, item[name])
        for name in ("title", "tag", "place", "dates", "description")
        if name in item and isinstance(item[name], Hit)
    ]
    fields = [(n, h) for n, h in fields if n != "description"]
    lines: list[list[tuple[str, Hit]]] = []
    for name, hit in sorted(fields, key=lambda f: (f[1].top, f[1].x0)):
        if lines and abs(lines[-1][0][1].top - hit.top) < 3:
            lines[-1].append((name, hit))
        else:
            lines.append([(name, hit)])
    rows = []
    for line in lines:
        row = Row()
        lefts: list[Hit] = []
        for name, hit in sorted(line, key=lambda f: f[1].x0):
            if abs(hit.x1 - frame_x1) <= 8 and hit.x0 > line[0][1].x0 + 5:
                row.right.append(name)
            else:
                row.left.append(name)
                lefts.append(hit)
        if len(lefts) > 1 and runs is not None:
            sep = _between(lefts[0], lefts[1], runs)
            row.sep = sep if sep is not None else " "
        rows.append(row)
    return rows


def infer(page: Page, content: CVContent, online: bool = True) -> CloneLayout:
    _heights(page.runs, online)
    m, header, found, contacts = locate(page, content)
    shapes = list(page.shapes)
    taken: set[int] = set()

    # L'interligne habituel du document (hauteur de ligne / taille).
    ratios = []
    for f in found.values():
        for h in f.hits():
            ys = sorted({round(r.y, 1) for r in h.runs})
            if len(ys) > 1:
                ratios.append((ys[1] - ys[0]) / h.main.size)
    ratio = statistics.median(ratios) if ratios else 1.25

    # Les colonnes : là où commence le contenu des rubriques.
    content_boxes = {sid: _box(f.hits()) for sid, f in found.items() if f.hits()}
    starts = [b[0] for b in content_boxes.values()]
    columns = []
    for group in _cluster(starts, 14):
        members = [
            sid for sid, b in content_boxes.items() if min(group) - 0.5 <= b[0] <= max(group) + 0.5
        ]
        x0 = min(content_boxes[s][0] for s in members)
        x1 = max(content_boxes[s][2] for s in members)
        columns.append({"x0": x0, "x1": x1, "members": members})
    columns.sort(key=lambda c: c["x0"])
    # Une colonne s'arrête avant la suivante ; ses filets de titre disent sa vraie largeur.
    for sid, f in found.items():
        if f.title is None:
            continue
        for col in columns:
            if sid in col["members"]:
                for s in shapes:
                    if (
                        s.h <= 3.5
                        and s.box[0] <= f.title.x0 + 2
                        and f.title.bottom - 3 <= s.box[1] <= f.title.bottom + 14
                    ):
                        col["x1"] = max(col["x1"], s.box[2])

    frames: list[Frame] = []
    elements: dict[int, list[tuple[float, Block, tuple[float, float, float, float]]]] = {}
    top_items: list[tuple[float, Block, tuple[float, float, float, float]]] = []

    def place(block: Block, box: tuple[float, float, float, float]) -> None:
        # Dans une colonne seulement s'il y tient et s'y aligne (à gauche, au centre, à droite).
        for n, col in enumerate(columns):
            align = _align(box[0], box[2], col["x0"], col["x1"], None)
            if box[0] >= col["x0"] - 8 and box[2] <= col["x1"] + 8 and align:
                block.align = align  # type: ignore[assignment]
                elements.setdefault(n, []).append((box[1], block, box))
                return
        top_items.append((box[1], block, box))

    # Le titre du CV sur la ligne des coordonnées (« Cheffe de projet — Nantes — 06… ») :
    # il ouvre cette ligne au lieu d'avoir sa propre ligne.
    joined = False
    head = header.get("headline")
    if (
        head is not None
        and head.part
        and any(c is not None and c.runs[0] is head.runs[0] for c in contacts)
    ):
        joined = True
    for name in ("name", "headline", "summary"):
        hit = header.get(name)
        if name == "headline" and joined:
            continue
        if hit:
            place(
                Block(kind=name, ink=ink_of(hit, getattr(content.header, name), online, ratio)),
                (hit.x0, hit.top, hit.x1, hit.bottom),
            )
    located = [(i, h) for i, h in enumerate(contacts) if h]
    if located:
        lines: list[list[int]] = []
        last_top = None
        for i, h in sorted(located, key=lambda x: (round(x[1].top), x[1].x0)):
            if last_top is not None and abs(h.top - last_top) < 3:
                lines[-1].append(i)
            else:
                lines.append([i])
                last_top = h.top
        sep = " · "
        if any(len(line) > 1 for line in lines):
            line = next(line for line in lines if len(line) > 1)
            a, b = contacts[line[0]], contacts[line[1]]
            found_sep = _between(a, b, page.runs) if a and b else None
            if found_sep and found_sep.strip():
                sep = found_sep
        hits = [h for _, h in located]
        # Le style des coordonnées ordinaires : le gras vient de chaque élément du contenu.
        items = [it for line in content.header.contact_lines for it in line]
        plain = [
            h for i, h in located if i < len(items) and not items[i].bold and not items[i].label
        ] or hits
        block = Block(
            kind="contacts",
            ink=ink_of(plain[0], "", online, ratio),
            lines=lines,
            sep=sep,
            with_headline=joined,
        )
        if block.ink:
            block.ink.bold = False
        if joined and head is not None:
            hits.append(head)
        place(block, _box(hits))

    looks: list[Look] = []
    for s in content.sections:
        if not s.visible or s.id not in found:
            continue
        f = found[s.id]
        hits = f.hits()
        if not hits:
            continue
        col_index = next((n for n, c in enumerate(columns) if s.id in c["members"]), 0)
        col = columns[col_index]
        look = Look(id=s.id)
        if f.title:
            look.title = ink_of(f.title, s.title, online, ratio)
            first = min(hits, key=lambda h: (h.top, h.x0))
            if f.title.x1 < first.x0 - 4 and abs(f.title.top - first.top) < 8:
                look.title_mode = "gutter"
                look.gutter = round(col["x0"] - f.title.x0, 2)
            else:
                look.title_align = _align(f.title.x0, f.title.x1, col["x0"], col["x1"])  # type: ignore[assignment]
                if (
                    look.title_align == "left"
                    or abs(f.title.x0 - col["x0"]) > 6
                    and look.title_align == "left"
                ):
                    look.title_indent = round(f.title.x0 - col["x0"], 2)
            look.deco = _title_deco(f.title, shapes, col["x0"], col["x1"], taken)
            if look.title_mode == "above":
                bottom = f.title.bottom
                if look.deco.kind == "rule":
                    bottom = max(bottom, f.title.bottom + look.deco.gap + look.deco.thickness)
                look.after_title = round(max(first.top - bottom, 0), 2)
        else:
            look.title_mode = "hidden"
        # Les encres de chaque champ : le style le plus fréquent.
        by_field: dict[str, list[Hit]] = {}
        for item in f.items:
            for name, value in item.items():
                by_field.setdefault(name, []).extend(value if isinstance(value, list) else [value])
        texts: dict[str, str] = {}
        for raw in _fields(s):
            for name, value in raw.items():
                if isinstance(value, str) and value:
                    texts.setdefault(name, value)
        for name, field_hits in by_field.items():
            best = max(field_hits, key=lambda h: len(h.runs))
            look.inks[name] = ink_of(best, texts.get(name, ""), online, ratio)
        # Les entrées : leurs lignes, leurs puces, l'écart entre elles.
        items = [it for it in f.items if it]
        if s.kind in ("experience", "education", "projects") and items:
            look.rows = _rows(items[0], col["x1"], page.runs)
            bullets = [h for it in items for h in it.get("bullets", [])]  # type: ignore[union-attr]
            body = look.inks.get("bullets") or look.inks.get("description")
            if bullets and body:
                look.bullet = _bullet(bullets, shapes, col["x0"], taken, body)
        if s.kind in ("skills", "languages") and items:
            first = items[0]
            label, text = first.get("label"), first.get("text")
            if isinstance(label, Hit) and isinstance(text, Hit):
                if abs(label.top - text.top) < 3:
                    look.mode = "inline"
                    if label.runs[0] is text.runs[0] and label.part and text.part:
                        run = label.runs[0]
                        look.sep = (
                            run.text[
                                round(label.part[1] * len(run.text)) : round(
                                    text.part[0] * len(run.text)
                                )
                            ]
                            or " : "
                        )
                    else:
                        tail = label.main.text[len(label.main.text.rstrip(" :—-–·")) :]
                        head = text.main.text[
                            : len(text.main.text) - len(text.main.text.lstrip(" :—-–·"))
                        ]
                        look.sep = (tail + head) or " "
                        if not look.sep.endswith(" "):
                            look.sep += " "
                else:
                    look.mode = "stacked"
            elif isinstance(label, Hit):
                look.mode = "label"
            elif isinstance(text, Hit) or not (first.get("label")):
                # Une compétence par pastille ?
                chips = [sh for sh in shapes if sh.radius > 0 and 6 < sh.h < 24 and sh.w < 140]
                tags = [
                    r
                    for r in page.runs
                    if any(
                        sh.box[0] <= r.x
                        and r.right <= sh.box[2]
                        and sh.box[1] <= r.y + 1
                        and r.bottom <= sh.box[3] + 1
                        for sh in chips
                    )
                ]
                if chips and tags:
                    sample = chips[0]
                    look.mode = "tags"
                    inside = tags[0]
                    look.chip = Chip(
                        fill=sample.fill,
                        stroke=sample.stroke,
                        width=max(sample.width, 0.4),
                        radius=sample.radius,
                        pad_x=round(inside.x - sample.box[0], 2),
                        pad_y=round(max(inside.y - sample.box[1], 0.5), 2),
                        gap=round(
                            min(
                                (
                                    b.box[0] - a.box[2]
                                    for a, b in zip(chips, chips[1:], strict=False)
                                    if abs(a.box[1] - b.box[1]) < 2 and b.box[0] > a.box[2]
                                ),
                                default=3,
                            ),
                            2,
                        ),
                    )
                    look.inks["text"] = ink_of(Hit([inside]), "", online, ratio)
                    for k, sh in enumerate(shapes):
                        if sh in chips:
                            taken.add(k)
                else:
                    look.mode = "list"
        if s.kind == "grid":
            xs = _cluster([it["text"].x0 for it in items if isinstance(it.get("text"), Hit)], 6)
            look.columns = max(1, len(xs))
        _flow(s, look, items, page.runs)
        # L'écart entre deux entrées : du bas de l'une au haut de la suivante.
        tops = [min(h.top for h in _flat(it)) for it in items if _flat(it)]
        bottoms = [max(h.bottom for h in _flat(it)) for it in items if _flat(it)]
        gaps = [t - b for b, t in zip(bottoms, tops[1:], strict=False) if t > b - 2]
        look.item_gap = round(statistics.median(gaps), 2) if gaps else 0.0
        looks.append(look)
        box = _box(hits + ([f.title] if f.title and look.title_mode == "above" else []))
        block = Block(kind="section", ref=s.id)
        if look.title_mode == "gutter" and f.title:
            box = _box(hits)
        elements.setdefault(col_index, []).append(
            (box[1] if not f.title else min(box[1], f.title.top), block, box)
        )

    # Les libellés fixes (« CONTACT », « PROFIL ») : un texte au style des titres, sans champ.
    title_runs = [f.title.main for f in found.values() if f.title]
    for run in m.leftovers():
        if any(_same_ink(run, t) for t in title_runs) and len(key(run.text)) >= 3:
            block = Block(
                kind="label", text=run.text, ink=ink_of(Hit([run]), run.text, online, ratio)
            )
            place(block, (run.x, run.y, run.right, run.bottom))
            m.used.add(m.runs.index(run))

    # Les cadres : une colonne (ou le haut de page) = ses éléments du haut vers le bas.
    def frame(
        x0: float, x1: float, items: list[tuple[float, Block, tuple[float, float, float, float]]]
    ) -> Frame:
        items.sort(key=lambda e: e[0])
        fr = Frame(x=round(x0, 2), y=round(items[0][2][1], 2), w=round(x1 - x0, 2))
        previous = None
        for top, block, box in items:
            block.gap = round(top - previous, 2) if previous is not None else 0.0
            fr.blocks.append(block)
            previous = box[3]
        return fr

    # Le haut de page d'abord : l'ordre de lecture du PDF suit l'ordre des cadres.
    if top_items:
        x0 = min(b[2][0] for b in top_items)
        x1 = max(b[2][2] for b in top_items)
        for _, block, box in top_items:
            block.align = _align(box[0], box[2], x0, x1)  # type: ignore[assignment]
        frames.append(frame(x0, x1, top_items))
    for n, col in enumerate(columns):
        if n in elements:
            frames.append(frame(col["x0"], col["x1"], elements[n]))
    _keep_everything(content, frames, looks, header, contacts, page)

    paints = [
        Paint(
            kind="line" if s.kind == "line" else "ellipse" if s.kind == "ellipse" else "rect",
            x0=round(s.box[0], 2),
            y0=round(s.box[1], 2),
            x1=round(s.box[2], 2),
            y1=round(s.box[3], 2),
            fill=s.fill,
            stroke=s.stroke,
            width=round(s.width, 2),
            radius=round(s.radius, 2),
        )
        for i, s in enumerate(shapes)
        if i not in taken and s.kind != "path"
    ]
    photo = None
    if page.pictures:
        pic = max(page.pictures, key=lambda p: (p.box[2] - p.box[0]) * (p.box[3] - p.box[1]))
        photo = Photo(
            x=pic.box[0],
            y=pic.box[1],
            w=pic.box[2] - pic.box[0],
            h=pic.box[3] - pic.box[1],
            shape=pic.shape,
        )  # type: ignore[arg-type]
    used_fonts = {r.font: _resolved(r.font, online) for r in page.runs}
    return CloneLayout(
        width=page.width,
        height=page.height,
        paints=paints,
        photo=photo,
        frames=frames,
        looks=looks,
        fonts=used_fonts,
    )


def _keep_everything(
    content: CVContent,
    frames: list[Frame],
    looks: list[Look],
    header: dict[str, Hit],
    contacts: list[Hit | None],
    page: Page,
) -> None:
    """Rien du contenu ne doit manquer : ce qui n'a pas été retrouvé sur la page va dans la
    colonne la plus large, avec le style des rubriques de même sorte."""
    if not frames:
        frames.append(Frame(x=40, y=40, w=page.width - 80))
    main = max(frames, key=lambda f: f.w)
    placed = {b.ref for f in frames for b in f.blocks if b.kind == "section"}
    kinds = {b.kind for f in frames for b in f.blocks}
    body = next((ink for look in looks for ink in look.inks.values()), None)
    for name in ("name", "headline", "summary"):
        if getattr(content.header, name).strip() and name not in kinds and name not in header:
            source = (
                next((look.title for look in looks if look.title), body) if name == "name" else body
            )
            main.blocks.insert(0, Block(kind=name, gap=4, ink=source))
    if (
        any(it.text.strip() for line in content.header.contact_lines for it in line)
        and "contacts" not in kinds
    ):
        main.blocks.insert(0, Block(kind="contacts", gap=4, ink=body))
    for section in content.sections:
        if not section.visible or section.id in placed:
            continue
        model = next(
            (look for look in looks if _kind_of(content, look.id) == section.kind),
            looks[0] if looks else None,
        )
        look = (
            model.model_copy(deep=True, update={"id": section.id}) if model else Look(id=section.id)
        )
        if look.title is None:
            look.title = body
            look.title_mode = "above"
        looks.append(look)
        main.blocks.append(Block(kind="section", ref=section.id, gap=10))


def _kind_of(content: CVContent, section_id: str) -> str | None:
    return next((s.kind for s in content.sections if s.id == section_id), None)


def _flow(section, look: Look, items: list[dict], runs: list[Run]) -> None:
    """Plusieurs éléments sur la même ligne : un seul paragraphe, et ses séparateurs."""
    if section.kind not in ("skills", "languages", "bullets", "grid") or len(items) < 2:
        return
    firsts = [min(_flat(it), key=lambda h: (h.top, h.x0)) for it in items if _flat(it)]
    if len(firsts) < 2 or abs(firsts[0].top - firsts[1].top) > 3:
        return
    line = " ".join(
        r.text for r in sorted((r for r in runs if abs(r.y - firsts[0].top) < 3), key=lambda r: r.x)
    )
    raw = _fields(section)
    label0 = (raw[0].get("label") or raw[0].get("text") or "").strip()
    text0 = (raw[0].get("text") or "").strip() if raw[0].get("label") else ""
    label1 = (raw[1].get("label") or raw[1].get("text") or "").strip()
    low = line.lower()
    a = low.find(label0.lower())
    b = low.find(label1.lower(), a + len(label0)) if a >= 0 else -1
    if a < 0 or b < 0:
        return
    look.mode = "flow"
    look.columns = 1
    look.bullet = Bullet()
    if text0:
        t = low.find(text0.lower(), a + len(label0))
        if 0 <= t < b:
            look.sep = line[a + len(label0) : t]
            between = line[t + len(text0) : b]
            look.suffix = ")" if "(" in look.sep and between.startswith(")") else ""
            look.joiner = between[len(look.suffix) :] or ", "
            return
    look.joiner = line[a + len(label0) : b] or ", "


def _flat(item: dict) -> list[Hit]:
    out: list[Hit] = []
    for value in item.values():
        out += value if isinstance(value, list) else [value]
    return out
