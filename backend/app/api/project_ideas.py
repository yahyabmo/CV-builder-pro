"""Les idées de projet d'un CV ciblé : trois projets à faire soi-même pour l'offre."""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import ValidationError

from app.ai import llm, targeting, usage_log
from app.ai.schemas import MissingSkill, OfferAnalysis, ProjectIdeas
from app.services import ats, project_ideas
from app.storage import cv_store, library_store

router = APIRouter(prefix="/api/cvs", tags=["idées de projet"])


def _targeted(slug: str) -> tuple[Path, OfferAnalysis, list[MissingSkill]]:
    try:
        path = cv_store.folder(slug)
    except cv_store.UnknownCV:
        raise HTTPException(404, f"CV introuvable : {slug}") from None
    file = path / "analysis.json"
    if not file.exists():
        raise HTTPException(404, "Ce CV n'a pas été ciblé sur une offre.")
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
        analysis = OfferAnalysis.model_validate(data["analysis"])
        missing = [MissingSkill.model_validate(m) for m in data.get("plan", {}).get("missing", [])]
    except (ValueError, KeyError, ValidationError):
        raise HTTPException(422, "L'analyse de l'offre de ce CV est illisible.") from None
    return path, analysis, missing


@router.get("/{slug}/project-ideas")
def saved_ideas(slug: str) -> project_ideas.SavedIdeas:
    """Les idées déjà proposées pour ce CV (aucune s'il n'y en a pas encore)."""
    path, _, _ = _targeted(slug)
    return project_ideas.load(path)


@router.post("/{slug}/project-ideas")
async def new_ideas(slug: str) -> project_ideas.SavedIdeas:
    """Trois idées de projet pour ce qui manque au CV face à l'offre (une requête)."""
    path, analysis, missing = _targeted(slug)
    content, _ = cv_store.load(path)
    know = targeting.build_knowledge(content, library_store.load())
    pdf = path / cv_store.PDF
    text = ats.pdf_text(pdf) if pdf.exists() else targeting.profile_text(content)
    absent = targeting.coverage(analysis, text, know).absent
    terms = list(dict.fromkeys([*absent, *(m.term for m in missing)]))
    try:
        provider = llm.provider_from_settings()
        system, message = targeting.load_prompt(
            "idees-projet",
            analysis=targeting.analysis_text(analysis),
            missing=", ".join(terms) or "(aucun)",
            skills=targeting.skills_text(know),
        )
        result = await llm.generate(provider, system, message, ProjectIdeas)
    except llm.LLMError as error:
        raise HTTPException(502, error.message) from None
    usage_log.record(provider.name, result.model, result.usage, "Idées de projet")
    return project_ideas.save(path, result.data.ideas[:3])


@router.get("/{slug}/project-ideas/{index}/brief")
def idea_brief(slug: str, index: int) -> Response:
    """Le cahier des charges d'une idée, en Markdown."""
    path, analysis, _ = _targeted(slug)
    ideas = project_ideas.load(path).ideas
    if not 0 <= index < len(ideas):
        raise HTTPException(404, "Idée introuvable : propose d'abord des idées.")
    idea = ideas[index]
    return Response(
        project_ideas.brief(idea, analysis),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{project_ideas.file_name(idea)}"'},
    )
