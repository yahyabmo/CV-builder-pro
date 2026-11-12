"""Remplissage de la bibliothèque depuis le CV et les dépôts GitHub.

Ce qui vient du CV est validé d'office (c'est déjà sur le CV) ; ce
qui vient de GitHub arrive « proposé », à valider. Une entrée déjà présente
(même lien, ou même nom) n'est jamais ajoutée une seconde fois.
"""

import base64
import json
import re
import subprocess
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from app.models.content import CVContent
from app.models.library import (
    Level,
    Library,
    LibraryExperience,
    LibraryProject,
    LibrarySkill,
    Source,
)

# Écritures GitHub des langages → nom de compétence.
_LANGUAGES = {
    "Dockerfile": "Docker",
    "Makefile": "Make",
    "Shell": "Bash",
    "TeX": "LaTeX",
    "Jupyter Notebook": "Jupyter",
    "Vue": "Vue.js",
}


class GitHubUnavailable(RuntimeError):
    pass


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def normalize(text: str) -> str:
    """« Acting Shooting Star – Moteur » → « actingshootingstarmoteur ».

    « + » et « # » restent : C, C++ et C# sont trois compétences différentes.
    """
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9+#]+", "", plain)


def _same_project(title: str, other: str) -> bool:
    a, b = normalize(title), normalize(other)
    if len(a) < 4 or len(b) < 4:
        return a == b
    return a.startswith(b) or b.startswith(a)


def find_project(library: Library, title: str, link: str | None) -> LibraryProject | None:
    """Le projet de la bibliothèque qui correspond : même lien d'abord, sinon même nom."""
    for project in library.projects:
        if link and project.link and project.link.rstrip("/") == link.rstrip("/"):
            return project
    for project in library.projects:
        if _same_project(project.title.split("–")[0], title):
            return project
    return None


def known_project(library: Library, title: str, link: str | None) -> bool:
    return find_project(library, title, link) is not None


def skill_keys(library: Library) -> set[str]:
    names: set[str] = set()
    for skill in library.skills:
        for name in [skill.name, *skill.aliases]:
            names.add(normalize(name))
            # « HTML/CSS » couvre aussi « HTML » et « CSS ».
            names.update(normalize(part) for part in name.split("/"))
    return names


# ─── Depuis le CV ────────────────────────────────────────────────────────────


def split_skills(text: str) -> list[str]:
    """« IA générative (LLM, RAG), NumPy. » → ['IA générative', 'LLM', 'RAG', 'NumPy']."""
    text = text.strip().rstrip(".")
    pieces: list[str] = []
    depth, current = 0, ""
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char in ",;" and depth == 0:
            pieces.append(current)
            current = ""
        else:
            current += char
    pieces.append(current)
    out: list[str] = []
    for piece in pieces:
        piece = piece.strip()
        match = re.match(r"^(.*?)\s*\((.*)\)$", piece)
        if match:
            head, inner = match.group(1).strip(), match.group(2)
            if head:
                out.append(head)
            out.extend(part.strip() for part in re.split(r"[,;]", inner) if part.strip())
        elif piece:
            out.append(piece)
    return [re.sub(r"\*\*|__", "", s) for s in out]


_TEAM = {
    "seul": "seul",
    "autonomie": "seul",
    "binôme": "binôme",
    "binome": "binôme",
    "équipe": "équipe",
    "equipe": "équipe",
}


def _team(tag: str) -> Literal["seul", "binôme", "équipe"] | None:
    lower = tag.lower()
    for word, team in _TEAM.items():
        if word in lower:
            return team  # type: ignore[return-value]
    return None


def _same_experience(a: LibraryExperience, title: str, place: str) -> bool:
    return normalize(a.title) == normalize(title) and normalize(a.place) == normalize(place)


