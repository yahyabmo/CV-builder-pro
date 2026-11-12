"""Les champs du contenu (chemins) et leur place sur la page (les mots qui les écrivent).

Un chemin nomme un champ : ``name``, ``headline``, ``summary``, ``contact.3`` (et
``contact.3.label``), ``<rubrique>.title``, ``<rubrique>.<n>.<champ>`` (title, place,
dates, description, label, text…), ``<rubrique>.<n>.bullets.<k>`` et ``<rubrique>.<n>``
pour une ligne de liste.

On retrouve chaque champ dans le texte de la page, lettres et chiffres seulement (sans
accents ni ponctuation), dans la rubrique de même titre d'abord : les plus longs d'abord,
pour qu'une date ne prenne pas un morceau de puce.
"""

import difflib
import re
from dataclasses import dataclass, field

from app.models.content import CVContent
from app.services.clone.reading import Line, Word
from app.services.clone.structure import Block, Structure, key

# ─── Les chemins ─────────────────────────────────────────────────────────────

ITEM_FIELDS = {
    "experience": ("title", "tag", "place", "dates"),
    "education": ("title", "place", "dates", "description"),
    "projects": ("title", "tag", "date", "description"),
    "skills": ("label", "text"),
    "languages": ("name", "level"),
    "grid": ("text",),
}


def contacts(content: CVContent):
    return [item for line in content.header.contact_lines for item in line]


def paths(content: CVContent, visible_only: bool = True) -> list[tuple[str, str, str | None]]:
    """Tous les champs écrits : (chemin, texte, rubrique)."""
    out: list[tuple[str, str, str | None]] = []
    h = content.header
    for name in ("name", "headline", "summary"):
        out.append((name, getattr(h, name), None))
    for i, item in enumerate(contacts(content)):
        out.append((f"contact.{i}", item.text, None))
        if item.label:
            out.append((f"contact.{i}.label", item.label, None))
    for s in content.sections:
        if visible_only and not s.visible:
            continue
        out.append((f"{s.id}.title", s.title, s.id))
        for n, it in enumerate(s.items):
            if s.kind == "bullets":
                out.append((f"{s.id}.{n}", it, s.id))
                continue
            for name in ITEM_FIELDS[s.kind]:
                out.append((f"{s.id}.{n}.{name}", getattr(it, name, "") or "", s.id))
            for k, bullet in enumerate(getattr(it, "bullets", []) or []):
                out.append((f"{s.id}.{n}.bullets.{k}", bullet, s.id))
    return [(p, t, s) for p, t, s in out if t and t.strip()]


def get(content: CVContent, path: str) -> str | None:
    parts = path.split(".")
    h = content.header
    if parts[0] in ("name", "headline", "summary") and len(parts) == 1:
        return getattr(h, parts[0])
    if parts[0] == "contact":
        items = contacts(content)
        i = int(parts[1])
        if i >= len(items):
            return None
        return (items[i].label or "") if len(parts) == 3 else items[i].text
    section = next((s for s in content.sections if s.id == parts[0]), None)
    if section is None:
        return None
    if parts[1] == "title":
        return section.title
    n = int(parts[1])
    if n >= len(section.items):
        return None
    item = section.items[n]
    if len(parts) == 2:
        return item if isinstance(item, str) else getattr(item, "text", None)
    if parts[2] == "bullets":
        bullets = getattr(item, "bullets", []) or []
        k = int(parts[3])
        return bullets[k] if k < len(bullets) else None
    return getattr(item, parts[2], None)


def strip_marks(text: str) -> str:
    return text.replace("**", "").replace("__", "")


# ─── Retrouver les champs sur la page ────────────────────────────────────────


@dataclass
class Hit:
    path: str
    words: list[Word]

    @property
    def top(self) -> float:
        return min(w.top for w in self.words)

    @property
    def bottom(self) -> float:
        return max(w.bottom for w in self.words)

    @property
    def x0(self) -> float:
        return min(w.x0 for w in self.words)

    @property
    def x1(self) -> float:
        return max(w.x1 for w in self.words)


@dataclass
class Region:
    """Des lignes dans l'ordre de lecture, et leur texte réduit aux lettres et chiffres."""

    lines: list[Line]
    words: list[Word] = field(default_factory=list)
    text: str = ""
    # Pour chaque lettre du texte : l'indice de son mot.
    owner: list[int] = field(default_factory=list)
    starts: set[int] = field(default_factory=set)
    ends: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        chunks = []
        pos = 0
        for line in self.lines:
            for w in line.words:
                k = key(w.text)
                index = len(self.words)
                self.words.append(w)
                if not k:
                    continue
                if not w.glued:
                    self.starts.add(pos)
                chunks.append(k)
                self.owner += [index] * len(k)
                pos += len(k)
                self.ends.add(pos)
        self.text = "".join(chunks)


