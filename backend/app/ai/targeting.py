"""Le ciblage d'une offre : de l'offre et d'un CV source à une proposition.

Trois appels au modèle (quatre si le CV change de langue) :

1. analyse de l'offre (``OfferAnalysis``) ;
2. plan : titre, accroche, compétences, projets (``TargetPlan``) ;
3. formulations : puces des expériences, choisies dans leur réserve et
   adaptées, et descriptions des projets (``Rewrite``) ;
4. traduction du reste du CV, si la langue visée n'est pas celle du CV.

« Relancer » refait les étapes 2 à 4 avec la bibliothèque à jour, en gardant
l'analyse.

On maximise la correspondance avec l'offre, mais rien de nouveau n'entre dans
le CV sans un clic de validation :

- une compétence absente de son profil arrive « à confirmer » (non cochée) ;
- une phrase qui introduit un mot-clé de l'offre absent de son profil arrive
  non cochée, avec ce terme à confirmer ;
- à la création du CV, ce qu'il a confirmé rejoint sa bibliothèque.
"""

import json
import re
import unicodedata
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from jinja2 import Environment, StrictUndefined
from pydantic import BaseModel, Field

from app.ai import llm, usage_log
from app.ai.schemas import (
    OfferAnalysis,
    ProjectChoice,
    Rewrite,
    SkillGroupOut,
    SkillItem,
    TargetPlan,
    Translation,
)
from app.models.content import (
    CVContent,
    ExperienceSection,
    ProjectItem,
    ProjectsSection,
    SkillGroup,
    SkillsSection,
)
from app.models.library import Library
from app.offer.fetch import Offer
from app.paths import DRAFTS_DIR, PROMPTS_DIR
from app.services.library_import import normalize, split_skills

Emit = Callable[[dict[str, Any]], Awaitable[None]]
Lang = Literal["fr", "en"]
LANG_NAME = {"fr": "français", "en": "anglais"}
TEAM_TAG = {
    "fr": {"seul": "Projet individuel", "binôme": "En binôme", "équipe": "En équipe"},
    "en": {"seul": "Individual project", "binôme": "Pair project", "équipe": "Team project"},
}


# ─── La proposition ──────────────────────────────────────────────────────────


class Coverage(BaseModel):
    score: int = Field(description="Part pondérée des mots-clés de l'offre présents, sur 100.")
    present: list[str]
    absent: list[str]


class Chip(BaseModel):
    """Une compétence d'un groupe proposé.

    ``kept`` : déjà dans ce groupe ; ``added`` : connue, ajoutée à ce groupe ;
    ``pending`` : absente du profil, à confirmer ; ``removed`` : retirée du CV.
    """

    text: str
    state: Literal["kept", "added", "pending", "removed"]


class Line(BaseModel):
    """Une puce proposée pour une expérience, avec la puce dont elle vient."""

    text: str
    source: str = ""
    # Tirée de la réserve de la bibliothèque (pas sur le CV de départ).
    reserve: bool = False


class Change(BaseModel):
    id: str
    group: Literal["En-tête", "Compétences", "Projets", "Expérience", "Langue"]
    label: str
    kind: Literal["replace", "add", "remove"]
    before: str = ""
    # Le texte proposé ; pour une expérience, une puce par ligne.
    after: str = ""
    warnings: list[str] = Field(default_factory=list)
    # Informations utiles pour décider (écritures changées…).
    notes: list[str] = Field(default_factory=list)
    chips: list[Chip] = Field(default_factory=list)
    lines: list[Line] = Field(default_factory=list)
    # Termes absents du profil : la case part décochée, l'accepter les confirme.
    pending: list[str] = Field(default_factory=list)


class SkillSlot(BaseModel):
    """Un groupe de compétences du plan : le groupe du CV qu'il remplace, son changement."""

    label: str
    source: int | None = None
    change: str | None = None


class Draft(BaseModel):
    id: str
    # La proposition relancée dont celle-ci est issue.
    parent: str | None = None
    source: str
    created_at: datetime
    language: Lang
    source_language: Lang
    options: dict[str, Any] = Field(default_factory=dict)
    offer_text: str
    offer_url: str | None = None
    analysis: OfferAnalysis
    plan: TargetPlan
    changes: list[Change]
    skills_layout: list[SkillSlot] = Field(default_factory=list)
    # Clé de chaque projet du CV source, dans son ordre.
    source_keys: list[str] = Field(default_factory=list)
    # Projets connus (bibliothèque validée + CV), par clé.
    projects: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # Traductions par chemin dans le CV source (``section/<id>/items/0/title``…).
    translation: dict[str, str] = Field(default_factory=dict)
    # Le texte d'origine de chaque traduction, pour la relire et la retoucher.
    translation_source: dict[str, str] = Field(default_factory=dict)
    score_before: Coverage
    score_after: Coverage
    model: str = ""
    seconds: float = 0
    tokens: dict[str, int] = Field(default_factory=dict)


@dataclass
class TargetOptions:
    projects_count: int | None = None
    language: Literal["auto", "fr", "en"] = "auto"


# ─── Le profil connu (bibliothèque validée + CV source) ──────────────────────