def from_cv(
    content: CVContent, library: Library
) -> tuple[list[LibraryProject], list[LibrarySkill], list[LibraryExperience]]:
    projects: list[LibraryProject] = []
    skills: list[LibrarySkill] = []
    experiences: list[LibraryExperience] = []
    seen_skills = skill_keys(library)
    for section in content.sections:
        if section.kind == "experience":
            for entry in section.items:
                if any(_same_experience(e, entry.title, entry.place) for e in library.experiences):
                    continue
                experiences.append(
                    LibraryExperience(
                        id=new_id("experience"),
                        title=entry.title,
                        place=entry.place,
                        dates=entry.dates,
                        bullets=list(entry.bullets),
                        source="cv",
                    )
                )
        if section.kind == "projects":
            for item in section.items:
                if known_project(library, item.title, item.link) or any(
                    _same_project(p.title, item.title) for p in projects
                ):
                    continue
                projects.append(
                    LibraryProject(
                        id=new_id("projet"),
                        title=item.title,
                        date=item.date,
                        context="école",
                        team=_team(item.tag),
                        description=item.description,
                        bullets=list(item.bullets),
                        link=item.link,
                        source="cv",
                    )
                )
        elif section.kind == "skills":
            for group in section.items:
                for name in split_skills(group.text):
                    key = normalize(name)
                    if not key or key in seen_skills:
                        continue
                    seen_skills.add(key)
                    skills.append(
                        LibrarySkill(
                            id=new_id("competence"),
                            name=name,
                            category=group.label,
                            source="cv",
                        )
                    )
    return projects, skills, experiences


# ─── Depuis GitHub ───────────────────────────────────────────────────────────


def _gh(path: str) -> object:
    """Un appel à l'API GitHub avec l'authentification de ``gh`` (dépôts privés compris)."""
    try:
        run = subprocess.run(
            ["gh", "api", path], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GitHubUnavailable(f"GitHub ne répond pas ({error})") from None
    if run.returncode != 0:
        if "auth" in run.stderr.lower() or "login" in run.stderr.lower():
            raise GitHubUnavailable("GitHub n'est pas connecté : lance « gh auth login ».")
        raise GitHubUnavailable(run.stderr.strip() or "Appel GitHub refusé")
    return json.loads(run.stdout or "null")


def _readme_excerpt(full_name: str) -> str:
    try:
        data = _gh(f"repos/{full_name}/readme")
    except GitHubUnavailable:
        return ""
    raw = base64.b64decode(data.get("content", "")).decode("utf-8", "replace")  # type: ignore[union-attr]
    return plain_readme(raw)


def plain_readme(raw: str, limit: int = 4000) -> str:
    """Le README en texte simple : sans titres, images, liens, blocs de code.

    Le README entier (ou presque) : c'est la source d'information de l'IA sur le projet.
    """
    raw = re.sub(r"```.*?```", " ", raw, flags=re.S)
    raw = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", raw)
    raw = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", raw)
    raw = re.sub(r"<[^>]+>|^#+\s*|[*_`>|]", " ", raw, flags=re.M)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:limit]


def _humanize(name: str) -> str:
    text = re.sub(r"[-_]+", " ", name).strip()
    return text[:1].upper() + text[1:]


def _repo_details(repo: dict) -> dict:
    full = repo["full_name"]
    languages = _gh(f"repos/{full}/languages") or {}
    total = sum(languages.values()) or 1  # type: ignore[union-attr]
    main_languages = [
        lang
        for lang, size in sorted(languages.items(), key=lambda kv: -kv[1])  # type: ignore[union-attr]
        if size / total >= 0.05
    ]
    return {"languages": main_languages, "readme": _readme_excerpt(full)}


