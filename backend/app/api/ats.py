"""Routes de la vérification ATS : ce que lit un logiciel de tri dans le PDF d'un CV."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.ai import targeting
from app.services import ats
from app.storage import cv_store, library_store

router = APIRouter(prefix="/api/cvs", tags=["ats"])


def _pdf(slug: str):  # noqa: ANN202
    try:
        path = cv_store.folder(slug)
    except cv_store.UnknownCV:
        raise HTTPException(404, f"CV introuvable : {slug}") from None
    if not (path / cv_store.PDF).exists():
        raise HTTPException(404, "Pas encore de PDF : lancer une compilation.")
    return path


@router.get("/{slug}/ats")
def check(slug: str) -> ats.AtsReport:
    path = _pdf(slug)
    content, _ = cv_store.load(path)
    return ats.analyze(path / cv_store.PDF, content, cv_store.load_meta(path).pages)


class TermsIn(BaseModel):
    terms: list[str] = Field(min_length=1, max_length=80)


class TermsOut(BaseModel):
    present: list[str]
    absent: list[str]


@router.post("/{slug}/ats/terms")
def check_terms(slug: str, body: TermsIn) -> TermsOut:
    """Des mots-clés (ceux d'une offre, par exemple) cherchés dans le texte extrait du PDF."""
    path = _pdf(slug)
    text = ats.pdf_text(path / cv_store.PDF)
    content, _ = cv_store.load(path)
    know = targeting.build_knowledge(content, library_store.load())
    terms = [t.strip() for t in body.terms if t.strip()]
    present = [t for t in terms if targeting.found(t, text, know)]
    return TermsOut(present=present, absent=[t for t in terms if t not in present])
