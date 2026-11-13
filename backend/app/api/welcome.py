"""Le premier lancement : importer son CV en PDF, le saisir à la main, ou garder l'exemple.

Valider remplace la version classique (l'ancienne part dans la corbeille) et remplit
la bibliothèque à partir du nouveau CV, comme « Remplir depuis mon CV ».
"""

import asyncio
import shutil
from collections import defaultdict

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import fonts, settings
from app.ai import llm, targeting, usage_log
from app.ai.schemas import ImportedCV
from app.api.cvs import compile_now
from app.api.schemas import CompileOut
from app.latex.compile import LatexNotInstalled, compile_tex
from app.models.content import CVContent
from app.models.meta import CVMeta, now
from app.paths import DEMO_DIR, server_mode
from app.services import cv_import, cv_style, library_import, ocr, photo
from app.services.clone import build as clone_build
from app.services.clone import fill as clone_fill
from app.services.clone import likeness
from app.services.clone import plan as clone_plan
from app.services.clone import report as clone_report
from app.services.clone import scan as clone_scan
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
    scanned: bool = False


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
    # Où va le CV : ``new_name`` = un CV classique de plus, à ce nom ; sinon ``target``,
    # le CV classique remplacé (la première version par défaut).
    new_name: str | None = Field(default=None, max_length=120)
    target: str = cv_store.BASE_SLUG
    # Garder la forme du PDF clonée (calculée par /clone) ; ``clone_active`` : le CV la prend
    # tout de suite (sinon la mise en page de l'appli, et le clone reste à côté).
    clone: bool = False
    clone_active: bool = True


class PreviewIn(BaseModel):
    content: CVContent
    keep: list[str] | None = None


class StyleOut(BaseModel):
    findings: list[cv_style.Finding]


class CloneFont(BaseModel):
    pdf: str
    name: str
    # « identique », « mêmes largeurs » ou « proche ».
    badge: str


class CloneOut(BaseModel):
    available: bool
    ok: bool = False
    # Pourquoi le clone n'est pas possible, ou a échoué.
    reason: str | None = None
    likeness: int | None = None
    fonts: list[CloneFont] = Field(default_factory=list)
    kept: list[str] = Field(default_factory=list)
    differences: list[str] = Field(default_factory=list)
    # Le contrôle mot à mot est quasi parfait : le clone est proposé par défaut. Sinon, un
    # avertissement, et « Proche du mien » d'abord.
    recommended: bool = True
    warning: str | None = None


class ApplyOut(BaseModel):
    added: dict[str, int]
    compile: CompileOut
    # Le CV classique écrit.
    slug: str = cv_store.BASE_SLUG


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


def _styled(import_id: str | None, content: CVContent, keep: list[str] | None, slug: str = "base"):
    """Le style d'un CV classique (la première version par défaut), avec ce qu'on garde du PDF."""
    _, style = cv_store.load(cv_store.folder(slug))
    if import_id is None or keep is None:
        return style, content
    return cv_style.apply_guess(style, content, _guess(import_id), set(keep) & set(cv_style.KEYS))


_PREVIEWS: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


