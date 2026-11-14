"""Routes des CV : liste, lecture, contenu, compilation, PDF, photo."""

from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import fonts
from app.api.schemas import CompileOut, CVDetail, CVSummary, LatexErrorOut
from app.latex.compile import CompileResult, LatexNotInstalled
from app.latex.render import render
from app.models import application
from app.models.application import ApplicationPatch
from app.models.content import CVContent
from app.models.style import CVStyle
from app.services import cuts, locate, photo
from app.services.compiler import compiler
from app.storage import cv_store

router = APIRouter(prefix="/api/cvs", tags=["cvs"])


def _folder(slug: str) -> Path:
    try:
        return cv_store.folder(slug)
    except cv_store.UnknownCV:
        raise HTTPException(404, f"CV introuvable : {slug}") from None


def _pdf_version(path: Path) -> int | None:
    pdf = path / cv_store.PDF
    return pdf.stat().st_mtime_ns if pdf.exists() else None


def summary(slug: str) -> CVSummary:
    path = cv_store.folder(slug)
    meta = cv_store.load_meta(path)
    return CVSummary(
        slug=slug,
        meta=meta,
        pdf_version=_pdf_version(path),
        file_stem=cv_store.file_stem(path),
        file_label=cv_store.offer_label(path, meta),
        **cv_store.offer_facts(path),
        due=meta.kind == "cv" and meta.application.due(date.today()),
    )


@router.get("")
def list_cvs() -> list[CVSummary]:
    return [summary(slug) for slug, _ in cv_store.list_all()]