@dataclass
class Knowledge:
    projects: dict[str, dict[str, Any]] = field(default_factory=dict)
    skills: list[dict[str, Any]] = field(default_factory=list)
    allowed: set[str] = field(default_factory=set)
    aliases: dict[str, set[str]] = field(default_factory=dict)

    def allow(self, name: str, aliases: list[str] | None = None) -> None:
        names = [name, *(aliases or [])]
        keys = {normalize(n) for n in names}
        # « HTML/CSS » couvre aussi « HTML » et « CSS ».
        keys.update(normalize(part) for n in names for part in n.split("/"))
        keys.discard("")
        self.allowed.update(keys)
        for key in keys:
            self.aliases.setdefault(key, set()).update(names)

    def knows(self, term: str) -> bool:
        """La compétence est-elle dans le profil (pluriel et listes compris) ?"""
        key = normalize(term)
        if not key:
            return False
        if key in self.allowed or (key.endswith("s") and key[:-1] in self.allowed):
            return True
        parts = split_skills(term)
        return len(parts) > 1 and all(self.knows(part) for part in parts)


def source_projects(content: CVContent) -> list[ProjectItem]:
    for section in content.sections:
        if isinstance(section, ProjectsSection):
            return section.items
    return []


def project_key(index: int, item: ProjectItem, projects: dict[str, dict[str, Any]]) -> str:
    """La clé d'un projet du CV : son entrée de bibliothèque si on la retrouve, sinon ``cv-<n>``."""
    if item.library_id and item.library_id in projects:
        return item.library_id
    for key, info in projects.items():
        if key.startswith("cv-"):
            continue
        same_link = (
            item.link
            and info.get("link")
            and item.link.rstrip("/") == str(info["link"]).rstrip("/")
        )
        if same_link or normalize(info["title"]) == normalize(item.title):
            return key
    return f"cv-{index}"


def build_knowledge(content: CVContent, library: Library) -> Knowledge:
    know = Knowledge()
    for project in library.projects:
        if project.status == "validé":
            know.projects[project.id] = {
                "title": project.title,
                "date": project.date,
                "team": project.team,
                "context": project.context,
                "techs": project.techs,
                "description": project.description,
                "bullets": project.bullets,
                "notes": project.notes[:1500],
                # Un dépôt privé ne s'ouvre pas pour un recruteur : pas de lien dans le CV.
                "link": None if project.private else project.link,
            }
    for index, item in enumerate(source_projects(content)):
        key = project_key(index, item, know.projects)
        if key not in know.projects:
            know.projects[key] = {
                "title": item.title,
                "date": item.date,
                "tag": item.tag,
                "techs": [],
                "description": item.description,
                "bullets": [],
                "notes": "",
                "link": item.link,
            }
    for skill in library.skills:
        if skill.status == "validé":
            know.skills.append(
                {
                    "name": skill.name,
                    "category": skill.category,
                    "aliases": skill.aliases,
                    "level": skill.level,
                    "evidence": skill.evidence,
                }
            )
            know.allow(skill.name, skill.aliases)
    for section in content.sections:
        if isinstance(section, SkillsSection):
            for group in section.items:
                for name in split_skills(group.text):
                    if not know.knows(name):
                        know.skills.append(
                            {"name": name, "category": group.label, "aliases": [], "level": None}
                        )
                    know.allow(name)
    return know


@dataclass
class Pool:
    """Les puces possibles d'une expérience du CV : les siennes, puis sa réserve."""

    ref: str
    section: str
    index: int
    title: str
    place: str
    cv: list[str]
    reserve: list[str]

    def lookup(self, ref: str) -> tuple[str, bool] | None:
        """(texte, vient de la réserve) de la puce « E1.3 »."""
        match = re.fullmatch(rf"{re.escape(self.ref)}\.(\d+)", ref.strip())
        if not match:
            return None
        n = int(match.group(1)) - 1
        everything = self.cv + self.reserve
        return (everything[n], n >= len(self.cv)) if 0 <= n < len(everything) else None


def experience_pools(content: CVContent, library: Library) -> list[Pool]:
    pools = []
    n = 0
    for section in content.sections:
        if not (isinstance(section, ExperienceSection) and section.visible):
            continue
        for i, entry in enumerate(section.items):
            n += 1
            mine = {normalize(b) for b in entry.bullets}
            reserve: list[str] = []
            for experience in library.experiences:
                if experience.status != "validé" or normalize(experience.title) != normalize(
                    entry.title
                ):
                    continue
                if experience.place and normalize(experience.place) != normalize(entry.place):
                    continue
                for bullet in experience.bullets:
                    if bullet.strip() and normalize(bullet) not in mine:
                        mine.add(normalize(bullet))
                        reserve.append(bullet.strip())
            pools.append(
                Pool(f"E{n}", section.id, i, entry.title, entry.place, list(entry.bullets), reserve)
            )
    return pools


# ─── Textes envoyés au modèle ────────────────────────────────────────────────

_ENV = Environment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)


def load_prompt(name: str, **values: Any) -> tuple[str, str]:
    """(consigne système, message) d'un fichier prompts/<name>.md."""
    raw = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    system, _, message = raw.partition("---message---")
    return _ENV.from_string(system).render(**values).strip(), _ENV.from_string(message).render(
        **values
    ).strip()


