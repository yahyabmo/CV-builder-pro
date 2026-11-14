"""Après l'IA : le contenu lu, complété et corrigé d'après la page elle-même.

L'IA range le texte dans les rubriques ; elle peut oublier une ligne, couper une puce en
deux, perdre un gras ou un lien. La page, elle, dit tout cela sans se tromper :

1. une puce que la page montre d'un seul tenant (sa suite n'a pas de signe de puce) est
   recollée ; une puce qui en contient deux est coupée ;
2. chaque ligne de la page qu'aucun champ n'écrit rejoint la rubrique sous le titre de
   laquelle elle se trouve (une puce de l'entrée au-dessus, une ligne de liste, une
   rubrique « autre » sous son titre d'origine, une coordonnée de l'en-tête) ;
3. les mots en gras ou en italique au milieu d'un texte courant reçoivent leurs marques
   (``**gras**``, ``__italique__``) ; les liens des coordonnées et des projets sont repris.

Le compte rendu dit combien de mots de la page sont écrits par un champ, et dans la
bonne rubrique.
"""

import re
from dataclasses import dataclass, field

from app.models.content import (
    BulletsSection,
    ContactItem,
    CVContent,
    EducationSection,
    ExperienceSection,
    GridItem,
    GridSection,
    Language,
    LanguagesSection,
    ProjectsSection,
    SkillGroup,
    SkillsSection,
)
from app.services.clone import fields as F
from app.services.clone.reading import Line, Page, Word
from app.services.clone.structure import (
    SEPARATOR,
    Block,
    Structure,
    analyse,
    is_marker,
    key,
    restore_first_letter,
)
from app.text import slugify

# Les champs où un mot en gras au milieu du texte garde sa marque.
RICH = ("summary", "bullets", "description", "text", "level", "")


@dataclass
class Report:
    """Ce que la page et le contenu ont en commun, mot à mot."""

    words: int = 0
    covered: int = 0
    # Mots fixes : un titre de rubrique que l'appli n'a pas en champ (« PROFIL »).
    fixed: int = 0
    misplaced: int = 0
    added: list[str] = field(default_factory=list)
    merged: int = 0
    split: int = 0
    marks: int = 0
    links: int = 0
    left: list[str] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        return (self.covered + self.fixed) / self.words if self.words else 1.0


def _put(content: CVContent, path: str, value: str) -> None:
    bits = path.split(".")
    h = content.header
    if bits[0] in ("name", "headline", "summary") and len(bits) == 1:
        setattr(h, bits[0], value)
        return
    if bits[0] == "contact":
        items = F.contacts(content)
        item = items[int(bits[1])]
        if len(bits) == 3:
            item.label = value
        else:
            item.text = value
        return
    section = next(s for s in content.sections if s.id == bits[0])
    if bits[1] == "title":
        section.title = value
        return
    n = int(bits[1])
    if len(bits) == 2:
        if isinstance(section.items[n], str):
            section.items[n] = value
        else:
            section.items[n].text = value
        return
    if bits[2] == "bullets":
        section.items[n].bullets[int(bits[3])] = value
        return
    setattr(section.items[n], bits[2], value)


def _starts_with_marker(words: list[Word], line: Line, page: Page) -> bool:
    """La ligne de ces mots commence par un signe de puce (lettre ou pastille dessinée)."""
    first = words[0]
    before = [w for w in line.words if w.x1 <= first.x0 + 0.1]
    if before and is_marker(before[-1].text):
        return True
    if is_marker(first.text):
        return True
    for s in page.shapes:
        cy = (s.box[1] + s.box[3]) / 2
        if (
            s.w <= 7
            and s.h <= 7
            and 0 < first.x0 - s.box[2] < 3 * first.size
            and first.top - 1 <= cy <= first.bottom + 1
        ):
            return True
    return False