class NewCV(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source: str = cv_store.BASE_SLUG
    # « base » : un CV classique de plus (copie d'un autre), pas une candidature.
    kind: Literal["base", "cv"] = "cv"


class Rename(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # 1 à 3 mots de l'offre pour le nom du fichier ; vide = retour à ceux de l'analyse.
    label: str | None = Field(default=None, max_length=60)


@router.post("")
async def create_cv(new: NewCV) -> CVSummary:
    """Un nouveau CV copié d'un autre (la version classique par défaut), compilé."""
    _folder(new.source)
    slug = cv_store.create(new.name, new.source, new.kind)
    await compiler.compile(slug)
    return summary(slug)


@router.patch("/{slug}")
def rename_cv(slug: str, rename: Rename) -> CVSummary:
    _folder(slug)
    cv_store.rename(slug, rename.name, rename.label, set_label="label" in rename.model_fields_set)
    return summary(slug)


@router.patch("/{slug}/application")
def update_application(slug: str, patch: ApplicationPatch) -> CVSummary:
    """Le suivi de la candidature : statut, dates, contact, notes, relance."""
    path = _folder(slug)
    meta = cv_store.load_meta(path)
    if meta.kind == "base":
        raise HTTPException(409, "La version classique n'est pas une candidature.")
    changes: dict[str, object] = {
        "application": application.update(meta.application, patch, date.today())
    }
    if "offer_url" in patch.model_fields_set:
        changes["offer_url"] = (patch.offer_url or "").strip() or None
    cv_store.save_meta(path, meta.model_copy(update=changes))
    return summary(slug)


@router.delete("/{slug}")
def delete_cv(slug: str) -> dict[str, str]:
    _folder(slug)
    try:
        moved = cv_store.delete(slug)
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    return {"trash": moved.name}


@router.get("/{slug}/thumbnail")
def get_thumbnail(slug: str) -> FileResponse:
    _folder(slug)
    thumb = cv_store.thumbnail(slug)
    if thumb is None:
        raise HTTPException(404, "Pas encore de PDF")
    return FileResponse(thumb, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/{slug}/tex")
def get_tex(slug: str) -> FileResponse:
    tex = _folder(slug) / cv_store.TEX
    if not tex.exists():
        raise HTTPException(404, "Pas encore de .tex : lancer une compilation.")
    return FileResponse(
        tex, media_type="application/x-tex", filename=f"{cv_store.file_stem(tex.parent)}.tex"
    )


@router.get("/{slug}/locate")
def locate_click(slug: str, x: float, y: float, page: int = 1) -> locate.Location | None:
    """L'élément du contenu sous un clic sur l'aperçu, en points depuis le haut gauche.

    Rien en mode manuel : le code LaTeX y est la source, plus le contenu.
    """
    path = _folder(slug)
    if cv_store.load_meta(path).mode == "manual":
        return None
    return locate.locate(path, x, y, page)


@router.get("/{slug}")
def get_cv(slug: str) -> CVDetail:
    path = _folder(slug)
    content, style = cv_store.load(path)
    return CVDetail(
        **summary(slug).model_dump(),
        content=content,
        style=style,
    )


@router.put("/{slug}/content")
def put_content(slug: str, content: CVContent) -> CVSummary:
    path = _folder(slug)
    if cv_store.load_meta(path).mode == "manual":
        raise HTTPException(409, "Ce CV est en mode manuel : son .tex est la source.")
    cv_store.save_content(path, content)
    return summary(slug)


@router.put("/{slug}/style")
def put_style(slug: str, style: CVStyle) -> CVSummary:
    path = _folder(slug)
    if cv_store.load_meta(path).mode == "manual":
        raise HTTPException(409, "Ce CV est en mode manuel : son .tex est la source.")
    content, _ = cv_store.load(path)
    # Une police ou une couleur inconnue se voit ici, pas à la compilation.
    try:
        render(content, style)
    except (ValueError, fonts.UnknownFont) as error:
        raise HTTPException(422, str(error)) from None
    cv_store.save_style(path, style)
    return summary(slug)


@router.post("/{slug}/photo")
async def upload_photo(slug: str, file: UploadFile) -> dict[str, str | int]:
    path = _folder(slug)
    if cv_store.load_meta(path).mode == "manual":
        raise HTTPException(409, "Ce CV est en mode manuel : change la photo dans son code LaTeX.")
    try:
        name = photo.store(path, await file.read())
    except photo.BadImage as error:
        raise HTTPException(422, str(error)) from None
    content, _ = cv_store.load(path)
    content.header.photo = name
    cv_store.save_content(path, content)
    return {"photo": name, "version": (path / name).stat().st_mtime_ns}


def compile_out(slug: str, result: CompileResult | None) -> CompileOut:
    if result is None:
        return CompileOut(ok=False, superseded=True)
    path = cv_store.folder(slug)
    suggested = []
    if result.ok and result.overflow_columns:
        content, _ = cv_store.load(path)
        suggested = cuts.suggest(content, result.overflow_columns)
    return CompileOut(
        ok=result.ok,
        pages=result.pages,
        seconds=round(result.seconds, 2),
        overflow_pt=round(result.overflow_pt, 1),
        pdf_version=_pdf_version(path),
        errors=[
            LatexErrorOut(message=e.message, line=e.line, context=e.context) for e in result.errors
        ],
        cuts=suggested,
    )


async def compile_now(slug: str) -> CompileOut:
    try:
        return compile_out(slug, await compiler.compile(slug))
    except LatexNotInstalled as error:
        raise HTTPException(503, str(error)) from None


@router.post("/{slug}/compile")
async def compile_cv(slug: str) -> CompileOut:
    _folder(slug)
    return await compile_now(slug)


class CutIn(BaseModel):
    id: str


@router.post("/{slug}/cut")
async def cut_cv(slug: str, cut: CutIn) -> CompileOut:
    """Applique une coupe proposée, puis recompile."""
    path = _folder(slug)
    if cv_store.load_meta(path).mode == "manual":
        raise HTTPException(409, "Ce CV est en mode manuel : son .tex est la source.")
    content, _ = cv_store.load(path)
    try:
        cv_store.save_content(path, cuts.apply_cut(content, cut.id))
    except cuts.UnknownCut:
        raise HTTPException(
            422, "Cette coupe ne correspond plus au CV : recompile pour en avoir de nouvelles."
        ) from None
    return await compile_now(slug)


@router.get("/{slug}/pdf")
def get_pdf(slug: str) -> FileResponse:
    pdf = _folder(slug) / cv_store.PDF
    if not pdf.exists():
        raise HTTPException(404, "Pas encore de PDF : lancer une compilation.")
    return FileResponse(pdf, media_type="application/pdf", headers={"Cache-Control": "no-store"})


@router.get("/{slug}/photo")
def get_photo(slug: str) -> FileResponse:
    path = _folder(slug)
    content, _ = cv_store.load(path)
    photo = (path / content.header.photo) if content.header.photo else None
    if photo is None or not photo.is_file() or photo.parent != path:
        raise HTTPException(404, "Pas de photo")
    return FileResponse(photo, headers={"Cache-Control": "no-store"})


# ─── Code LaTeX et mode manuel ───────────────────────────────────────────────


class SourceOut(BaseModel):
    tex: str
    mode: Literal["visual", "manual"]


class SourceIn(BaseModel):
    tex: str = Field(min_length=1, max_length=300_000)


class SourceResult(BaseModel):
    mode: Literal["visual", "manual"]
    compile: CompileOut


@router.get("/{slug}/source")
def get_source(slug: str) -> SourceOut:
    """Le .tex du CV : celui de main.tex en mode manuel, sinon tiré du contenu et du style."""
    path = _folder(slug)
    meta = cv_store.load_meta(path)
    if meta.mode == "manual":
        return SourceOut(tex=(path / cv_store.TEX).read_text(encoding="utf-8"), mode="manual")
    return SourceOut(tex=cv_store.generated(path), mode="visual")


@router.put("/{slug}/source")
async def put_source(slug: str, body: SourceIn) -> SourceResult:
    """Enregistre un .tex modifié à la main : le CV passe en mode manuel, puis compile."""
    path = _folder(slug)
    meta = cv_store.load_meta(path)
    if meta.mode == "visual":
        if body.tex == cv_store.generated(path):
            return SourceResult(mode="visual", compile=await compile_now(slug))
        if meta.kind == "base":
            raise HTTPException(
                409,
                "Un CV classique reste en mode visuel : il sert de modèle aux autres CV. "
                "Duplique-le pour modifier son code LaTeX.",
            )
    (path / cv_store.TEX).write_text(body.tex, encoding="utf-8")
    cv_store.touch(path, mode="manual")
    return SourceResult(mode="manual", compile=await compile_now(slug))


@router.post("/{slug}/visual")
async def back_to_visual(slug: str) -> SourceResult:
    """Retour au mode visuel : le .tex est refait depuis le contenu et le style (modifications
    manuelles perdues)."""
    path = _folder(slug)
    cv_store.touch(path, mode="visual")
    return SourceResult(mode="visual", compile=await compile_now(slug))