def profile_text(content: CVContent) -> str:
    """Le CV en texte lisible, sans le nom ni les coordonnées (inutiles au modèle)."""
    lines = [f"Titre : {content.header.headline}", f"Accroche : {content.header.summary}"]
    for section in content.sections:
        if not section.visible:
            continue
        lines.append(f"\n## {section.title}")
        if section.kind == "education":
            lines += [f"- {i.title}, {i.place} ({i.dates}). {i.description}" for i in section.items]
        elif section.kind == "skills":
            lines += [f"- {g.label} : {g.text}" for g in section.items]
        elif section.kind == "experience":
            for item in section.items:
                lines.append(f"- {item.title}, {item.place} ({item.dates}) {item.tag}".rstrip())
                lines += [f"  • {b}" for b in item.bullets]
        elif section.kind == "projects":
            lines += [f"- {p.title} ({p.date}) : {p.description}" for p in section.items]
        elif section.kind == "languages":
            lines += [f"- {lang.name} : {lang.level}" for lang in section.items]
        elif section.kind == "grid":
            lines.append(", ".join(i.text for i in section.items))
        elif section.kind == "bullets":
            lines += [f"- {b}" for b in section.items]
    return "\n".join(lines)


def skills_text(know: Knowledge) -> str:
    groups: dict[str, list[str]] = {}
    for skill in know.skills:
        extra = [f"aussi : {', '.join(skill['aliases'])}"] if skill["aliases"] else []
        if skill.get("level"):
            extra.append(skill["level"])
        if skill.get("evidence"):
            extra.append(f"où : {skill['evidence']}")
        label = skill["name"] + (f" ({' ; '.join(extra)})" if extra else "")
        groups.setdefault(skill["category"], []).append(label)
    return "\n".join(f"- {cat} : {', '.join(names)}" for cat, names in groups.items())


def projects_text(know: Knowledge, keys: list[str] | None = None) -> str:
    out = []
    for key, p in know.projects.items():
        if keys is not None and key not in keys:
            continue
        parts = [f"[{key}] {p['title']} ({p.get('date') or 'date ?'})"]
        if p.get("team"):
            parts.append(f"cadre : {p['team']}")
        if p.get("techs"):
            parts.append("technos : " + ", ".join(p["techs"]))
        out.append(" ; ".join(parts))
        if p.get("description"):
            out.append(f"  description : {p['description']}")
        out += [f"  • {b}" for b in p.get("bullets", [])]
        if p.get("notes"):
            out.append(f"  notes : {p['notes']}")
    return "\n".join(out)


def experiences_text(pools: list[Pool]) -> str:
    out = []
    for pool in pools:
        if not pool.cv:
            continue
        out.append(f"## {pool.ref} : {pool.title}, {pool.place} (garder {len(pool.cv)} puces)")
        for n, bullet in enumerate(pool.cv + pool.reserve, start=1):
            mark = " (réserve)" if n > len(pool.cv) else ""
            out.append(f"{pool.ref}.{n} : {bullet}{mark}")
    return "\n".join(out)


def analysis_text(analysis: OfferAnalysis) -> str:
    keywords = ", ".join(f"{k.term} ({k.importance})" for k in analysis.keywords)
    return (
        f"Poste : {analysis.job_title} ({analysis.company}, {analysis.location})\n"
        f"Mission : {analysis.summary}\n"
        f"Technos : {', '.join(analysis.technologies)}\nOutils : {', '.join(analysis.tools)}\n"
        f"Méthodes : {', '.join(analysis.methods)}\nCompétences : {', '.join(analysis.skills)}\n"
        f"Soft skills : {', '.join(analysis.soft_skills)}\n"
        f"Mots-clés (importance 3 = indispensable) : {keywords}"
    )


# ─── Vérifications et score ──────────────────────────────────────────────────