class _Pages:
    def __init__(self, structure: Structure) -> None:
        self.structure = structure
        self.line_of: dict[int, Line] = {}
        self.page_of: dict[int, Page] = {}
        for page in structure.pages:
            for line in page.lines:
                for w in line.words:
                    self.line_of[id(w)] = line
                    self.page_of[id(w)] = page

    def first_line(self, hit: F.Hit) -> tuple[Line, Page]:
        w = hit.words[0]
        return self.line_of[id(w)], self.page_of[id(w)]

    def follows(self, a: F.Hit, b: F.Hit) -> bool:
        """``b`` reprend là où ``a`` s'arrête : juste après sur la même ligne, ou au début
        de la ligne d'en dessous."""
        last, first = a.words[-1], b.words[0]
        line_a, line_b = self.line_of[id(last)], self.line_of[id(first)]
        if line_a is line_b:
            after = line_a.words[line_a.words.index(last) + 1 :]
            between = [w for w in after if w.x0 < first.x0 and key(w.text)]
            return first.x0 >= last.x0 and not between
        below = 0 <= first.top - last.bottom < 0.8 * first.size
        starts = line_b.words[0] is first or all(
            not key(w.text) for w in line_b.words[: line_b.words.index(first)]
        )
        return below and starts and first.x0 >= min(w.x0 for w in a.words) - 1.5

    def marker(self, hit: F.Hit) -> bool:
        line, page = self.first_line(hit)
        words = [w for w in line.words if w in hit.words] or hit.words[:1]
        return _starts_with_marker(words, line, page)


def _bullet_lists(content: CVContent) -> list[tuple[str, list[str], callable]]:
    """Chaque liste de puces du contenu : (préfixe de chemin, puces, de quoi la remplacer)."""
    out = []
    for s in content.sections:
        if not s.visible:
            continue
        if s.kind in ("experience", "projects", "education"):
            for n, item in enumerate(s.items):

                def setter(values: list[str], item=item) -> None:
                    item.bullets = values

                out.append((f"{s.id}.{n}.bullets.", list(item.bullets), setter))
        elif s.kind == "bullets":

            def setter(values: list[str], s=s) -> None:
                s.items = values

            out.append((f"{s.id}.", list(s.items), setter))
    return out


def _fix_bullets(content: CVContent, structure: Structure, report: Report) -> bool:
    """Recolle les puces coupées par l'IA, coupe celles qui en contiennent deux."""
    hits = F.Locator(structure, content).locate()
    pages = _Pages(structure)
    changed = False
    for prefix, bullets, setter in _bullet_lists(content):
        found = [hits.get(f"{prefix}{k}") for k in range(len(bullets))]
        located = [h for h in found if h is not None]
        if not located or not any(pages.marker(h) or _inner_markers(h, pages) for h in located):
            continue
        out: list[str] = []
        previous: F.Hit | None = None
        for k, text in enumerate(bullets):
            hit = found[k]
            if (
                hit is not None
                and previous is not None
                and out
                and not pages.marker(hit)
                and pages.follows(previous, hit)
            ):
                out[-1] = out[-1].rstrip() + " " + text.lstrip()
                report.merged += 1
                previous = F.Hit(hit.path, previous.words + hit.words)
                changed = True
                continue
            # Deux puces de la page dans une seule puce du contenu : on coupe.
            if hit is not None:
                starts = []
                lines: list[Line] = []
                for w in hit.words:
                    line = pages.line_of[id(w)]
                    if not lines or lines[-1] is not line:
                        lines.append(line)
                for line in lines[1:]:
                    words = [w for w in line.words if w in hit.words]
                    if words and _starts_with_marker(words, line, pages.page_of[id(words[0])]):
                        first = next((w.text for w in words if not is_marker(w.text)), "")
                        if first:
                            starts.append(first)
                pieces = _split_at(text, starts)
                if len(pieces) > 1:
                    out += pieces
                    report.split += len(pieces) - 1
                    changed = True
                    previous = hit
                    continue
            out.append(text)
            previous = hit if hit is not None else previous
        if changed:
            setter(out)
    return changed


def _same_name(a: str, b: str) -> bool:
    """Deux noms pareils, même si la lecture d'un scan a perdu une première lettre."""
    ka, kb = key(a), key(b)
    return bool(ka and kb) and (ka == kb or ka == kb[1:] or kb == ka[1:])


