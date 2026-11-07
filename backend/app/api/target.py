"""Routes du ciblage d'une offre : lancer, relancer, relire, appliquer.

``POST /api/target`` et ``POST /api/target/drafts/<id>/rerun`` répondent en
flux d'évènements (text/event-stream), un par ligne ``data: {...}`` :

- ``step`` : une étape commence (``label``) ;
- ``wait`` : le fournisseur est surchargé, nouvel essai bientôt (``message``) ;
- ``done`` : la proposition (``draft``) ;
- ``error`` : l'échec, en clair (``message``).
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from app.ai import llm, targeting
from app.ai.schemas import MissingSkill, OfferAnalysis
from app.ai.targeting import Coverage, Draft, TargetOptions
from app.api.cvs import compile_now
from app.api.schemas import CompileOut
from app.offer import fetch
from app.services import ats, library_import
from app.storage import cv_store, library_store

router = APIRouter(prefix="/api/target", tags=["target"])
log = logging.getLogger(__name__)


class TargetIn(BaseModel):
    source: str = cv_store.BASE_SLUG
    text: str | None = None
    url: str | None = None
    projects_count: int | None = Field(default=None, ge=1, le=8)
    language: Literal["auto", "fr", "en"] = "auto"


def _load_source(slug: str) -> Any:
    try:
        path = cv_store.folder(slug)
    except cv_store.UnknownCV:
        raise HTTPException(404, f"CV introuvable : {slug}") from None
    return cv_store.load(path)[0]


def _provider() -> llm.LLMProvider:
    try:
        return llm.provider_from_settings()
    except llm.LLMError as error:
        raise HTTPException(400, error.message) from None


def _stream(work: Callable[[targeting.Emit], Awaitable[Draft]]) -> StreamingResponse:
    """La progression de ``work`` en évènements, puis la proposition ou l'erreur."""
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def emit(event: dict[str, Any]) -> None:
        await queue.put(event)

    async def run() -> None:
        try:
            draft = await work(emit)
            await emit({"type": "done", "draft": draft.model_dump(mode="json")})
        except fetch.OfferUnavailable as error:
            await emit({"type": "error", "message": str(error)})
        except llm.LLMError as error:
            await emit({"type": "error", "message": error.message})
        except Exception as error:  # noqa: BLE001 — l'interface doit toujours recevoir une fin
            log.exception("ciblage")
            await emit({"type": "error", "message": f"Erreur inattendue : {type(error).__name__}"})
        finally:
            await queue.put(None)

    async def stream() -> Any:
        task = asyncio.create_task(run())
        try:
            while (event := await queue.get()) is not None:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            # L'onglet fermé en cours de route : on arrête aussi les appels au modèle.
            task.cancel()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("")
async def start(body: TargetIn) -> StreamingResponse:
    content = _load_source(body.source)
    if not (body.text and body.text.strip()) and not (body.url and body.url.strip()):
        raise HTTPException(422, "Colle le texte de l'offre ou donne son adresse.")
    provider = _provider()

    async def work(emit: targeting.Emit) -> Draft:
        if body.text and body.text.strip():
            offer = fetch.from_text(body.text)
        else:
            await emit({"type": "step", "label": "Lecture de la page"})
            offer = await fetch.from_url(body.url or "")
        return await targeting.run(
            body.source,
            content,
            library_store.load(),
            offer,
            TargetOptions(projects_count=body.projects_count, language=body.language),
            provider,
            emit,
        )

    return _stream(work)


def _draft(draft_id: str) -> Draft:
    try:
        return targeting.load_draft(draft_id)
    except FileNotFoundError:
        raise HTTPException(
            404, "Proposition introuvable (elle a peut-être été effacée avec build/)."
        ) from None


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: str) -> Draft:
    return _draft(draft_id)


@router.post("/drafts/{draft_id}/rerun")
async def rerun(draft_id: str) -> StreamingResponse:
    """Refait le plan et les formulations avec la bibliothèque à jour, sans réanalyser l'offre."""
    draft = _draft(draft_id)
    content = _load_source(draft.source)
    provider = _provider()
    options = TargetOptions(**draft.options)

    async def work(emit: targeting.Emit) -> Draft:
        offer = fetch.Offer(text=draft.offer_text, url=draft.offer_url, title=None)
        return await targeting.run(
            draft.source,
            content,
            library_store.load(),
            offer,
            options,
            provider,
            emit,
            analysis=draft.analysis,
            parent=draft.id,
        )

    return _stream(work)


class Choices(BaseModel):
    # Changements acceptés : identifiant → texte final (retouché ou non).
    accepted: dict[str, str]
    # Retouches de la traduction : chemin → texte.
    translation_edits: dict[str, str] = Field(default_factory=dict)


@router.post("/drafts/{draft_id}/score")
def preview_score(draft_id: str, choices: Choices) -> Coverage:
    """La couverture des mots-clés avec les choix en cours (calcul local, sans IA)."""
    draft = _draft(draft_id)
    source = _load_source(draft.source)
    content = targeting.apply(source, draft, choices.accepted, choices.translation_edits)
    know = targeting.build_knowledge(source, library_store.load())
    return targeting.coverage(draft.analysis, targeting.profile_text(content), know)