def flatten(text: str) -> str:
    """Texte normalisé pour chercher des mots-clés : minuscules, sans accents ni ponctuation."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    plain = re.sub(r"\*\*|__", "", plain)
    # Le point d'une fin de phrase disparaît, celui de « Node.js » reste.
    plain = re.sub(r"\.(\s|$)", r" \1", plain)
    plain = re.sub(r"[^a-z0-9+#.]+", " ", plain)
    return " " + re.sub(r"\s+", " ", plain).strip() + " "


def _stem(flat: str) -> str:
    """Le pluriel ne compte pas : « revues de code » trouve « revue de code »."""
    return " ".join(w[:-1] if len(w) > 3 and w[-1] in "sx" else w for w in flat.split())


def _hay(text: str) -> str:
    return f" {_stem(flatten(text))} "


def variants(term: str, know: Knowledge) -> set[str]:
    """Les écritures qui valent ce mot-clé : « RAG (Retrieval…) » vaut « RAG » ou « Retrieval… »."""
    found = {term}
    match = re.match(r"^(.*?)\s*\((.*)\)$", term)
    if match:
        found |= {match.group(1), match.group(2)}
    found |= {part for t in list(found) for part in t.split(" / ")}
    for t in list(found):
        found |= know.aliases.get(normalize(t), set())
    return {t for t in found if t.strip()}


def found(term: str, text: str, know: Knowledge) -> bool:
    """Le mot-clé (ou une autre de ses écritures) figure-t-il dans le texte ?"""
    hay = _hay(text)
    return any(n.strip() and n in hay for n in (_hay(v) for v in variants(term, know)))


def coverage(analysis: OfferAnalysis, text: str, know: Knowledge) -> Coverage:
    present, absent, got, total = [], [], 0, 0
    for keyword in analysis.keywords:
        total += keyword.importance
        if found(keyword.term, text, know):
            got += keyword.importance
            present.append(keyword.term)
        else:
            absent.append(keyword.term)
    return Coverage(score=round(100 * got / total) if total else 0, present=present, absent=absent)


def new_terms(
    before: str,
    after: str,
    analysis: OfferAnalysis,
    know: Knowledge,
    extra: str = "",
    translating: bool = False,
) -> list[str]:
    """Les mots-clés de l'offre qu'apporte ``after`` et que le profil ne contient pas.

    Seuls comptent ceux absents de ``before`` et de ``extra``. Quand le texte
    change de langue, seuls les noms de technos et d'outils (les mêmes dans
    toutes les langues) peuvent être comparés.
    """
    out = []
    old, new, info = _hay(before), _hay(after), _hay(extra)
    for keyword in analysis.keywords:
        if translating and keyword.category not in ("techno", "outil"):
            continue
        term = _hay(keyword.term)
        if term.strip() and term in new and term not in old and term not in info:
            if not know.knows(keyword.term):
                out.append(keyword.term)
    return out


def lost_terms(
    before: str, after: str, analysis: OfferAnalysis, know: Knowledge, translating: bool = False
) -> list[str]:
    """Les compétences du profil et les mots-clés de l'offre que la reformulation fait disparaître.

    En traduction, seuls les noms de technos et d'outils de l'offre sont comparés.
    """
    names = {
        k.term for k in analysis.keywords if not translating or k.category in ("techno", "outil")
    }
    if not translating:
        names |= {s["name"] for s in know.skills}
    lost = [n for n in names if found(n, before, know) and not found(n, after, know)]
    return sorted(lost, key=str.lower)


def lost_message(terms: list[str]) -> list[str]:
    return (
        [f"Disparaît de ce texte : {', '.join(terms)}. Vérifie que c'est voulu."] if terms else []
    )


def confirm_message(term: str) -> str:
    return (
        f"« {term} » n'est pas dans ton profil : en acceptant, tu confirmes que c'est vrai "
        "(il rejoint ta bibliothèque)."
    )


def length_warning(before: str, after: str) -> list[str]:
    """Une alerte quand le texte s'allonge nettement : le CV doit tenir sur une page."""
    if before and len(after) > 1.3 * len(before):
        more = round(100 * (len(after) / len(before) - 1))
        return [f"Plus long que l'original (+{more} %) : le CV risque de dépasser la page."]
    return []


def plain_marks(source: str, text: str) -> str:
    """Le texte sans le gras ni l'italique que l'IA aurait ajoutés."""
    if "**" not in source:
        text = text.replace("**", "")
    if "__" not in source:
        text = text.replace("__", "")
    return text.strip()


def _dedup(group: SkillGroup, taken: set[str]) -> SkillGroup | None:
    """Le groupe sans les compétences déjà montrées ailleurs (None s'il n'en reste rien)."""
    items = split_skills(group.text)
    rest = [x for x in items if normalize(x) not in taken]
    if len(rest) == len(items):
        return group
    return SkillGroup(label=group.label, text=", ".join(rest) + ".") if rest else None


# ─── Traduction ──────────────────────────────────────────────────────────────

_FIELDS = {
    "education": ("title", "dates", "description"),
    "skills": ("label", "text"),
    "grid": ("text",),
    "languages": ("name", "level"),
    "experience": ("title", "tag", "dates"),
    "projects": ("title", "tag", "date", "description"),
}


def translatable(
    content: CVContent, added: list[str], projects: dict[str, dict[str, Any]]
) -> dict[str, str]:
    """Tous les textes du CV à traduire, par chemin stable, plus le titre des projets ajoutés.

    Les coordonnées ne partent que si elles ne contiennent ni chiffres, ni « @ »,
    ni lien (« Bordeaux, France », « Permis B »).
    """
    out = {"header/headline": content.header.headline, "header/summary": content.header.summary}
    for li, line in enumerate(content.header.contact_lines):
        for ii, item in enumerate(line):
            if item.label:
                out[f"contact/{li}/{ii}/label"] = item.label
            if not item.url and not re.search(r"\d|@", item.text):
                out[f"contact/{li}/{ii}/text"] = item.text
    for section in content.sections:
        out[f"section/{section.id}/title"] = section.title
        base = f"section/{section.id}/items"
        for i, item in enumerate(section.items):
            if section.kind == "bullets":
                out[f"{base}/{i}"] = item
                continue
            for name in _FIELDS[section.kind]:
                out[f"{base}/{i}/{name}"] = getattr(item, name)
            if section.kind == "experience":
                out |= {f"{base}/{i}/bullets/{j}": b for j, b in enumerate(item.bullets)}
    for key in added:
        out[f"project/{key}/title"] = projects[key]["title"]
        out[f"project/{key}/date"] = projects[key].get("date") or ""
    return {k: v for k, v in out.items() if v and v.strip()}