def _split_lists(content: CVContent, structure: Structure, report: Report) -> bool:
    """Une liste de compétences à puces : un groupe par puce de la page (l'IA les écrit
    parfois à la suite, dans un seul groupe) ; un groupe nommé comme sa rubrique n'a pas
    de nom."""
    hits = F.Locator(structure, content).locate()
    pages = _Pages(structure)
    changed = False
    for s in content.sections:
        if not isinstance(s, SkillsSection) or not s.visible:
            continue
        out: list[SkillGroup] = []
        for n, group in enumerate(s.items):
            if group.label and _same_name(group.label, s.title):
                group.label = ""
                changed = True
            hit = hits.get(f"{s.id}.{n}.text")
            starts: list[str] = []
            if hit is not None:
                lines: list[Line] = []
                for w in hit.words:
                    line = pages.line_of[id(w)]
                    if not lines or lines[-1] is not line:
                        lines.append(line)
                for line in lines[1:]:
                    words = [w for w in line.words if w in hit.words]
                    if words and _starts_with_marker(words, line, pages.page_of[id(words[0])]):
                        # Le premier mot après le signe de puce (que le texte n'a pas).
                        text = next((w.text for w in words if not is_marker(w.text)), "")
                        if text:
                            starts.append(text)
            pieces = _split_at(group.text, starts) if starts else [group.text]
            if len(pieces) > 1:
                out.append(SkillGroup(label=group.label, text=pieces[0]))
                out += [SkillGroup(label="", text=piece) for piece in pieces[1:]]
                report.split += len(pieces) - 1
                changed = True
            else:
                out.append(group)
        s.items = out
    return changed


def _description_bullets(content: CVContent, structure: Structure, report: Report) -> bool:
    """La description d'une formation ou d'un projet écrite en lignes à puces sur la page :
    ses puces."""
    hits = F.Locator(structure, content).locate()
    pages = _Pages(structure)
    changed = False
    for s in content.sections:
        if not isinstance(s, (EducationSection, ProjectsSection)) or not s.visible:
            continue
        for n, item in enumerate(s.items):
            hit = hits.get(f"{s.id}.{n}.description")
            if item.bullets or hit is None:
                continue
            lines: list[Line] = []
            for w in hit.words:
                line = pages.line_of[id(w)]
                if not lines or lines[-1] is not line:
                    lines.append(line)
            starts = []
            for line in lines:
                words = [w for w in line.words if w in hit.words]
                if words and _starts_with_marker(words, line, pages.page_of[id(words[0])]):
                    first = next((w.text for w in words if not is_marker(w.text)), "")
                    if first:
                        starts.append(first)
            if len(starts) < 2:
                continue
            text = item.description.replace("\n", " ").lstrip("•·-– ").strip()
            pieces = _split_at(text, starts[1:])
            if len(pieces) < 2:
                continue
            item.bullets = [p.lstrip("•·-– ").strip() for p in pieces]
            item.description = ""
            report.split += len(pieces) - 1
            changed = True
    return changed


def _merge_twins(content: CVContent, structure: Structure) -> bool:
    """Deux rubriques du même genre et du même titre (l'IA a mis le bénévolat à part, sous
    le même « EXPÉRIENCE ») : une seule, ses entrées dans l'ordre de la page."""
    hits = F.Locator(structure, content).locate()
    changed = False
    seen: dict[tuple[str, str], object] = {}
    for s in content.sections:
        if not s.visible or not s.items or not key(s.title):
            continue
        k = (s.kind, key(s.title))
        first = seen.get(k)
        if first is None:
            seen[k] = s
            continue
        if type(first.items[0]) is not type(s.items[0]):
            continue

        def top(section, n: int) -> float:
            found = [h.top for p, h in hits.items() if p.startswith(f"{section.id}.{n}.")]
            return min(found) if found else 10.0**6

        both = [(top(first, n), 0, n, it) for n, it in enumerate(first.items)]
        both += [(top(s, n), 1, n, it) for n, it in enumerate(s.items)]
        both.sort(key=lambda t: (t[0], t[1], t[2]))
        first.items = [it for *_, it in both]
        s.items = []
        s.visible = False
        changed = True
    return changed