@router.get("")
def state() -> WelcomeState:
    show = cv_store.load_meta(_base()).welcome
    # En ligne, rien à régler : ni modèle d'IA à choisir, ni machine à vérifier.
    setup = show and not server_mode() and not settings.setup_done()
    return WelcomeState(show=show, setup=setup)


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
    # La page corrige l'IA : lignes oubliées, puces coupées, gras et liens.
    left = None
    try:
        pages = await asyncio.to_thread(cv_import.pages_of, import_id)
        content, report = await asyncio.to_thread(clone_fill.complete, content, pages)
        left = report.left
    except Exception:  # noqa: BLE001 — sans la page, la lecture de l'IA reste telle quelle
        pass
    out = ImportResult(
        id=import_id,
        content=content,
        photo=with_photo,
        checks=cv_import.checks(result.data, source, left),
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
    # Deux aperçus demandés coup sur coup (onglet, puis case) : l'un après l'autre, jamais
    # deux compilations dans le même dossier.
    async with _PREVIEWS[import_id]:
        cv_store.save(folder, content, style)
        if content.header.photo:
            shutil.copy(folder.parent / photo.PHOTO, folder / photo.PHOTO)
        try:
            result = await asyncio.to_thread(compile_tex, cv_store.write_tex(folder))
        except LatexNotInstalled as error:
            raise HTTPException(503, str(error)) from None
    return CompileOut(ok=result.ok, pages=result.pages, seconds=round(result.seconds, 2))


CLONE_DIR = "clone"


def _summary(
    layout: clone_plan.AnchoredLayout, diff: clone_report.Differences, scanned: bool
) -> tuple[list[str], list[str]]:
    """Ce qui est repris à l'identique, et ce qui ne l'est pas, en phrases courtes."""
    kept, differences = [], []
    pages = len(layout.pages)
    if pages > 1:
        kept.append(f"{pages} pages, chacune à sa forme")
    columns = len(layout.lanes[0]) if layout.lanes else 1
    if columns > 1:
        kept.append(f"{columns} colonnes, aux mêmes largeurs")
    fills = [
        p for p in layout.paints if p.fill and (p.box[2] - p.box[0]) * (p.box[3] - p.box[1]) > 4000
    ]
    if fills:
        kept.append("Fonds et bandeaux de couleur")
    if layout.photo:
        shape = {"circle": "ronde", "rounded": "aux coins arrondis", "square": "carrée"}
        kept.append(f"Photo {shape[layout.photo.shape]}, à sa place")
    if layout.pictures:
        kept.append("Icônes et images, à leur place")
    same = sorted({fonts.get(f).name for f, badge in layout.fonts.values() if badge != "proche"})
    if same:
        kept.append("Police " + ", ".join(same))
    if diff.lines and diff.in_place >= 0.999 and not scanned:
        kept.append(f"Chaque ligne à sa place exacte (écart maximal {diff.max_shift:.1f} pt)")
    elif not scanned:
        kept.append(f"{round(100 * diff.in_place)} % des lignes à leur place exacte")
    if not diff.restyled:
        kept.append("Gras, italiques, couleurs et tailles du texte")
    for pdf, (font_id, badge) in sorted(layout.fonts.items()):
        if badge == "proche":
            differences.append(
                f"Police {pdf} : remplacée par {fonts.get(font_id).name}, la plus proche"
            )
    differences += clone_report.phrases(diff, scanned)
    return kept, differences


@router.post("/import/{import_id}/clone")
async def clone_preview(import_id: str, body: PreviewIn) -> CloneOut:
    """Le CV lu, dans la forme de son PDF : le clone, ancré mot à mot, et sa ressemblance."""
    origin = _folder(import_id)
    source = origin / cv_import.SOURCE
    folder = origin / CLONE_DIR
    folder.mkdir(exist_ok=True)
    content = body.content.model_copy(deep=True)
    if content.header.photo and (origin / photo.PHOTO).exists():
        shutil.copy(origin / photo.PHOTO, folder / photo.PHOTO)
        content.header.photo = photo.PHOTO
    else:
        content.header.photo = ""
    # Un scan : les pages et leurs mots viennent de Tesseract et de l'image.
    scanned = cv_import.is_scanned(import_id)
    async with _PREVIEWS[f"{import_id}/clone"]:
        try:
            pages = await asyncio.to_thread(cv_import.pages_of, import_id)
            result = await asyncio.to_thread(
                clone_build.clone_into, folder, source, content, True, pages, scanned
            )
        except LatexNotInstalled as error:
            raise HTTPException(503, str(error)) from None
        if not result.ok:
            return CloneOut(available=True, reason="Le clone n'a pas pu être mis en page.")
        words = [clone_scan.words(p) for p in ocr.load(origin) or []] if scanned else None
        measured = await asyncio.to_thread(likeness.measure, source, folder / cv_store.PDF, words)
        diff = await asyncio.to_thread(
            clone_report.compare, pages, folder / cv_store.PDF, 3.0 if scanned else 1.0
        )
    layout = cv_store.load_clone(folder)
    if not isinstance(layout, clone_plan.AnchoredLayout):
        return CloneOut(available=True, reason="Le clone n'a pas pu être mis en page.")
    if scanned:
        # Un scan ne dit pas sa police : elle est devinée à ses largeurs.
        layout.fonts = {name: (font_id, "proche") for name, (font_id, _) in layout.fonts.items()}
    kept, differences = _summary(layout, diff, scanned)
    if scanned:
        differences.insert(
            0,
            "CV scanné : le texte est lu par reconnaissance de caractères et la police est "
            "devinée ; relis bien chaque rubrique",
        )
    if scanned:
        recommended = measured.score >= 93 and not diff.overlaps
    else:
        recommended = (
            measured.score >= 97
            and not diff.missing
            and not diff.overlaps
            and not diff.overflow
            and diff.in_place >= 0.98
        )
    return CloneOut(
        available=True,
        ok=True,
        recommended=recommended,
        warning=None
        if recommended
        else "Ce clone n'est pas assez fidèle à ton PDF (voir ci-dessous) : relis-le de près, "
        "ou choisis « Proche du mien ».",
        likeness=measured.score,
        fonts=[
            CloneFont(pdf=pdf, name=fonts.get(font_id).name, badge=badge)
            for pdf, (font_id, badge) in sorted(layout.fonts.items())
        ],
        kept=kept,
        differences=differences,
    )


@router.get("/import/{import_id}/clone.pdf")
def clone_pdf(import_id: str) -> FileResponse:
    file = _folder(import_id) / CLONE_DIR / cv_store.PDF
    if not file.exists():
        raise HTTPException(404, "Pas encore de clone.")
    return FileResponse(file, media_type="application/pdf", headers={"Cache-Control": "no-store"})


@router.get("/import/{import_id}/preview.pdf")
def preview_pdf(import_id: str) -> FileResponse:
    file = _folder(import_id) / "apercu" / cv_store.PDF
    if not file.exists():
        raise HTTPException(404, "Pas encore d'aperçu.")
    return FileResponse(file, media_type="application/pdf")


@router.post("/apply")
async def apply(body: ApplyIn) -> ApplyOut:
    """Le CV devient un CV classique (nouveau, ou à la place d'un autre) ; la bibliothèque
    reçoit ce qu'il contient."""
    new_name = (body.new_name or "").strip()
    if not new_name:
        try:
            replaced = cv_store.folder(body.target)
        except cv_store.UnknownCV:
            raise HTTPException(404, "CV classique introuvable") from None
        if cv_store.load_meta(replaced).kind != "base":
            raise HTTPException(409, "Seul un CV classique peut être remplacé ici.")
    # Un nouveau CV classique part du style de la première version ; un remplacé garde le sien.
    style, content = _styled(
        body.import_id, body.content, body.keep, cv_store.BASE_SLUG if new_name else body.target
    )
    source_photo = None
    if body.import_id is not None:
        candidate = _folder(body.import_id) / photo.PHOTO
        if body.keep_photo and candidate.exists():
            source_photo = candidate
    if new_name:
        slug, base = cv_store.new_folder(new_name)
        cv_store.save_meta(base, CVMeta(name=new_name, kind="base"))
    else:
        slug, base = body.target, replaced
        # L'ancien CV classique reste récupérable dans la corbeille.
        cv_store.TRASH_DIR.mkdir(parents=True, exist_ok=True)
        stamp = now().strftime("%Y%m%d-%H%M%S")
        shutil.copytree(
            base, cv_store.TRASH_DIR / f"{slug}-{stamp}", ignore=shutil.ignore_patterns("build")
        )
    if source_photo is not None:
        content.header.photo = photo.store(base, source_photo.read_bytes())
    else:
        # Vide, et non None : un champ None n'est pas écrit, et la photo par défaut reviendrait.
        content.header.photo = ""
    cv_store.save_content(base, content)
    cv_store.save_style(base, style)
    cv_store.touch(base, welcome=False)
    # La forme du PDF, clonée à la relecture ; sinon le style de l'appli (l'ancien clone part).
    cloned = _folder(body.import_id) / CLONE_DIR if body.import_id else None
    if body.clone and cloned is not None and (cloned / cv_store.CLONE).exists():
        cv_store.copy_clone(cloned, base)
        cv_store.touch(base, shape="clone" if body.clone_active else "app")
    else:
        cv_store.remove_clone(base)
        cv_store.touch(base, shape="clone")
    if new_name:
        # Le premier lancement est passé : l'accueil ne se rouvre plus sur la première version.
        main = _base()
        cv_store.save_meta(main, cv_store.load_meta(main).model_copy(update={"welcome": False}))

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
    return ApplyOut(added=added, compile=await compile_now(slug), slug=slug)