def _apply_translation(content: CVContent, translation: dict[str, str]) -> None:
    for path, text in translation.items():
        parts = path.split("/")
        try:
            if parts[0] == "header":
                setattr(content.header, parts[1], text)
            elif parts[0] == "contact":
                setattr(content.header.contact_lines[int(parts[1])][int(parts[2])], parts[3], text)
            elif parts[0] == "section":
                section = next(s for s in content.sections if s.id == parts[1])
                if parts[2] == "title":
                    section.title = text
                elif len(parts) == 4:
                    section.items[int(parts[3])] = text
                elif len(parts) == 5:
                    setattr(section.items[int(parts[3])], parts[4], text)
                else:
                    section.items[int(parts[3])].bullets[int(parts[5])] = text
        except (IndexError, StopIteration, ValueError, AttributeError):
            # Un chemin qui ne correspond plus à rien (CV source modifié depuis).
            continue


# ─── Le plan, vérifié ────────────────────────────────────────────────────────


def _match_group(group: SkillGroupOut, old: list[SkillGroup], used: set[int]) -> int | None:
    """Le groupe du CV que ce groupe remplace : même nom, sinon le plus de compétences communes."""
    for i, g in enumerate(old):
        if i not in used and normalize(g.label) == normalize(group.label):
            return i
    items = {normalize(x.source or x.text) for x in group.items}
    best, best_score = None, 0.0
    for i, g in enumerate(old):
        if i in used:
            continue
        theirs = {normalize(x) for x in split_skills(g.text)}
        if items and theirs:
            score = len(items & theirs) / min(len(items), len(theirs))
            if score >= 0.5 and score > best_score:
                best, best_score = i, score
    return best


def _clean_plan(plan: TargetPlan, know: Knowledge, source_keys: list[str], count: int) -> None:
    """Doublons de compétences et projets inconnus retirés du plan."""
    seen: set[str] = set()
    for group in plan.skill_groups:
        kept: list[SkillItem] = []
        for item in group.items:
            item.text = item.text.strip()
            if item.text and normalize(item.text) not in seen:
                seen.add(normalize(item.text))
                kept.append(item)
        group.items = kept
    plan.skill_groups = [g for g in plan.skill_groups if g.items]
    chosen: list[ProjectChoice] = []
    for choice in plan.projects:
        if choice.id in know.projects and all(c.id != choice.id for c in chosen):
            chosen.append(choice)
    if not chosen:
        chosen = [ProjectChoice(id=key, reason="Projet du CV d'origine.") for key in source_keys]
    plan.projects = chosen[:count]


def _pending(item: SkillItem, know: Knowledge, keywords: set[str], translating: bool) -> bool:
    """À confirmer : ni l'écriture ni le nom d'origine ne sont dans le profil.

    Un nom d'origine connu couvre une écriture différente (traduction,
    variante), sauf si cette écriture est un mot-clé de l'offre absent du
    profil : « Docker » ne devient pas « Kubernetes » sans confirmation.
    """
    if know.knows(item.text):
        return False
    if item.source and know.knows(item.source):
        return not translating and normalize(item.text) in keywords
    return True


def _chosen_lines(pools: list[Pool], rewrite: Rewrite) -> dict[str, list[Line]]:
    """Les puces retenues pour chaque expérience, autant que sur le CV de départ."""
    by_exp = {e.exp.strip(): e.bullets for e in rewrite.experiences}
    out: dict[str, list[Line]] = {}
    for pool in pools:
        picked: list[Line] = []
        used: set[str] = set()
        for choice in by_exp.get(pool.ref, []):
            hit = pool.lookup(choice.ref)
            if hit is None or choice.ref.strip() in used or len(picked) >= len(pool.cv):
                continue
            source, reserve = hit
            used.add(choice.ref.strip())
            picked.append(
                Line(
                    text=plain_marks(source, choice.text) or source, source=source, reserve=reserve
                )
            )
        # Le modèle en a rendu moins : on complète avec les puces du CV, dans l'ordre.
        for j, bullet in enumerate(pool.cv):
            if len(picked) >= len(pool.cv):
                break
            if f"{pool.ref}.{j + 1}" not in used:
                picked.append(Line(text=bullet, source=bullet))
        out[pool.ref] = picked
    return out