def _titles_from_labels(content: CVContent, structure: Structure) -> bool:
    """Plusieurs rubriques au même titre, tirées d'une seule liste de la page (« Langues : … »,
    « Compétences transversales : … » sous « Compétences ») : chacune prend le libellé écrit
    devant sa ligne, que la page montre (sans lui, ce libellé resterait sans champ)."""
    hits = F.Locator(structure, content).locate()
    pages = _Pages(structure)
    groups: dict[str, list] = {}
    for s in content.sections:
        if s.visible and s.items and key(s.title):
            groups.setdefault(key(s.title), []).append(s)
    changed = False
    for same in groups.values():
        if len(same) < 2:
            continue
        for s in same:
            # Un groupe de compétences porte déjà son libellé : seulement les autres listes.
            if s.kind not in ("languages", "grid", "bullets"):
                continue
            mine = [h for p, h in hits.items() if p == f"{s.id}.0" or p.startswith(f"{s.id}.0.")]
            if not mine:
                continue
            # Le premier mot de l'élément sur la page (son nom, pas son niveau).
            w = min((h.words[0] for h in mine), key=lambda x: (round(x.top), x.x0))
            line = pages.line_of[id(w)]
            before = [x for x in line.words if x.x1 <= w.x0 + 0.1 and not is_marker(x.text)]
            label = " ".join(x.text for x in before).strip().rstrip(":").strip()
            if (
                label
                and re.search(r"[A-Za-zÀ-ÿ]", label)
                and len(label) <= 40
                and key(label) != key(s.title)
            ):
                s.title = label
                changed = True
    return changed


def _inner_markers(hit: F.Hit, pages: _Pages) -> bool:
    """Une ligne d'un champ, après la première, commence par un signe de puce."""
    lines: list[Line] = []
    for w in hit.words:
        line = pages.line_of[id(w)]
        if not lines or lines[-1] is not line:
            lines.append(line)
    for line in lines[1:]:
        words = [w for w in line.words if w in hit.words]
        if words and _starts_with_marker(words, line, pages.page_of[id(words[0])]):
            return True
    return False


def _split_at(text: str, starts: list[str]) -> list[str]:
    pieces = [text]
    for start in starts:
        last = pieces[-1]
        position = last.find(start, 1)
        if position <= 0:
            continue
        pieces[-1:] = [last[:position].rstrip(" ;,"), last[position:]]
    return [p for p in pieces if p.strip()]


def _paragraphs(lines: list[Line], pages: _Pages, right: float) -> list[list[Line]]:
    """Des lignes en paragraphes : une ligne sans puce, juste sous une ligne pleine (coupée
    au bord droit ``right``), la continue."""
    out: list[list[Line]] = []
    for line in lines:
        last = out[-1][-1] if out else None
        page = pages.page_of[id(line.words[0])]
        if (
            last is not None
            and 0 <= line.top - last.bottom < 0.8 * line.size
            and last.x1 >= right - max(3 * line.size, 15)
            and not _starts_with_marker(line.words, line, page)
            and abs(line.x0 - last.x0) < 2 * line.size
        ):
            out[-1].append(line)
        else:
            out.append([line])
    return out


def _text(lines: list[Line], only: set[int]) -> str:
    words = [w for line in lines for w in line.words if id(w) in only or not key(w.text)]
    while words and is_marker(words[0].text):
        words = words[1:]
    text = ""
    for w in words:
        text += ("" if w.glued or not text else " ") + w.text
    # Une coupure en fin de ligne (« prépa- ration ») se recolle.
    return re.sub(r"(\w)- (\w)", r"\1\2", text).strip()


_DATE = re.compile(
    r"(?:(?:janv|févr|fevr|mars|avr|mai|juin|juil|août|aout|sept|oct|nov|déc|dec)\w*\.?\s+)?"
    r"(?:\d{1,2}/)?(?:19|20)\d\d(?:\s*[-–—]\s*(?:(?:\w+\.?\s+)?(?:\d{1,2}/)?(?:19|20)\d\d"
    r"|aujourd\S*hui|présent|present|en cours))?",
    re.I,
)
_CONTACT = re.compile(r"@|https?://|www\.|linkedin|github|\+?\d[\d .-]{7,}")
# « Adresse : 69000 Lyon », « Tél : », « Permis B » : une coordonnée, libellé en tête.
_CONTACT_LABEL = re.compile(
    r"^\s*(adresse|t[ée]l[ée]?(?:phone)?|t[ée]l\.?|e-?mail|mail|portable|mobile|linkedin|"
    r"github|site(?: web)?|permis(?: de conduire)?|n[ée]e? le|nationalit[ée]|[âa]ge|"
    r"date de naissance)\s*(?::|$)",
    re.I,
)


