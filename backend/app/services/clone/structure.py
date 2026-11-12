"""La structure d'un CV, tirée de sa page et non de l'IA : colonnes, titres, rubriques.

- Les colonnes : les couloirs verticaux que presque aucune ligne ne traverse.
- Les titres de rubrique (la règle d'OpenResume) : une ligne seule dans sa colonne, courte,
  d'un style que partagent d'autres lignes de même rôle et qui tranche sur le texte
  courant (gras, capitales, plus grand, en couleur), souvent avec un filet ou un bandeau.
- Chaque ligne appartient au titre le plus proche au-dessus d'elle, dans sa colonne ;
  ce qui précède tout titre est l'en-tête.

L'IA reçoit ce texte déjà rangé par rubrique : elle nomme et découpe, rien ne s'y perd.
"""

import re
import statistics
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from app.services.clone.reading import Line, Page, Shape

# Les mots des titres de rubrique, en français et en anglais (sans accents ni espaces).
VOCABULARY = (
    "profil", "profile", "resume", "summary", "apropos", "aboutme", "objectif", "objective",
    "experience", "parcours", "emploi", "employment", "stage", "internship", "career",
    "formation", "education", "etude", "diplome", "cursus", "scolarite", "academic",
    "competence", "skill", "technique", "outil", "tools", "informatique", "logiciel",
    "langue", "language", "interet", "interest", "loisir", "hobbies", "hobby", "passion",
    "projet", "project", "realisation", "achievement", "certification", "certificat",
    "publication", "prix", "award", "distinction", "honor", "reference", "contact",
    "coordonnee", "benevolat", "volunteer", "engagement", "associati", "activite",
    "activities", "savoiretre", "softskill", "qualite", "atout", "enseignement", "cours",
    "course", "module", "recherche", "research", "conference", "teaching", "permis",
    "divers", "autres", "additional", "extra", "expertise", "domaine",
    "these", "thesis", "memoire", "stack",
)  # fmt: skip

BULLETS = "•·▪■□◦●○‣–—-➢➤►▸▹✓✔❖◆◇★☆"
# Les puces des polices de symboles (Symbol, Wingdings), dans la zone privée d'Unicode.
PRIVATE_BULLETS = {"": "•", "": "▪", "": "➢", "": "❖", "": "✓"}


