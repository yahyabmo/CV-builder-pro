"""Le premier lancement : importer son CV en PDF, le saisir à la main, ou garder l'exemple.

Valider remplace la version classique (l'ancienne part dans la corbeille) et remplit
la bibliothèque à partir du nouveau CV, comme « Remplir depuis mon CV ».
"""

import asyncio
import shutil

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import settings
from app.ai import llm, targeting, usage_log
from app.ai.schemas import ImportedCV
from app.api.cvs import compile_now
from app.api.schemas import CompileOut
from app.latex.compile import LatexNotInstalled, compile_tex
from app.models.content import CVContent
from app.models.meta import now
from app.paths import DEMO_DIR
from app.services import cv_import, cv_style, library_import, photo
from app.storage import cv_store, library_store

router = APIRouter(prefix="/api/welcome", tags=["accueil"])


class WelcomeState(BaseModel):
    # La version classique est encore le CV fictif : l'accueil s'ouvre.
    show: bool
    # L'écran de démarrage (modèle d'IA, machine) n'a pas encore été passé.
    setup: bool = False


class ReadingOut(BaseModel):
    id: str
    words: int
    pages: int | None
    photo: bool


class ImportResult(BaseModel):
    id: str
    content: CVContent
    photo: bool
    checks: list[cv_import.Check]
    counts: dict[str, int]


class ApplyIn(BaseModel):
    content: CVContent
    # L'import d'où vient le CV (sa photo), absent pour une saisie à la main.
    import_id: str | None = None
    keep_photo: bool = True
    # Le style repéré dans le PDF à reprendre (clés de cv_style.KEYS) ; None : celui de l'appli.
    keep: list[str] | None = None


class PreviewIn(BaseModel):
    content: CVContent
    keep: list[str] | None = None


class StyleOut(BaseModel):
    findings: list[cv_style.Finding]


class ApplyOut(BaseModel):
    added: dict[str, int]
    compile: CompileOut


def _base():
    return cv_store.folder(cv_store.BASE_SLUG)


def _folder(import_id: str):
    try:
        return cv_import.folder(import_id)
    except cv_import.UnknownImport:
        raise HTTPException(404, "Import introuvable : recommence depuis l'accueil.") from None


STYLE = "style.json"


def _guess(import_id: str) -> cv_style.Guess:
    """Le style repéré dans le PDF importé, calculé une fois (il ne coûte aucune requête)."""
    folder = _folder(import_id)
    cached = folder / STYLE
    if cached.exists():
        return cv_style.Guess.model_validate_json(cached.read_text(encoding="utf-8"))
    data = cv_import.load_result(import_id)
    if data is None:
        raise HTTPException(404, "Ce PDF n'a pas encore été lu.")
    content = CVContent.model_validate(data["content"])
    found = cv_style.guess(folder / cv_import.SOURCE, content, cv_import.has_photo(import_id))
    cached.write_text(found.model_dump_json(), encoding="utf-8")
    return found


def _styled(import_id: str | None, content: CVContent, keep: list[str] | None):
    """Le style de la version classique, avec ce qu'on garde du style du PDF."""
    _, style = cv_store.load(_base())
    if import_id is None or keep is None:
        return style, content
    return cv_style.apply_guess(style, content, _guess(import_id), set(keep) & set(cv_style.KEYS))


@router.get("")
def state() -> WelcomeState:
    show = cv_store.load_meta(_base()).welcome
    return WelcomeState(show=show, setup=show and not settings.setup_done())


@router.post("/setup")
def setup_done() -> WelcomeState:
    """L'écran de démarrage est passé : l'accueil continue par le CV de base."""
    settings.mark_setup_done()
    return state()


@router.post("/dismiss")
def dismiss() -> WelcomeState:
    """« Partir de l'exemple » : l'accueil ne s'ouvre plus."""
    cv_store.save_meta(_base(), cv_store.load_meta(_base()).model_copy(update={"welcome": False}))
    return WelcomeState(show=False)


@router.get("/blank")
def blank() -> CVContent:
    """Un CV vide, avec les rubriques de l'appli : le point de départ de la saisie à la main."""
    empty = ImportedCV(
        language="fr", name="", headline="", summary="", contacts=[], education=[],
        experience=[], associative=[], projects=[], skills=[], soft_skills=[], languages=[],
        interests=[], unplaced=[],
    )  # fmt: skip
    return cv_import.to_content(empty, with_photo=False)


@router.get("/demo-pdf")
def demo_pdf() -> FileResponse:
    """Le PDF d'exemple : le seul que le mode démo sait lire."""
    return FileResponse(DEMO_DIR / "cv-exemple.pdf", media_type="application/pdf")


@router.post("/import")
async def upload(file: UploadFile) -> ReadingOut:
    """Étape 1 : le texte et la photo du PDF, sans IA."""
    data = await file.read()
    if settings.load().provider == "demo" and not cv_import.is_demo_pdf(data):
        raise HTTPException(
            422,
            "En mode démo, seul le PDF d'exemple a une lecture enregistrée. "
            "Choisis un modèle d'IA dans Réglages pour importer ton CV.",
        )
    try:
        reading = await asyncio.to_thread(cv_import.read_pdf, data)
    except cv_import.UnreadablePdf as error:
        raise HTTPException(422, str(error)) from None
    return ReadingOut(**reading.__dict__)