def _add_lines(content: CVContent, structure: Structure, report: Report) -> None:
    """Chaque ligne qu'aucun champ n'écrit rejoint la rubrique de son titre."""
    locator = F.Locator(structure, content)
    hits = locator.locate()
    pages = _Pages(structure)
    left = F.uncovered(structure, hits)
    title_words = {id(w) for b in structure.blocks for line in b.title_lines for w in line.words}
    left = [w for w in left if id(w) not in title_words]
    if not left:
        return
    left_ids = {id(w) for w in left}
    block_section: dict[int, str] = {}
    for sid, b in locator.section_block.items():
        block_section.setdefault(id(b), sid)
    lines: list[Line] = []
    for w in left:
        line = pages.line_of[id(w)]
        if not lines or lines[-1] is not line:
            if line not in lines:
                lines.append(line)
    by_block: dict[int, tuple[Block | None, list[Line]]] = {}
    for line in lines:
        block = structure.block_of(line)
        slot = id(block) if block is not None else 0
        by_block.setdefault(slot, (block, []))[1].append(line)
    for block, block_lines in by_block.values():
        ordered = structure.order(block_lines)
        sid = block_section.get(id(block)) if block is not None else None
        section = next((s for s in content.sections if s.id == sid), None)
        # Le bord droit du texte de la colonne : une ligne qui l'atteint a été coupée.
        lane = set(structure.lane_of(ordered[0]))
        page = pages.page_of[id(ordered[0].words[0])]
        right = max(
            (line.x1 for line in page.lines if set(structure.lane_of(line)) == lane),
            default=ordered[0].x1,
        )
        for paragraph in _paragraphs(ordered, pages, right):
            text = _text(paragraph, left_ids)
            if not key(text):
                continue
            report.added.append(text)
            top = paragraph[0].top
            listed = section is None or not isinstance(
                section, (ExperienceSection, ProjectsSection, EducationSection)
            )
            if block is None or (section is None and block.title is None):
                _to_header(content, text)
            elif listed and _CONTACT_LABEL.match(text):
                _to_header(content, text)
            elif section is None:
                _to_other(content, structure, block, text)
            else:
                _to_section(section, text, top, hits, pages)


def _to_header(content: CVContent, text: str) -> None:
    h = content.header
    labelled = _CONTACT_LABEL.match(text)
    if labelled:
        label, _, value = text.partition(":")
        if not h.contact_lines:
            h.contact_lines.append([])
        if value.strip():
            h.contact_lines[-1].append(
                ContactItem(text=value.strip(), label=label.strip(), url=None, bold=False)
            )
        else:
            h.contact_lines[-1].append(ContactItem(text=text.strip(), url=None, bold=False))
        return
    if _CONTACT.search(text):
        if not h.contact_lines:
            h.contact_lines.append([])
        url = None
        if "@" in text and " " not in text.strip():
            url = f"mailto:{text.strip()}"
        elif re.match(r"https?://", text):
            url = text.strip()
        h.contact_lines[-1].append(ContactItem(text=text, url=url, bold=False))
    elif not h.headline.strip() and len(text) <= 80:
        h.headline = text
    elif not h.summary.strip():
        h.summary = text
    else:
        h.summary = h.summary.rstrip() + " " + text


def _to_other(content: CVContent, structure: Structure, block: Block, text: str) -> None:
    title = block.title_text.strip()
    k = key(title)
    section = next((s for s in content.sections if s.kind == "bullets" and key(s.title) == k), None)
    if section is None:
        taken = {s.id for s in content.sections}
        base = slugify(title, "rubrique")
        sid, n = base, 2
        while sid in taken:
            sid, n = f"{base}-{n}", n + 1
        lanes = structure.lane_of(block.title) if block.title is not None else [0]
        column = (
            "left"
            if lanes and lanes[0] == 0 and len(structure.lanes[block.page - 1]) > 1
            else "right"
        )
        section = BulletsSection(id=sid, title=title, column=column, items=[])
        content.sections.append(section)
    section.items.append(text)