def key(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", plain)


def is_marker(text: str) -> bool:
    """Un signe de puce seul (« • », « – », « ➢ », une puce de police de symboles)."""
    text = text.strip()
    return len(text) == 1 and (text in BULLETS or text in PRIVATE_BULLETS or "" <= text <= "")


@dataclass
class Block:
    """Une rubrique de la page : son titre et ses lignes, dans l'ordre de lecture."""

    title: Line | None
    page: int
    lines: list[Line] = field(default_factory=list)
    # Un titre sur deux lignes (« EXPÉRIENCE / PROFESSIONNELLE ») : toutes ses lignes.
    title_lines: list[Line] = field(default_factory=list)

    @property
    def title_text(self) -> str:
        return " ".join(line.text for line in self.title_lines) if self.title_lines else ""


@dataclass
class Structure:
    pages: list[Page]
    # Par page : les couloirs (x0, x1) des colonnes.
    lanes: list[list[tuple[float, float]]]
    titles: list[Line]
    header: list[Line]
    blocks: list[Block]
    page_of: dict[int, int] = field(default_factory=dict)

    def lane_of(self, line: Line) -> list[int]:
        return lanes_of(self.lanes[self.page_of[id(line)] - 1], line.x0, line.x1)

    def order(self, lines: list[Line]) -> list[Line]:
        """L'ordre de lecture : page, colonne, puis de haut en bas et de gauche à droite."""
        return sorted(
            lines,
            key=lambda line: (
                self.page_of.get(id(line), 1),
                min(self.lane_of(line)) if id(line) in self.page_of else 0,
                round(line.baseline),
                line.x0,
            ),
        )

    def block_of(self, line: Line) -> Block | None:
        for block in self.blocks:
            if block.title is line or any(other is line for other in block.lines):
                return block
        return None


def lanes_of(lanes: list[tuple[float, float]], x0: float, x1: float) -> list[int]:
    found = [
        n
        for n, (a, b) in enumerate(lanes)
        if min(b, x1) - max(a, x0) > min(20.0, 0.3 * max(x1 - x0, 1.0))
    ]
    if found:
        return found
    middle = (x0 + x1) / 2
    return [min(range(len(lanes)), key=lambda n: abs((lanes[n][0] + lanes[n][1]) / 2 - middle))]


# ─── Les colonnes ────────────────────────────────────────────────────────────


def find_lanes(page: Page) -> list[tuple[float, float]]:
    """Les colonnes d'une page : séparées par un couloir que presque aucune ligne ne traverse,
    avec assez de lignes de chaque côté, à la même hauteur."""
    lines = [line for line in page.lines if line.x1 - line.x0 > 2]
    if len(lines) < 6:
        return [(0.0, page.width)]
    width = int(page.width)
    crossing = [0] * (width + 1)
    for line in lines:
        for x in range(max(0, int(line.x0) + 1), min(width, int(line.x1))):
            crossing[x] += 1
    limit = max(1, round(0.06 * len(lines)))
    gutters: list[float] = []
    x = 0
    while x <= width:
        if crossing[x] > limit:
            x += 1
            continue
        start = x
        while x <= width and crossing[x] <= limit:
            x += 1
        end = x - 1
        if end - start < 6:
            continue
        left = [line for line in lines if line.x1 <= start + 1]
        right = [line for line in lines if line.x0 >= end - 1]
        if len(left) < 0.12 * len(lines) or len(right) < 0.12 * len(lines):
            continue
        # Une vraie colonne a de la matière (15 % des lettres) ou un titre de rubrique ; des
        # dates ou une grille de mots-clés seules n'en font pas une.
        letters = sum(len(line.text) for line in lines) or 1
        substantial = [
            sum(len(line.text) for line in side) >= 0.15 * letters
            or any(vocabulary(line.text) and len(line.text) <= 48 for line in side)
            for side in (left, right)
        ]
        if not all(substantial):
            continue
        # Côte à côte : des lignes des deux côtés à la même hauteur.
        lo = max(min(line.top for line in left), min(line.top for line in right))
        hi = min(max(line.bottom for line in left), max(line.bottom for line in right))
        extent = max(line.bottom for line in lines) - min(line.top for line in lines)
        if hi - lo < max(60.0, 0.3 * extent):
            continue
        # Des dates alignées à droite ne sont pas une colonne : elles finissent toutes au même
        # bord, commencent n'importe où, et chacune est sur la ligne d'un intitulé à sa gauche.
        nearest = [line for line in lines if start - 1 <= line.x0 < end + 60 and line.x1 > end]
        if len(nearest) >= 2:
            ends = [line.x1 for line in nearest]
            starts = [line.x0 for line in nearest]
            paired = [
                line
                for line in nearest
                if any(abs(o.baseline - line.baseline) < 1.5 and o.x1 < line.x0 for o in lines)
            ]
            if (
                max(ends) - min(ends) < 2.5
                and max(starts) - min(starts) > 6
                and len(paired) >= 0.7 * len(nearest)
            ):
                continue
        gutters.append((start + end) / 2)
    edges = [0.0, *gutters, page.width]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


# ─── Les titres ──────────────────────────────────────────────────────────────


def _body(pages: list[Page]) -> tuple:
    """Le style du texte courant : le plus de lettres."""
    count: Counter = Counter()
    for page in pages:
        for line in page.lines:
            for w in line.words:
                count[(w.font, round(w.size * 2) / 2, w.bold, w.color)] += len(w.text)
    return count.most_common(1)[0][0] if count else ("", 10.0, False, "000000")


def _style(line: Line) -> tuple:
    main = max(line.words, key=lambda w: len(w.text))
    letters = re.sub(r"[^A-Za-zÀ-ÿ]", "", line.text)
    upper = bool(letters) and letters.isupper()
    return (main.font, round(main.size * 2) / 2, main.bold, main.color, upper)


def _decorated(line: Line, shapes: list[Shape]) -> bool:
    """Un filet juste sous la ligne, ou un bandeau derrière elle."""
    for s in shapes:
        overlaps = s.box[0] < line.x1 and s.box[2] > line.x0
        if not overlaps:
            continue
        if s.h <= 3.5 and s.w > 15 and line.bottom - 3 <= s.box[1] <= line.bottom + 14:
            return True
        if (
            s.fill
            and s.box[0] <= line.x0 + 1
            and s.box[2] >= line.x1 - 1
            and s.box[1] <= line.top + 1
            and s.box[3] >= line.bottom - 1
            and s.h < 40
        ):
            return True
    return False


def vocabulary(text: str) -> bool:
    """Un titre de rubrique connu : il commence par un mot de rubrique, ou il est court et
    en contient un (« Mes compétences », « Langues parlées »)."""
    k = key(text)
    return any(k.startswith(word) or (word in k and len(k) <= 26) for word in VOCABULARY)


def _lane_bodies(page: Page, page_lanes: list[tuple[float, float]], default: tuple) -> dict:
    """Le style courant de chaque colonne (une colonne de couleur a le sien)."""
    counts: dict[int, Counter] = {}
    for line in page.lines:
        lanes = lanes_of(page_lanes, line.x0, line.x1)
        if len(lanes) != 1:
            continue
        for w in line.words:
            counts.setdefault(lanes[0], Counter())[
                (w.font, round(w.size * 2) / 2, w.bold, w.color)
            ] += len(w.text)
    return {n: c.most_common(1)[0][0] if c else default for n, c in counts.items()}


def find_titles(pages: list[Page], lanes: list[list[tuple[float, float]]]) -> list[Line]:
    page_body = _body(pages)
    candidates: list[tuple[tuple, Line, Page, bool, bool]] = []
    for page in pages:
        page_lanes = lanes[page.number - 1]
        bodies = _lane_bodies(page, page_lanes, page_body)
        ordered = sorted(page.lines, key=lambda line: line.baseline)
        for i, line in enumerate(ordered):
            text = line.text.strip()
            letters = re.sub(r"[^A-Za-zÀ-ÿ]", "", text)
            if not (2 <= len(text) <= 48) or len(letters) < 2 or len(text.split()) > 6:
                continue
            if text[-1] in ".,;" or is_marker(line.words[0].text):
                continue
            mine = set(lanes_of(page_lanes, line.x0, line.x1))
            beside = [
                other
                for other in page.lines
                if other is not line
                and abs(other.baseline - line.baseline) < 2.5
                and mine & set(lanes_of(page_lanes, other.x0, other.x1))
            ]
            if beside:
                continue
            style = _style(line)
            font, size, bold, color, upper = style
            own = [bodies.get(n, page_body) for n in sorted(mine)]
            body_font, body_size, body_bold, body_color = own[0] if len(own) == 1 else page_body
            distinct = (
                (bold and not body_bold)
                or upper
                or size >= body_size * 1.1
                or (color != body_color and font == body_font)
                or font != body_font
            )
            if not distinct:
                continue
            above = [o for o in ordered[:i] if mine & set(lanes_of(page_lanes, o.x0, o.x1))]
            gap = line.top - above[-1].bottom if above else 99.0
            spaced = gap > 0.9 * body_size
            candidates.append((style, line, page, spaced, _decorated(line, page.shapes)))
    groups: dict[tuple, list[tuple[Line, bool, bool]]] = {}
    for style, line, _, spaced, deco in candidates:
        groups.setdefault(style, []).append((line, spaced, deco))
    scored = []
    for style, members in groups.items():
        hits = sum(1 for line, _, _ in members if vocabulary(line.text))
        n = len(members)
        if n < 2 and hits < 1:
            continue
        size_ratio = style[1] / page_body[1] if page_body[1] else 1
        score = (
            3 * hits
            + 0.5 * n
            + 2 * (1 if style[4] else 0)
            + 4 * max(0.0, size_ratio - 1)
            + 1.5 * sum(1 for _, s, _ in members if s) / n
            + 2 * sum(1 for _, _, d in members if d) / n
        )
        # Des titres de postes en gras : nombreux, sans mot de rubrique.
        if hits == 0:
            score -= 2
        scored.append((score, hits, style, members))
    if not scored:
        return []
    scored.sort(key=lambda s: -s[0])
    best = scored[0][0]
    chosen = [s for s in scored if s is scored[0] or (s[1] >= 1 and s[0] >= 0.5 * best)]
    titles = [line for _, _, _, members in chosen for line, _, _ in members]
    return titles


# ─── Les rubriques ───────────────────────────────────────────────────────────


def analyse(pages: list[Page], extra_titles: list[str] | None = None) -> Structure:
    """La structure des pages ; ``extra_titles`` : des titres lus par l'IA, à retrouver."""
    lanes = [find_lanes(page) for page in pages]
    titles = find_titles(pages, lanes)
    if extra_titles:
        wanted = {key(t) for t in extra_titles if key(t)}
        known = {id(t) for t in titles}
        for page in pages:
            for line in page.lines:
                if id(line) not in known and key(line.text) in wanted:
                    titles.append(line)
                    known.add(id(line))
    page_of = {id(line): page.number for page in pages for line in page.lines}
    # Un titre sur deux lignes : la seconde, collée et alignée, du même style, le continue.
    titles.sort(key=lambda t: (page_of[id(t)], t.baseline, t.x0))
    groups: list[list[Line]] = []
    for t in titles:
        last = groups[-1][-1] if groups else None
        if (
            last is not None
            and page_of[id(last)] == page_of[id(t)]
            and _style(last) == _style(t)
            and 0 <= t.top - last.bottom < 0.8 * t.size
            and min(abs(t.x0 - last.x0), abs(t.x1 - last.x1)) < 3
        ):
            groups[-1].append(t)
        else:
            groups.append([t])
    blocks = [Block(title=g[0], page=page_of[id(g[0])], title_lines=g) for g in groups]
    titles = [g[0] for g in groups]
    block_of_title = {id(b.title): b for b in blocks}
    header: list[Line] = []
    title_ids = {id(t) for g in groups for t in g}
    pending: list[Line] = []
    for page in pages:
        page_lanes = lanes[page.number - 1]
        page_titles = [t for t in titles if page_of[id(t)] == page.number]
        lanes_with_titles = {n for t in page_titles for n in lanes_of(page_lanes, t.x0, t.x1)}
        for line in sorted(page.lines, key=lambda line: (line.baseline, line.x0)):
            if id(line) in title_ids:
                continue
            mine = set(lanes_of(page_lanes, line.x0, line.x1))
            if mine & lanes_with_titles:
                options = [
                    t
                    for t in page_titles
                    if t.baseline < line.baseline - 1
                    and mine & set(lanes_of(page_lanes, t.x0, t.x1))
                ]
            else:
                # Une colonne sans titre (dates, libellés Europass) : la rubrique de la ligne
                # posée à la même hauteur, sinon le titre le plus proche au-dessus.
                pending.append(line)
                continue
            owner = max(options, key=lambda t: t.baseline, default=None)
            if owner is None and page.number > 1:
                # Le haut d'une page suivante continue la dernière rubrique de sa colonne.
                earlier = [
                    t
                    for t in titles
                    if page_of[id(t)] < page.number
                    and mine & set(lanes_of(lanes[page_of[id(t)] - 1], t.x0, t.x1))
                ]
                owner = earlier[-1] if earlier else None
            if owner is None:
                header.append(line)
            else:
                block_of_title[id(owner)].lines.append(line)
    owner_of: dict[int, Block | None] = {id(line): None for line in header}
    for b in blocks:
        for line in b.lines + b.title_lines:
            owner_of[id(line)] = b
    for line in pending:
        page = next(p for p in pages if p.number == page_of[id(line)])
        partners = [
            o
            for o in page.lines
            if o is not line and abs(o.baseline - line.baseline) < 1.5 and id(o) in owner_of
        ]
        if partners:
            partner = min(partners, key=lambda o: abs(o.x1 - line.x0))
            block = owner_of[id(partner)]
        else:
            above = [
                t
                for t in titles
                if page_of[id(t)] == page.number and t.baseline <= line.baseline + 3
            ]
            title = max(above, key=lambda t: t.baseline, default=None)
            block = block_of_title.get(id(title)) if title is not None else None
        if block is None:
            header.append(line)
        else:
            block.lines.append(line)
    blocks.sort(key=lambda b: (b.page, b.title.baseline if b.title else 0))
    return Structure(
        pages=pages, lanes=lanes, titles=titles, header=header, blocks=blocks, page_of=page_of
    )


def _text(lines: list[Line]) -> list[str]:
    """Des lignes (dans l'ordre de lecture) en texte : les segments d'une même ligne de base
    séparés par « | »."""
    rows: list[list[Line]] = []
    for line in lines:
        if rows and abs(rows[-1][0].baseline - line.baseline) < 2.5:
            rows[-1].append(line)
        else:
            rows.append([line])
    out = []
    for row in rows:
        parts = []
        for segment in sorted(row, key=lambda line: line.x0):
            text = segment.text
            first = segment.words[0].text
            if is_marker(first):
                text = "• " + text[len(first) :].strip()
            parts.append(text)
        out.append(" | ".join(parts))
    return out


def text(structure: Structure) -> str:
    """Le texte du CV pour l'IA : l'en-tête, puis chaque rubrique sous son titre."""
    out = ["[En-tête]", *_text(structure.order(structure.header))]
    for block in structure.blocks:
        out.append("")
        out.append(f"## {block.title_text}")
        out += _text(sorted(block.lines, key=lambda line: (round(line.baseline), line.x0)))
    return "\n".join(out).strip() + "\n"


def median_gap(lines: list[Line]) -> float:
    ys = sorted({round(line.baseline, 1) for line in lines})
    steps = [b - a for a, b in zip(ys, ys[1:], strict=False) if b - a > 1]
    return statistics.median(steps) if steps else 12.0
