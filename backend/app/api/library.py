"""Routes de la bibliothèque : projets, compétences, propositions (CV, GitHub)."""

import asyncio
import json
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.ai import llm, targeting, usage_log
from app.ai.schemas import ProjectDraft
from app.models.library import Level, Library, LibraryExperience, LibraryProject, LibrarySkill
from app.paths import server_mode
from app.services import library_import, skill_categories
from app.storage import cv_store, library_store

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("")
def get_library() -> Library:
    return library_store.load()


@router.put("/projects")
def put_projects(projects: list[LibraryProject]) -> Library:
    if len({p.id for p in projects}) != len(projects):
        raise HTTPException(422, "Deux projets ont le même identifiant.")
    library_store.save_projects(projects)
    return library_store.load()


@router.put("/skills")
def put_skills(skills: list[LibrarySkill]) -> Library:
    if len({s.id for s in skills}) != len(skills):
        raise HTTPException(422, "Deux compétences ont le même identifiant.")
    library_store.save_skills(skills)
    return library_store.load()


class GroupIn(BaseModel):
    term: str = Field(min_length=1, max_length=120)
    groups: list[str] = Field(default_factory=list, max_length=50)


class GroupOut(BaseModel):
    # Le groupe du CV où ranger le mot, ou un nouveau nom ; None : rien de connu.
    group: str | None
    exists: bool


@router.post("/skills/group")
def skill_group(body: GroupIn) -> GroupOut:
    """Le groupe de compétences où ranger un mot-clé, deviné sans IA (« Power BI » → Outils)."""
    if skill_categories.canonical(body.term) is None:
        return GroupOut(group=None, exists=False)
    found = skill_categories.guess(body.term, body.groups)
    return GroupOut(group=found, exists=found in body.groups)


class FillOut(BaseModel):
    library: Library
    added: dict[str, int]
    github_error: str | None


@router.post("/fill")
async def fill(github: bool = True) -> FillOut:
    """Complète la bibliothèque : le CV classique (validé d'office) et GitHub (à valider).

    ``github=false`` : le CV seul, sans lire le compte GitHub connecté sur la machine.
    """
    content, _ = cv_store.load(cv_store.folder(cv_store.BASE_SLUG))
    before = library_store.load()
    # En ligne, le compte GitHub de la machine est celui de Yahya : jamais lu pour les autres.
    github = github and not server_mode()
    merged, error = await asyncio.to_thread(library_import.fill, content, before, github)
    library_store.save_projects(merged.projects)
    library_store.save_skills(merged.skills)
    library_store.save_experiences(merged.experiences)
    return FillOut(
        library=merged,
        added={
            "projects": len(merged.projects) - len(before.projects),
            "skills": len(merged.skills) - len(before.skills),
            "experiences": len(merged.experiences) - len(before.experiences),
        },
        github_error=error,
    )


@router.put("/experiences")
def put_experiences(experiences: list[LibraryExperience]) -> Library:
    if len({e.id for e in experiences}) != len(experiences):
        raise HTTPException(422, "Deux expériences ont le même identifiant.")
    library_store.save_experiences(experiences)
    return library_store.load()


class BulkSkills(BaseModel):
    # « Kubernetes, Streamlit ; dbt » ou une compétence par ligne.
    text: str = Field(min_length=1, max_length=5000)
    category: str = ""
    level: Level | None = None
    evidence: str = ""
    source: Literal["manuel", "offre"] = "manuel"


class BulkOut(BaseModel):
    library: Library
    added: list[str]
    known: list[str]


@router.post("/skills/bulk")
def add_skills(bulk: BulkSkills) -> BulkOut:
    """Ajoute plusieurs compétences d'un coup (validées), catégorie devinée si absente."""
    library = library_store.load()
    added, known = library_import.add_skills(
        library,
        library_import.split_list(bulk.text),
        category=bulk.category,
        level=bulk.level,
        evidence=bulk.evidence,
        source=bulk.source,
    )
    library_store.save_skills(library.skills)
    return BulkOut(library=library_store.load(), added=added, known=known)


@router.post("/projects/{project_id}/draft")
async def draft_project(project_id: str) -> ProjectDraft:
    """Une description, des puces et les technos d'un projet, proposées par l'IA (1 requête)."""
    library = library_store.load()
    project = next((p for p in library.projects if p.id == project_id), None)
    if project is None:
        raise HTTPException(404, "Projet introuvable")
    if not (project.notes or project.description or project.bullets):
        raise HTTPException(
            422, "Rien à partir de quoi rédiger : ajoute une description ou des notes."
        )
    facts = project.model_dump(
        include={"title", "date", "team", "techs", "description", "bullets", "notes", "link"}
    )
    try:
        provider = llm.provider_from_settings()
        system, message = targeting.load_prompt(
            "projet", project=json.dumps(facts, ensure_ascii=False, indent=1)
        )
        result = await llm.generate(provider, system, message, ProjectDraft)
    except llm.LLMError as error:
        raise HTTPException(502, error.message) from None
    usage_log.record(provider.name, result.model, result.usage, "Fiche de projet")
    return result.data