def _to_section(section, text: str, top: float, hits: dict[str, F.Hit], pages: _Pages) -> None:
    if isinstance(section, (ExperienceSection, ProjectsSection, EducationSection)):
        # L'entrée juste au-dessus de la ligne.
        tops = []
        for n in range(len(section.items)):
            starts = [h.top for p, h in hits.items() if p.startswith(f"{section.id}.{n}.")]
            if starts:
                tops.append((min(starts), n))
        above = [(t, n) for t, n in tops if t <= top + 1]
        n = max(above)[1] if above else len(section.items) - 1
        if n < 0:
            return
        item = section.items[n]
        # Une date oubliée par l'IA va dans le champ des dates de l'entrée, s'il est vide.
        if _DATE.fullmatch(text.strip()):
            name = "date" if isinstance(section, ProjectsSection) else "dates"
            if not (getattr(item, name, "") or "").strip():
                setattr(item, name, text.strip())
                return
        if isinstance(section, EducationSection) and not item.bullets:
            item.description = (item.description.rstrip() + " " + text).strip()
        else:
            item.bullets.append(text)
        return
    if isinstance(section, SkillsSection):
        label, _, rest = text.partition(":")
        if rest.strip() and len(label) <= 40:
            section.items.append(SkillGroup(label=label.strip(), text=rest.strip()))
        else:
            section.items.append(SkillGroup(label="", text=text))
    elif isinstance(section, LanguagesSection):
        found = re.match(r"^(.+?)\s*(?::|–|—|-|\()\s*(.*?)\)?$", text)
        if found:
            section.items.append(
                Language(name=found.group(1).strip(), level=found.group(2).strip())
            )
        else:
            section.items.append(Language(name=text, level=""))
    elif isinstance(section, GridSection):
        section.items.append(GridItem(text=text, wide=len(text) > 22))
    elif isinstance(section, BulletsSection):
        section.items.append(text)


def _marks_and_links(content: CVContent, structure: Structure, report: Report) -> None:
    hits = F.Locator(structure, content).locate()
    items = F.contacts(content)
    for path, hit in hits.items():
        bits = path.split(".")
        last = bits[-1] if not bits[-1].isdigit() else (bits[-2] if len(bits) > 2 else "")
        if bits[0] == "summary" or (
            bits[0] not in ("name", "headline", "contact") and last in RICH
        ):
            text = F.get(content, path) or ""
            marks = F.marks_for(hit.words)
            if marks:
                marked = F.apply_marks(text, marks)
                if marked != text:
                    _put(content, path, marked)
                    report.marks += marked.count("**") // 2 + marked.count("__") // 2
        url = next((w.url for w in hit.words if w.url), None)
        if url is None:
            continue
        if bits[0] == "contact" and len(bits) == 2:
            item = items[int(bits[1])]
            if not item.url:
                item.url = url
                report.links += 1
        elif len(bits) >= 3:
            section = next((s for s in content.sections if s.id == bits[0]), None)
            if isinstance(section, ProjectsSection):
                item = section.items[int(bits[1])]
                if not item.link:
                    item.link = url
                    report.links += 1


def _titles_from_page(content: CVContent, structure: Structure) -> bool:
    """Une rubrique que l'IA a créée sans titre écrit sur la page (« Soft skills ») mais dont
    tous les mots sont sous un même titre de la page prend ce titre : c'est là qu'ils sont."""
    locator = F.Locator(structure, content)
    hits = locator.locate()
    pages = _Pages(structure)
    changed = False
    for section in content.sections:
        if not section.visible or section.id in locator.section_block:
            continue
        # Son titre se lit déjà sur la page (un libellé de ligne, « Langues : … ») : il reste.
        if f"{section.id}.title" in hits:
            continue
        words = [
            w
            for path, hit in hits.items()
            if path.startswith(f"{section.id}.") and not path.endswith(".title")
            for w in hit.words
        ]
        blocks = {
            id(structure.block_of(pages.line_of[id(w)])): structure.block_of(pages.line_of[id(w)])
            for w in words
        }
        if len(blocks) == 1:
            block = next(iter(blocks.values()))
            if block is not None and block.title_lines and block in locator.section_block.values():
                section.title = block.title_text
                changed = True
    return changed


