"""Routes de la lettre de motivation d'un CV ciblé : générer, retoucher, compiler, exporter."""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError

from app.ai import letter as letter_ai
from app.ai import llm
from app.ai.schemas import OfferAnalysis
from app.api.cvs import SourceIn, SourceOut, SourceResult
from app.api.schemas import CompileOut, LatexErrorOut
from app.latex.compile import CompileResult, LatexNotInstalled
from app.models.letter import LetterContent
from app.services.compiler import compiler
from app.storage import cv_store, letter_store, library_store

router = APIRouter(prefix="/api/cvs/{slug}/letter", tags=["lettre"])


def _folder(slug: str) -> Path:
    try:
        return cv_store.folder(slug)
    except cv_store.UnknownCV:
        raise HTTPException(404, f"CV introuvable : {slug}") from None


def _offer(path: Path) -> tuple[OfferAnalysis, str] | None:
    """L'analyse et le texte de l'offre visée par ce CV.

    None pour un CV non ciblé, ou dont l'analyse est illisible : pas de lettre.
    """
    file = path / "analysis.json"
    if not file.exists():
        return None
    try:
        analysis = OfferAnalysis.model_validate(
            json.loads(file.read_text(encoding="utf-8"))["analysis"]
        )
    except (ValueError, KeyError, ValidationError):
        return None
    offer = path / "offer.txt"
    return analysis, offer.read_text(encoding="utf-8") if offer.exists() else analysis.summary


class LetterState(BaseModel):
    # Une lettre demande une offre : faux pour un CV non ciblé.
    available: bool
    letter: LetterContent | None
    checks: list[letter_ai.LetterCheck]
    words: int
    pdf_version: int | None
    file_stem: str


def _state(path: Path) -> LetterState:
    letter = letter_store.load(path)
    offer = _offer(path)
    checks: list[letter_ai.LetterCheck] = []
    if letter is not None and letter.mode == "visual":
        content, _ = cv_store.load(path)
        checks = letter_ai.checks(
            letter, content, library_store.load(), offer[0] if offer else None
        )
    return LetterState(
        available=offer is not None,
        letter=letter,
        checks=checks,
        words=letter_ai.words(letter) if letter else 0,
        pdf_version=letter_store.pdf_version(path),
        file_stem=cv_store.letter_file_stem(path),
    )


def _compile_out(path: Path, result: CompileResult | None) -> CompileOut:
    if result is None:
        return CompileOut(ok=False, superseded=True)
    return CompileOut(
        ok=result.ok,
        pages=result.pages,
        seconds=round(result.seconds, 2),
        pdf_version=letter_store.pdf_version(path),
        errors=[
            LatexErrorOut(message=e.message, line=e.line, context=e.context) for e in result.errors
        ],
    )


async def _compile(slug: str, path: Path) -> CompileOut:
    try:
        return _compile_out(path, await compiler.compile_letter(slug))
    except LatexNotInstalled as error:
        raise HTTPException(503, str(error)) from None


@router.get("")
def get_letter(slug: str) -> LetterState:
    return _state(_folder(slug))


class GenerateIn(BaseModel):
    why: str = Field(default="", max_length=3000)
    detail: str = Field(default="", max_length=3000)


class LetterResult(BaseModel):
    state: LetterState
    compile: CompileOut


@router.post("/generate")
async def generate(slug: str, body: GenerateIn) -> LetterResult:
    """Écrit la lettre (1 requête), l'enregistre et la compile. Remplace la précédente."""
    path = _folder(slug)
    offer = _offer(path)
    if offer is None:
        raise HTTPException(409, "Ce CV ne vise aucune offre : cible une offre d'abord.")
    content, _ = cv_store.load(path)
    try:
        provider = llm.provider_from_settings()
        letter = await letter_ai.generate(
            content, library_store.load(), offer[1], offer[0], body.why, body.detail, provider
        )
    except llm.LLMError as error:
        raise HTTPException(502, error.message) from None
    letter_store.save(path, letter)
    compiled = await _compile(slug, path)
    return LetterResult(state=_state(path), compile=compiled)


@router.put("")
def put_letter(slug: str, letter: LetterContent) -> LetterState:
    path = _folder(slug)
    current = letter_store.load(path)
    if current is None:
        raise HTTPException(404, "Pas encore de lettre : génère-la d'abord.")
    if current.mode == "manual":
        raise HTTPException(409, "La lettre est en mode manuel : son .tex est la source.")
    letter_store.save(path, letter.model_copy(update={"mode": "visual"}))
    return _state(path)


@router.post("/compile")
async def compile_letter(slug: str) -> CompileOut:
    path = _folder(slug)
    if letter_store.load(path) is None:
        raise HTTPException(404, "Pas encore de lettre.")
    return await _compile(slug, path)


@router.get("/pdf")
def get_pdf(slug: str) -> FileResponse:
    pdf = _folder(slug) / letter_store.PDF
    if not pdf.exists():
        raise HTTPException(404, "Pas encore de PDF de la lettre.")
    return FileResponse(pdf, media_type="application/pdf", headers={"Cache-Control": "no-store"})


class TextOut(BaseModel):
    text: str


@router.get("/text")
def get_text(slug: str) -> TextOut:
    """Le corps de la lettre, prêt à coller dans un formulaire ou un mail."""
    letter = letter_store.load(_folder(slug))
    if letter is None:
        raise HTTPException(404, "Pas encore de lettre.")
    return TextOut(text=letter_store.plain_text(letter))


# ─── Code LaTeX et mode manuel ───────────────────────────────────────────────


@router.get("/tex")
def get_tex(slug: str) -> FileResponse:
    path = _folder(slug)
    letter = letter_store.load(path)
    if letter is None:
        raise HTTPException(404, "Pas encore de lettre.")
    tex = path / letter_store.TEX if letter.mode == "manual" else letter_store.write_tex(path)
    return FileResponse(
        tex, media_type="application/x-tex", filename=f"{cv_store.letter_file_stem(path)}.tex"
    )


@router.get("/source")
def get_source(slug: str) -> SourceOut:
    path = _folder(slug)
    letter = letter_store.load(path)
    if letter is None:
        raise HTTPException(404, "Pas encore de lettre.")
    if letter.mode == "manual":
        return SourceOut(tex=(path / letter_store.TEX).read_text(encoding="utf-8"), mode="manual")
    return SourceOut(tex=letter_store.render(path, letter), mode="visual")


@router.put("/source")
async def put_source(slug: str, body: SourceIn) -> SourceResult:
    """Un .tex modifié à la main : la lettre passe en mode manuel, puis compile."""
    path = _folder(slug)
    letter = letter_store.load(path)
    if letter is None:
        raise HTTPException(404, "Pas encore de lettre.")
    if letter.mode == "visual" and body.tex == letter_store.render(path, letter):
        return SourceResult(mode="visual", compile=await _compile(slug, path))
    (path / letter_store.TEX).write_text(body.tex, encoding="utf-8")
    letter_store.save(path, letter.model_copy(update={"mode": "manual"}))
    return SourceResult(mode="manual", compile=await _compile(slug, path))


@router.post("/visual")
async def back_to_visual(slug: str) -> SourceResult:
    path = _folder(slug)
    letter = letter_store.load(path)
    if letter is None:
        raise HTTPException(404, "Pas encore de lettre.")
    letter_store.save(path, letter.model_copy(update={"mode": "visual"}))
    return SourceResult(mode="visual", compile=await _compile(slug, path))