def build_changes(
    content: CVContent,
    analysis: OfferAnalysis,
    plan: TargetPlan,
    know: Knowledge,
    source_keys: list[str],
    pools: list[Pool],
    chosen: dict[str, list[Line]],
    rewritten: dict[str, str],
    proj_refs: dict[str, str],
    translating: bool = False,
) -> tuple[list[Change], list[SkillSlot]]:
    changes: list[Change] = []
    header = content.header
    profile = profile_text(content)

    def sentence(
        id_: str,
        group: Any,
        label: str,
        before: str,
        after: str,
        extra: str = "",
        kind: Any = "replace",
    ) -> None:
        terms = new_terms(before, after, analysis, know, extra, translating)
        changes.append(
            Change(
                id=id_,
                group=group,
                label=label,
                kind=kind,
                before=before,
                after=after,
                pending=terms,
                warnings=[confirm_message(t) for t in terms]
                + lost_message(lost_terms(before, after, analysis, know, translating))
                + length_warning(before, after),
            )
        )

    headline = plain_marks(header.headline, plan.headline)
    if headline and headline != header.headline:
        sentence("headline", "En-tête", "Titre", header.headline, headline, profile)
    summary = plain_marks(header.summary, plan.summary)
    if summary and summary != header.summary:
        sentence("summary", "En-tête", "Accroche", header.summary, summary, profile)

    # Compétences : un changement par groupe, ses compétences en étiquettes.
    skills = next((s for s in content.sections if isinstance(s, SkillsSection)), None)
    old = skills.items if skills else []
    keywords = {normalize(k.term) for k in analysis.keywords}
    states = {
        id(item): _pending(item, know, keywords, translating)
        for group in plan.skill_groups
        for item in group.items
    }
    shown = {
        normalize(x)
        for group in plan.skill_groups
        for item in group.items
        if not states[id(item)]
        for x in (item.source, item.text)
        if x
    }
    used: set[int] = set()
    layout: list[SkillSlot] = []
    for n, group in enumerate(plan.skill_groups):
        src = _match_group(group, old, used)
        mine = {normalize(x) for x in split_skills(old[src].text)} if src is not None else set()
        chips: list[Chip] = []
        renamed: list[str] = []
        for item in group.items:
            if states[id(item)]:
                chips.append(Chip(text=item.text, state="pending"))
                continue
            here = normalize(item.text) in mine or normalize(item.source) in mine
            chips.append(Chip(text=item.text, state="kept" if here else "added"))
            if item.source and normalize(item.source) != normalize(item.text):
                renamed.append(f"{item.source} → {item.text}")
        if src is not None:
            used.add(src)
            chips += [
                Chip(text=x, state="removed")
                for x in split_skills(old[src].text)
                if normalize(x) not in shown
            ]
        text = ", ".join(c.text for c in chips if c.state in ("kept", "added"))
        text = f"{text}." if text else ""
        pending = [c.text for c in chips if c.state == "pending"]
        notes = [f"Écrites autrement : {' ; '.join(renamed)}."] if renamed else []
        change_id = f"skills-{n}"
        if src is None:
            changes.append(
                Change(
                    id=change_id,
                    group="Compétences",
                    label=group.label,
                    kind="add",
                    after=text,
                    chips=chips,
                    pending=pending,
                    notes=notes,
                )
            )
        elif old[src].text != text or old[src].label != group.label or pending:
            label = (
                group.label
                if old[src].label == group.label
                else f"{old[src].label} → {group.label}"
            )
            changes.append(
                Change(
                    id=change_id,
                    group="Compétences",
                    label=label,
                    kind="replace",
                    before=old[src].text,
                    after=text,
                    chips=chips,
                    pending=pending,
                    notes=notes,
                )
            )
        else:
            change_id = None
        layout.append(SkillSlot(label=group.label, source=src, change=change_id))
    for i, g in enumerate(old):
        if i not in used:
            items = split_skills(g.text)
            kept = [x for x in items if normalize(x) in shown]
            changes.append(
                Change(
                    id=f"skills-remove-{i}",
                    group="Compétences",
                    label=g.label,
                    kind="remove",
                    before=g.text,
                    chips=[
                        Chip(text=x, state="removed") for x in items if normalize(x) not in shown
                    ],
                    notes=[f"Gardées dans un autre groupe : {', '.join(kept)}."] if kept else [],
                )
            )

    # Expériences : les puces retenues (réserve comprise), adaptées.
    for pool in pools:
        lines = chosen.get(pool.ref, [])
        before, after = "\n".join(pool.cv), "\n".join(line.text for line in lines)
        if not lines or after == before:
            continue
        terms: list[str] = []
        lost: list[str] = []
        for line in lines:
            for term in new_terms(line.source, line.text, analysis, know, "", translating):
                if term not in terms:
                    terms.append(term)
            lost += [
                t
                for t in lost_terms(line.source, line.text, analysis, know, translating)
                if t not in lost
            ]
        changes.append(
            Change(
                id=f"exp-{pool.section}-{pool.index}",
                group="Expérience",
                label=pool.title,
                kind="replace",
                before=before,
                after=after,
                lines=lines,
                pending=terms,
                warnings=[confirm_message(t) for t in terms]
                + lost_message(lost)
                + length_warning(before, after),
            )
        )

    # Projets : ajoutés, gardés (description adaptée), retirés.
    current = source_projects(content)
    keys = [c.id for c in plan.projects]
    ref_of = {key: ref for ref, key in proj_refs.items()}
    for key in keys:
        info = know.projects[key]
        original = info.get("description") or ""
        description = plain_marks(original, rewritten.get(ref_of.get(key, ""), "") or original)
        extra = json.dumps(info, ensure_ascii=False)
        if key in source_keys:
            before = current[source_keys.index(key)].description
            if description and description != before:
                sentence(f"project-{key}", "Projets", info["title"], before, description, extra)
        else:
            sentence(
                f"project-{key}", "Projets", info["title"], original, description, extra, "add"
            )
            changes[-1].before = ""
    for i, key in enumerate(source_keys):
        if key not in keys:
            changes.append(
                Change(
                    id=f"project-remove-{key}",
                    group="Projets",
                    label=current[i].title,
                    kind="remove",
                    before=current[i].description,
                )
            )
    return changes, layout


def default_accepted(draft: Draft) -> dict[str, str]:
    """Les choix de départ : tout, sauf les phrases qui ont un terme à confirmer."""
    return {c.id: c.after for c in draft.changes if not (c.pending and c.group != "Compétences")}


# ─── Le pipeline ─────────────────────────────────────────────────────────────