class Locator:
    """Retrouve les champs du contenu, sans jamais donner deux fois le même mot."""

    def __init__(self, structure: Structure, content: CVContent) -> None:
        self.structure = structure
        self.content = content
        self.used: set[int] = set()  # id() des mots déjà pris
        self.hits: dict[str, Hit] = {}
        # La rubrique de la page qui porte le titre de chaque rubrique du contenu.
        self.section_block: dict[str, Block] = {}
        for s in content.sections:
            k = key(s.title)
            block = next((b for b in structure.blocks if key(b.title_text) == k), None)
            if block is None and k:
                block = next(
                    (
                        b
                        for b in structure.blocks
                        if k in key(b.title_text) or (key(b.title_text) and key(b.title_text) in k)
                    ),
                    None,
                )
            # Deux rubriques au même titre (l'IA range une ligne de qualités sous « Compétences »)
            # partagent la rubrique de la page ; un titre approché n'en prend qu'une libre.
            exact = block is not None and key(block.title_text) == k
            if block is not None and (exact or block not in self.section_block.values()):
                self.section_block[s.id] = block
        taken = set(map(id, self.section_block.values()))
        free = [b for b in structure.blocks if id(b) not in taken]
        self.header_lines = structure.header + [line for b in free for line in b.lines]
        self.everything = structure.order([line for page in structure.pages for line in page.lines])

    def region_for(self, section_id: str | None) -> list[Line]:
        if section_id is None:
            return self.structure.order(self.header_lines)
        block = self.section_block.get(section_id)
        if block is None:
            return []
        return block.title_lines + self.structure.order(block.lines)

    def locate(self) -> dict[str, Hit]:
        jobs = sorted(paths(self.content), key=lambda job: -len(key(strip_marks(job[1]))))
        # Les titres de rubrique d'abord : ce sont leurs propres lignes.
        for sid, block in self.section_block.items():
            path = f"{sid}.title"
            words = [w for line in block.title_lines for w in line.words]
            if words and not any(id(w) in self.used for w in words):
                self.hits[path] = Hit(path, words)
                self.used.update(map(id, words))
        for path, text, sid in jobs:
            if path in self.hits:
                continue
            k = key(strip_marks(text))
            if not k:
                continue
            hit = self.find(k, self.region_for(sid))
            if hit is None:
                hit = self.find(k, self.everything)
            if hit is None and len(k) >= 12:
                hit = self.fuzzy(k, self.region_for(sid)) or self.fuzzy(k, self.everything)
            if hit is not None:
                self.hits[path] = Hit(path, hit)
                self.used.update(map(id, hit))
        return self.hits

    def find(self, k: str, lines: list[Line]) -> list[Word] | None:
        if not lines:
            return None
        region = Region(lines)
        best: tuple[int, int] | None = None
        start = region.text.find(k)
        while start >= 0:
            end = start + len(k)
            ids = {id(region.words[i]) for i in region.owner[start:end]}
            if not ids & self.used:
                score = (start in region.starts) + (end in region.ends)
                if best is None or score > best[1]:
                    best = (start, score)
                    if score == 2:
                        break
            start = region.text.find(k, start + 1)
        if best is None:
            return None
        s = best[0]
        indexes = region.owner[s : s + len(k)]
        # Les signes entre les mots du champ (« 2022 – 2024 ») lui appartiennent aussi.
        return [region.words[i] for i in range(min(indexes), max(indexes) + 1)]

    def fuzzy(self, k: str, lines: list[Line]) -> list[Word] | None:
        """Le texte presque identique (une lettre changée par l'IA) : 90 % des lettres."""
        if not lines:
            return None
        region = Region(lines)
        free = "".join(
            ch if id(region.words[region.owner[i]]) not in self.used else "\0"
            for i, ch in enumerate(region.text)
        )
        matcher = difflib.SequenceMatcher(None, free, k, autojunk=False)
        blocks = [b for b in matcher.get_matching_blocks() if b.size >= 3]
        if not blocks:
            return None
        # La fenêtre la plus dense autour du plus long bloc.
        longest = max(blocks, key=lambda b: b.size)
        window = [
            b for b in blocks if abs(b.a - longest.a - (b.b - longest.b)) <= max(8, len(k) // 10)
        ]
        matched = sum(b.size for b in window)
        if matched < 0.9 * len(k):
            return None
        a0 = min(b.a for b in window)
        a1 = max(b.a + b.size for b in window)
        indexes = region.owner[a0:a1]
        words = [region.words[i] for i in range(min(indexes), max(indexes) + 1)]
        if any(id(w) in self.used for w in words):
            return None
        return words


def uncovered(structure: Structure, hits: dict[str, Hit]) -> list[Word]:
    """Les mots de la page (avec lettres ou chiffres) qu'aucun champ n'écrit."""
    used = {id(w) for hit in hits.values() for w in hit.words}
    return [
        w
        for page in structure.pages
        for line in page.lines
        for w in line.words
        if key(w.text) and id(w) not in used
    ]


def marks_for(words: list[Word]) -> list[tuple[str, str]]:
    """Les suites de mots en gras ou en italique dans un texte qui ne l'est pas : (marque,
    texte). Rien si tout le champ a ce style."""
    letters = sum(len(w.text) for w in words) or 1
    bold = sum(len(w.text) for w in words if w.bold) / letters
    italic = sum(len(w.text) for w in words if w.italic) / letters
    out: list[tuple[str, str]] = []
    for mark, flag, share in (("**", "bold", bold), ("__", "italic", italic)):
        if share == 0 or share > 0.6:
            continue
        run: list[Word] = []
        for w in [*words, None]:
            if w is not None and getattr(w, flag) and key(w.text):
                run.append(w)
                continue
            if w is not None and getattr(w, flag) and run:
                run.append(w)
                continue
            if run:
                text = ""
                for r in run:
                    text += ("" if r.glued or not text else " ") + r.text
                out.append((mark, text.strip(" ,;:")))
                run = []
    return [(m, t) for m, t in out if key(t)]


def apply_marks(text: str, marks: list[tuple[str, str]]) -> str:
    """Pose les marques dans le texte du contenu, là où le texte marqué s'y trouve tel quel."""
    if "**" in text or "__" in text:
        return text
    out = text
    for mark, part in marks:
        pattern = re.escape(part)
        found = re.search(rf"(?<![\w*_]){pattern}(?![\w*_])", out)
        if found:
            out = out[: found.start()] + mark + found.group(0) + mark + out[found.end() :]
    return out