def measure(content: CVContent, structure: Structure, report: Report | None = None) -> Report:
    """Les mots de la page écrits par un champ du contenu, et dans la bonne rubrique."""
    report = report or Report()
    locator = F.Locator(structure, content)
    hits = locator.locate()
    words = [
        w for page in structure.pages for line in page.lines for w in line.words if key(w.text)
    ]
    report.words = len(words)
    block_of_word: dict[int, Block | None] = {}
    for page in structure.pages:
        for line in page.lines:
            block = structure.block_of(line)
            for w in line.words:
                block_of_word[id(w)] = block
    section_of_block: dict[int, set[str]] = {}
    for sid, b in locator.section_block.items():
        section_of_block.setdefault(id(b), set()).add(sid)
    # Une rubrique nommée par un libellé de ligne (« Qualités : … ») est sous le titre de la
    # page où se trouve cette ligne.
    lines_of = {id(w): line for page in structure.pages for line in page.lines for w in line.words}
    for sid, label in locator.label_words.items():
        if sid not in locator.section_block and label:
            b = structure.block_of(lines_of[id(label[0])])
            if b is not None:
                section_of_block.setdefault(id(b), set()).add(sid)
    # Les mots d'un titre de la page qu'aucun champ n'écrit (« PROFIL », ou « LANGUES &
    # CENTRES D'INTÉRÊT » quand ses deux rubriques portent le nom de leur ligne) : fixes.
    title_words = {id(w) for b in structure.blocks for line in b.title_lines for w in line.words}
    covered = {}
    for path, hit in hits.items():
        for w in hit.words:
            covered[id(w)] = path
    report.covered = report.fixed = report.misplaced = 0
    report.left = []
    for w in words:
        path = covered.get(id(w))
        if path is None:
            if id(w) in title_words:
                report.fixed += 1
            else:
                report.left.append(w.text)
            continue
        report.covered += 1
        block = block_of_word.get(id(w))
        sid = path.split(".")[0]
        header = sid in ("name", "headline", "summary", "contact")
        expected = section_of_block.get(id(block)) if block is not None else None
        if header:
            if expected is not None and block is not None and block.title is not None:
                report.misplaced += 1
        elif expected is not None and sid not in expected:
            report.misplaced += 1
    return report


def _no_separator(content: CVContent) -> None:
    """Le séparateur du texte donné à l'IA (« ⟶ »), s'il a été recopié dans un champ."""
    for path, text, _ in F.paths(content):
        if SEPARATOR in text:
            _put(content, path, re.sub(rf"\s*{SEPARATOR}\s*", " ", text).strip())


def _no_repeated_label(content: CVContent) -> None:
    """Une coordonnée qui répète son libellé (« LinkedIn » : « LinkedIn : prénom-nom ») : le
    texte sans lui."""
    for item in F.contacts(content):
        if not item.label:
            continue
        head, colon, rest = item.text.partition(":")
        if colon and rest.strip() and key(head) == key(item.label):
            item.text = rest.strip()


def complete(content: CVContent, pages: list[Page]) -> tuple[CVContent, Report]:
    """Le contenu complété d'après la page, et le compte rendu."""
    content = content.model_copy(deep=True)
    _no_separator(content)
    _no_repeated_label(content)
    report = Report()
    titles = lambda: [s.title for s in content.sections if s.visible]  # noqa: E731
    structure = analyse(pages, titles())
    if _fix_bullets(content, structure, report):
        structure = analyse(pages, titles())
    if _split_lists(content, structure, report):
        structure = analyse(pages, titles())
    if _description_bullets(content, structure, report):
        structure = analyse(pages, titles())
    if _merge_twins(content, structure):
        structure = analyse(pages, titles())
    if _titles_from_labels(content, structure):
        structure = analyse(pages, titles())
    _add_lines(content, structure, report)
    structure = analyse(pages, titles())
    if _titles_from_page(content, structure):
        structure = analyse(pages, titles())
    _marks_and_links(content, structure, report)
    for section in content.sections:
        if section.items:
            section.visible = True
        section.title = restore_first_letter(section.title)
    measure(content, structure, report)
    return content, report