async def run(
    source: str,
    content: CVContent,
    library: Library,
    offer: Offer,
    options: TargetOptions,
    provider: llm.LLMProvider,
    emit: Emit,
    analysis: OfferAnalysis | None = None,
    parent: str | None = None,
) -> Draft:
    """Une proposition complète ; avec ``analysis``, l'offre n'est pas réanalysée (relance)."""
    know = build_knowledge(content, library)
    pools = experience_pools(content, library)
    source_keys = [project_key(i, p, know.projects) for i, p in enumerate(source_projects(content))]
    total = llm.Usage()
    seconds = 0.0
    model = ""

    async def notify(message: str) -> None:
        await emit({"type": "wait", "message": message})

    async def step(label: str, prompt: str, expected: type, **values: Any) -> Any:
        nonlocal seconds, model
        await emit({"type": "step", "label": label})
        system, message = load_prompt(prompt, **values)
        result = await llm.generate(provider, system, message, expected, notify)
        total.add(result.usage)
        seconds += result.seconds
        model = result.model
        usage_log.record(provider.name, result.model, result.usage, label)
        return result.data

    if analysis is None:
        analysis = await step("Analyse de l'offre", "analyse", OfferAnalysis, offer=offer.text)
        if not analysis.is_job_offer:
            raise llm.LLMError(
                "Ce texte ne ressemble pas à une offre d'emploi : "
                "colle le texte de l'offre elle-même."
            )

    language: Lang = (
        options.language
        if options.language != "auto"
        else ("en" if analysis.offer_language == "en" else "fr")
    )
    translating = language != content.language
    count = min(options.projects_count or len(source_keys) or 3, len(know.projects))

    plan: TargetPlan = await step(
        "Compétences et projets",
        "plan",
        TargetPlan,
        analysis=analysis_text(analysis),
        profile=profile_text(content),
        skills=skills_text(know),
        projects=projects_text(know),
        projects_count=count,
        language_name=LANG_NAME[language],
    )
    _clean_plan(plan, know, source_keys, count)
    keys = [c.id for c in plan.projects]

    proj_refs = {f"P{n + 1}": key for n, key in enumerate(keys)}
    texts = [
        f"{ref} : {know.projects[key].get('description') or '(à écrire)'}"
        for ref, key in proj_refs.items()
    ]
    rewrite = Rewrite()
    if texts or any(pool.cv for pool in pools):
        rewrite = await step(
            "Formulations",
            "reecriture",
            Rewrite,
            analysis=analysis_text(analysis),
            experiences=experiences_text(pools) or "(aucune)",
            texts="\n".join(texts) or "(aucune)",
            projects=projects_text(know, keys),
            language_name=LANG_NAME[language]
            + (" : traduis tous les textes, même ceux que tu n'adaptes pas" if translating else ""),
        )
    chosen = _chosen_lines(pools, rewrite)
    rewritten = {t.ref.strip(): t.text for t in rewrite.texts}
    changes, layout = build_changes(
        content, analysis, plan, know, source_keys, pools, chosen, rewritten, proj_refs, translating
    )

    translation: dict[str, str] = {}
    translation_source: dict[str, str] = {}
    if translating:
        todo = translatable(content, [k for k in keys if k not in source_keys], know.projects)
        # Les étiquettes des groupes proposés aussi : le modèle y laisse parfois
        # des compétences dans la langue du profil.
        chips = {
            f"chip/{c.id}/{n}": chip
            for c in changes
            if c.group == "Compétences" and c.kind != "remove"
            for n, chip in enumerate(c.chips)
            if chip.state != "removed"
        }
        todo |= {path: chip.text for path, chip in chips.items()}
        ref_paths = {f"T{n + 1}": path for n, path in enumerate(todo)}
        translated: Translation = await step(
            f"Traduction en {LANG_NAME[language]}",
            "traduction",
            Translation,
            target_name=LANG_NAME[language],
            texts="\n".join(f"{ref} : {todo[path]}" for ref, path in ref_paths.items()),
        )
        translation = {ref_paths[t.ref]: t.text for t in translated.texts if t.ref in ref_paths}
        for path in [p for p in translation if p.startswith("chip/")]:
            chips[path].text = translation.pop(path).strip().rstrip(".")
        for change in changes:
            if change.chips and change.kind != "remove":
                shown = [c.text for c in change.chips if c.state in ("kept", "added")]
                change.after = f"{', '.join(shown)}." if shown else ""
                change.pending = [c.text for c in change.chips if c.state == "pending"]
        translation_source = {path: todo[path] for path in translation}
        changes.append(
            Change(
                id="translation",
                group="Langue",
                label=f"Le reste du CV en {LANG_NAME[language]} ({len(translation)} textes)",
                kind="replace",
                before=LANG_NAME[content.language].capitalize(),
                after=LANG_NAME[language].capitalize(),
            )
        )

    # Ce qui figure déjà dans le profil n'est pas « manquant » (« English » quand
    # le CV dit « Anglais : courant »), ni ce qui est déjà proposé à confirmer.
    known = "\n".join(
        [profile_text(content), *translation.values(), *(s["name"] for s in know.skills)]
    )
    proposed = {normalize(t) for c in changes for t in c.pending}
    plan.missing = [
        m
        for m in plan.missing
        if not found(m.term, known, know) and normalize(m.term) not in proposed
    ]

    draft = Draft(
        id=uuid.uuid4().hex[:12],
        parent=parent,
        source=source,
        created_at=datetime.now(UTC).replace(microsecond=0),
        language=language,
        source_language=content.language,
        options={"projects_count": options.projects_count, "language": options.language},
        offer_text=offer.text,
        offer_url=offer.url,
        analysis=analysis,
        plan=plan,
        changes=changes,
        skills_layout=layout,
        source_keys=source_keys,
        projects=know.projects,
        translation=translation,
        translation_source=translation_source,
        score_before=coverage(analysis, profile_text(content), know),
        score_after=Coverage(score=0, present=[], absent=[]),
        model=model,
        seconds=round(seconds, 1),
        tokens={
            "input": total.input_tokens,
            "output": total.output_tokens,
            "thinking": total.thinking_tokens,
        },
    )
    draft.score_after = coverage(
        analysis, profile_text(apply(content, draft, default_accepted(draft))), know
    )
    save_draft(draft)
    return draft