class ApplyIn(Choices):
    name: str = Field(min_length=1, max_length=120)
    # Termes confirmés (compétences et mots-clés absents du profil).
    confirmed: list[str] = Field(default_factory=list)


class ApplyOut(BaseModel):
    slug: str
    compile: CompileOut
    score: Coverage | None
    # Termes confirmés ajoutés à la bibliothèque.
    library_added: list[str] = Field(default_factory=list)


@router.post("/drafts/{draft_id}/apply")
async def apply_draft(draft_id: str, body: ApplyIn) -> ApplyOut:
    """Crée le CV ciblé : changements acceptés, offre et analyse jointes, compilé."""
    draft = _draft(draft_id)
    source = _load_source(draft.source)
    known = {c.id for c in draft.changes}
    unknown = set(body.accepted) - known
    if unknown:
        raise HTTPException(422, f"Changements inconnus : {', '.join(sorted(unknown))}")
    # Un retrait ou la traduction n'ont pas de texte ; les autres doivent en avoir un.
    written = {c.id for c in draft.changes if c.kind != "remove" and c.id != "translation"}
    if any(not text.strip() for key, text in body.accepted.items() if key in written):
        raise HTTPException(
            422, "Un changement accepté a un texte vide : retouche-le ou refuse-le."
        )
    missing = targeting.unconfirmed(draft, body.accepted, body.confirmed)
    if missing:
        raise HTTPException(422, f"À confirmer avant de créer le CV : {', '.join(missing)}.")
    content = targeting.apply(source, draft, body.accepted, body.translation_edits)

    # Ce qui a été confirmé et figure dans le CV rejoint la bibliothèque.
    library = library_store.load()
    text = targeting.profile_text(content)
    confirmed = [t for t in body.confirmed if targeting.found(t, text, targeting.Knowledge())]
    added, _ = library_import.add_skills(library, confirmed, source="offre")
    if added:
        library_store.save_skills(library.skills)

    # Les mots d'offre déjà pris, pour que ce CV ait un nom de fichier à lui.
    used = cv_store.labels_in_use()
    slug = cv_store.create(body.name, draft.source)
    path = cv_store.folder(slug)
    cv_store.save_content(path, content)
    (path / "offer.txt").write_text(draft.offer_text + "\n", encoding="utf-8")
    analysis = {
        "draft": draft.id,
        "analysis": draft.analysis.model_dump(mode="json"),
        "plan": draft.plan.model_dump(mode="json"),
    }
    (path / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    cv_store.touch(
        path,
        company=draft.analysis.company or None,
        position=draft.analysis.job_title or None,
        label=cv_store.unique_label(
            cv_store.short_label(draft.analysis.short_name or draft.analysis.job_title),
            draft.analysis.company,
            used,
        )
        or None,
        offer_url=draft.offer_url,
    )
    result = await compile_now(slug)
    score = None
    if result.ok:
        know = targeting.build_knowledge(content, library_store.load())
        score = targeting.coverage(draft.analysis, ats.pdf_text(path / cv_store.PDF), know)
        cv_store.touch(path, score=score.score)
    return ApplyOut(slug=slug, compile=result, score=score, library_added=added)


class OfferInfo(BaseModel):
    text: str
    url: str | None
    analysis: OfferAnalysis
    missing: list[MissingSkill]
    # Recalculé sur le PDF actuel (None tant qu'il n'y a pas de PDF).
    score: Coverage | None


class DemoOffer(BaseModel):
    text: str


@router.get("/demo-offer")
def demo_offer() -> DemoOffer:
    """L'offre d'exemple : la seule pour laquelle le mode démo a des réponses."""
    return DemoOffer(text=llm.DEMO_OFFER.read_text(encoding="utf-8"))


@router.get("/offer/{slug}")
def offer_info(slug: str) -> OfferInfo:
    """L'offre visée par un CV ciblé, son analyse et la couverture de ses mots-clés."""
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
    except (ValueError, KeyError, ValidationError):
        raise HTTPException(422, "L'analyse de l'offre de ce CV est illisible.") from None
    offer = path / "offer.txt"
    meta = cv_store.load_meta(path)
    score = None
    if (path / cv_store.PDF).exists():
        content, _ = cv_store.load(path)
        know = targeting.build_knowledge(content, library_store.load())
        score = targeting.coverage(analysis, ats.pdf_text(path / cv_store.PDF), know)
        if score.score != meta.score:
            cv_store.save_meta(path, meta.model_copy(update={"score": score.score}))
    return OfferInfo(
        text=offer.read_text(encoding="utf-8").strip() if offer.exists() else "",
        url=meta.offer_url,
        analysis=analysis,
        missing=[MissingSkill.model_validate(m) for m in data.get("plan", {}).get("missing", [])],
        score=score,
    )