@router.post("/import/{import_id}/read")
async def read(import_id: str) -> ImportResult:
    """Étape 2 : l'IA range le texte dans les rubriques de l'appli (une requête)."""
    _folder(import_id)
    source = cv_import.text_of(import_id)
    try:
        provider = llm.provider_from_settings()
        system, message = targeting.load_prompt("import", text=source)
        result = await llm.generate(provider, system, message, ImportedCV)
    except llm.LLMError as error:
        raise HTTPException(502, error.message) from None
    usage_log.record(provider.name, result.model, result.usage, "Import d'un CV")
    with_photo = cv_import.has_photo(import_id)
    content = cv_import.to_content(result.data, with_photo)
    out = ImportResult(
        id=import_id,
        content=content,
        photo=with_photo,
        checks=cv_import.checks(result.data, source),
        counts=cv_import.counts(content),
    )
    cv_import.save_result(import_id, out.model_dump(mode="json"))
    return out


@router.get("/import/{import_id}")
def result(import_id: str) -> ImportResult:
    """La lecture déjà faite, pour reprendre la relecture après un rechargement."""
    _folder(import_id)
    data = cv_import.load_result(import_id)
    if data is None:
        raise HTTPException(404, "Ce PDF n'a pas encore été lu.")
    return ImportResult.model_validate(data)


@router.get("/import/{import_id}/source")
def source_pdf(import_id: str) -> FileResponse:
    return FileResponse(_folder(import_id) / cv_import.SOURCE, media_type="application/pdf")


@router.get("/import/{import_id}/photo")
def import_photo(import_id: str) -> FileResponse:
    file = _folder(import_id) / photo.PHOTO
    if not file.exists():
        raise HTTPException(404, "Pas de photo dans ce PDF.")
    return FileResponse(file, media_type="image/jpeg")


@router.get("/import/{import_id}/style")
def import_style(import_id: str) -> StyleOut:
    """Ce que l'appli a repéré du style du PDF : police, couleurs, colonnes, titres…"""
    return StyleOut(findings=_guess(import_id).findings)


@router.post("/import/{import_id}/preview")
async def preview(import_id: str, body: PreviewIn) -> CompileOut:
    """L'aperçu du CV lu, au format de l'appli (et dans le style gardé), avant de le valider."""
    folder = _folder(import_id) / "apercu"
    folder.mkdir(exist_ok=True)
    style, content = _styled(import_id, body.content, body.keep)
    cv_store.save(folder, content, style)
    if content.header.photo:
        shutil.copy(folder.parent / photo.PHOTO, folder / photo.PHOTO)
    try:
        result = await asyncio.to_thread(compile_tex, cv_store.write_tex(folder))
    except LatexNotInstalled as error:
        raise HTTPException(503, str(error)) from None
    return CompileOut(ok=result.ok, pages=result.pages, seconds=round(result.seconds, 2))


@router.get("/import/{import_id}/preview.pdf")
def preview_pdf(import_id: str) -> FileResponse:
    file = _folder(import_id) / "apercu" / cv_store.PDF
    if not file.exists():
        raise HTTPException(404, "Pas encore d'aperçu.")
    return FileResponse(file, media_type="application/pdf")


@router.post("/apply")
async def apply(body: ApplyIn) -> ApplyOut:
    """Le CV devient la version classique ; la bibliothèque reçoit ce qu'il contient."""
    style, content = _styled(body.import_id, body.content, body.keep)
    source_photo = None
    if body.import_id is not None:
        candidate = _folder(body.import_id) / photo.PHOTO
        if body.keep_photo and candidate.exists():
            source_photo = candidate
    base = _base()
    # L'ancienne version classique reste récupérable dans la corbeille.
    cv_store.TRASH_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now().strftime("%Y%m%d-%H%M%S")
    shutil.copytree(
        base, cv_store.TRASH_DIR / f"base-{stamp}", ignore=shutil.ignore_patterns("build")
    )
    if source_photo is not None:
        content.header.photo = photo.store(base, source_photo.read_bytes())
    else:
        # Vide, et non None : un champ None n'est pas écrit, et la photo par défaut reviendrait.
        content.header.photo = ""
    cv_store.save_content(base, content)
    cv_store.save_style(base, style)
    cv_store.touch(base, welcome=False)

    before = library_store.load()
    merged, _ = await asyncio.to_thread(library_import.fill, content, before, False)
    library_store.save_projects(merged.projects)
    library_store.save_skills(merged.skills)
    library_store.save_experiences(merged.experiences)
    added = {
        "skills": len(merged.skills) - len(before.skills),
        "experiences": len(merged.experiences) - len(before.experiences),
        "projects": len(merged.projects) - len(before.projects),
    }
    return ApplyOut(added=added, compile=await compile_now(cv_store.BASE_SLUG))