# ─── Appliquer les changements acceptés ──────────────────────────────────────


def unconfirmed(draft: Draft, accepted: dict[str, str], confirmed: list[str]) -> list[str]:
    """Les termes à confirmer présents dans un texte accepté sans avoir été confirmés."""
    yes = {normalize(t) for t in confirmed}
    know = Knowledge()
    out = []
    for change in draft.changes:
        text = accepted.get(change.id)
        if text is None:
            continue
        for term in change.pending:
            if normalize(term) not in yes and found(term, text, know) and term not in out:
                out.append(term)
    return out


def apply(
    content: CVContent,
    draft: Draft,
    accepted: dict[str, str],
    edits: dict[str, str] | None = None,
) -> CVContent:
    """Le CV source avec les changements acceptés (``accepted`` : id → texte final).

    La traduction, si elle est acceptée (avec les retouches ``edits``, par
    chemin), s'applique d'abord au CV source ; les changements acceptés passent
    ensuite par-dessus.
    """
    out = content.model_copy(deep=True)
    translated = "translation" in accepted and bool(draft.translation)
    tr = {**draft.translation, **{k: v for k, v in (edits or {}).items() if k in draft.translation}}
    if translated:
        _apply_translation(out, tr)
        out.language = draft.language

    if "headline" in accepted:
        out.header.headline = accepted["headline"]
    if "summary" in accepted:
        out.header.summary = accepted["summary"]

    skills = next((s for s in out.sections if isinstance(s, SkillsSection)), None)
    if skills is not None:
        old = skills.items
        new = {
            slot.change: accepted[slot.change]
            for slot in draft.skills_layout
            if slot.change in accepted and accepted[slot.change].strip()
        }
        # Un groupe du CV gardé à côté des nouveaux perd ce qu'ils montrent déjà.
        taken = {normalize(x) for text in new.values() for x in split_skills(text)}
        groups: list[SkillGroup] = []
        used: set[int] = set()
        for slot in draft.skills_layout:
            if slot.source is not None and slot.source >= len(old):
                continue
            if slot.change in new:
                groups.append(SkillGroup(label=slot.label, text=new[slot.change]))
            elif slot.source is not None and (kept := _dedup(old[slot.source], taken)):
                groups.append(kept)
            if slot.source is not None:
                used.add(slot.source)
        for i, g in enumerate(old):
            if (
                i not in used
                and f"skills-remove-{i}" not in accepted
                and (kept := _dedup(g, taken))
            ):
                groups.append(kept)
        skills.items = groups

    for section in out.sections:
        if isinstance(section, ExperienceSection):
            for i, item in enumerate(section.items):
                text = accepted.get(f"exp-{section.id}-{i}")
                if text is not None:
                    item.bullets = [line.strip() for line in text.split("\n") if line.strip()]

    projects = next((s for s in out.sections if isinstance(s, ProjectsSection)), None)
    if projects is not None:
        current = projects.items
        keys = [c.id for c in draft.plan.projects]
        names = tr if translated else {}
        placed: list[ProjectItem] = []
        for key in keys:
            change = f"project-{key}"
            if key in draft.source_keys:
                index = draft.source_keys.index(key)
                if index >= len(current):
                    continue
                item = current[index].model_copy(deep=True)
                if change in accepted:
                    item.description = accepted[change]
                placed.append(item)
            elif change in accepted:
                info = draft.projects[key]
                placed.append(
                    ProjectItem(
                        title=names.get(f"project/{key}/title", info["title"]),
                        tag=TEAM_TAG[out.language].get(info.get("team") or "", info.get("tag", "")),
                        date=names.get(f"project/{key}/date", info.get("date") or ""),
                        description=accepted[change],
                        link=info.get("link"),
                        library_id=None if key.startswith("cv-") else key,
                    )
                )
        placed += [
            current[i]
            for i, key in enumerate(draft.source_keys)
            if i < len(current) and key not in keys and f"project-remove-{key}" not in accepted
        ]
        projects.items = placed
    return out


# ─── Brouillons ──────────────────────────────────────────────────────────────


def save_draft(draft: Draft) -> None:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    (DRAFTS_DIR / f"{draft.id}.json").write_text(draft.model_dump_json(indent=2), encoding="utf-8")


def load_draft(draft_id: str) -> Draft:
    if not re.fullmatch(r"[0-9a-f]{12}", draft_id):
        raise FileNotFoundError(draft_id)
    return Draft.model_validate_json((DRAFTS_DIR / f"{draft_id}.json").read_text(encoding="utf-8"))