def from_github(library: Library) -> tuple[list[LibraryProject], list[LibrarySkill]]:
    from app.services.skill_categories import guess

    categories = list(dict.fromkeys(s.category for s in library.skills))
    repos = _gh("user/repos?per_page=100&affiliation=owner")
    if not isinstance(repos, list):
        raise GitHubUnavailable("Réponse inattendue de GitHub")
    found = [(r, find_project(library, _humanize(r["name"]), r["html_url"])) for r in repos]
    candidates = [r for r, project in found if project is None]
    # Un projet déjà connu (celui du CV) récupère le lien, le README et les langages de
    # son dépôt ; un dépôt retrouvé par son lien passe avant un dépôt au nom voisin.
    matched = sorted(
        [(r, p) for r, p in found if p is not None and not (p.link and p.notes and p.techs)],
        key=lambda pair: not (pair[1].link and pair[1].link.rstrip("/") == pair[0]["html_url"]),
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        details = list(pool.map(_repo_details, candidates))
        known_details = list(pool.map(_repo_details, [r for r, _ in matched]))
    for (repo, project), info in zip(matched, known_details, strict=True):
        if not project.link:
            project.link = repo["html_url"]
        if not project.notes and info["readme"]:
            project.notes = info["readme"]
        if not project.techs:
            project.techs = [_LANGUAGES.get(lang, lang) for lang in info["languages"]]

    projects: list[LibraryProject] = []
    seen_skills = skill_keys(library)
    skills: list[LibrarySkill] = []
    for repo, info in zip(candidates, details, strict=True):
        start, end = repo["created_at"][:4], repo["pushed_at"][:4]
        projects.append(
            LibraryProject(
                id=new_id("projet"),
                title=_humanize(repo["name"]),
                date=start if start == end else f"{start} – {end}",
                # Le cadre (seul, binôme, équipe) ne se devine pas : un projet
                # d'équipe peut n'avoir été poussé que depuis un compte. On le
                # précise en validant.
                team=None,
                techs=[_LANGUAGES.get(lang, lang) for lang in info["languages"]],
                description=(repo.get("description") or "").strip(),
                link=repo["html_url"],
                private=bool(repo.get("private")),
                notes=info["readme"],
                source="github",
                status="proposé",
            )
        )
        for lang in info["languages"]:
            name = _LANGUAGES.get(lang, lang)
            if normalize(name) in seen_skills:
                continue
            seen_skills.add(normalize(name))
            skills.append(
                LibrarySkill(
                    id=new_id("competence"),
                    name=name,
                    category=guess(name, categories),
                    source="github",
                    status="proposé",
                )
            )
    return projects, skills


# ─── Remplissage complet ─────────────────────────────────────────────────────


def fill(content: CVContent, library: Library, github: bool = True) -> tuple[Library, str | None]:
    """La bibliothèque complétée par le CV (validé) et GitHub (proposé).

    GitHub indisponible n'empêche pas le reste : le message d'erreur est rendu.
    """
    projects, skills, experiences = from_cv(content, library)
    merged = Library(
        projects=[*library.projects, *projects],
        skills=[*library.skills, *skills],
        experiences=[*library.experiences, *experiences],
    )
    error = None
    if github:
        try:
            more_projects, more_skills = from_github(merged)
        except GitHubUnavailable as failure:
            error = str(failure)
        else:
            merged.projects += more_projects
            merged.skills += more_skills
    return merged, error


# ─── Ajout de compétences ────────────────────────────────────────────────────


def split_list(text: str) -> list[str]:
    """« Kubernetes, Streamlit ; dbt » ou une compétence par ligne."""
    return [part.strip(" .\t") for part in re.split(r"[,;\n]+", text) if part.strip(" .\t")]


def add_skills(
    library: Library,
    names: list[str],
    category: str = "",
    level: Level | None = None,
    evidence: str = "",
    source: Source = "manuel",
) -> tuple[list[str], list[str]]:
    """Ajoute (validés) les noms absents de ``library.skills`` ; rend (ajoutés, déjà connus).

    Sans catégorie donnée, elle est devinée (``skill_categories``).
    """
    from app.services.skill_categories import guess

    seen = skill_keys(library)
    categories = list(dict.fromkeys(s.category for s in library.skills))
    added, known = [], []
    for name in names:
        key = normalize(name)
        if not key or key in seen:
            known.append(name)
            continue
        seen.add(key)
        library.skills.append(
            LibrarySkill(
                id=new_id("competence"),
                name=name,
                category=category.strip() or guess(name, categories),
                level=level,
                evidence=evidence.strip(),
                source=source,
            )
        )
        added.append(name)
    return added, known
