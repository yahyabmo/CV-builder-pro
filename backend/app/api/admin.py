"""Administration de la version en ligne, réservée à ``CVB_ADMIN``.

Inviter et retirer des personnes, voir leurs candidatures et leurs CV en lecture seule,
effacer leurs données. Toute autre personne connectée reçoit 403 ; en local, 404.
"""

import asyncio
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from app import paths, people, settings
from app.ai import llm
from app.api.cvs import summary
from app.api.export import build_zip
from app.api.schemas import CVSummary
from app.paths import as_user, current_user, server_mode, user_root
from app.storage import cv_store


def _only_admin() -> None:
    if not server_mode():
        raise HTTPException(404, "Adresse inconnue")
    if not people.is_admin(current_user()):
        raise HTTPException(403, "Réservé à l'administrateur.")


router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(_only_admin)])


class PersonOut(BaseModel):
    email: str
    invited: str | None
    removed: str | None
    last_seen: str | None
    admin: bool
    cvs: int | None
    applications: int | None
    due: int | None
    ai_left: int | None
    ai_quota: int | None


class PeopleOut(BaseModel):
    people: list[PersonOut]
    spent: float | None
    budget: float | None
    # Le groupe Cloudflare Access est réglé : l'invitation suffit pour se connecter.
    cloudflare: bool
    # Un échec de Cloudflare lors du dernier changement.
    warning: str | None = None


class InviteIn(BaseModel):
    email: str


def _email(raw: str) -> str:
    try:
        return people.clean(raw)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


def _folder(email: str) -> Path:
    return paths.DATA_DIR / "users" / email


def _counts(email: str) -> tuple[int | None, int | None, int | None]:
    if not (_folder(email) / "base").is_dir():
        return None, None, None
    with as_user(email):
        found = [summary(slug) for slug, _ in cv_store.list_all()]
    targeted = [cv for cv in found if cv.meta.kind == "cv"]
    return len(found), len(targeted), sum(cv.due for cv in targeted)


async def _relay(email: str | None) -> dict:
    ai = settings.load()
    code = settings.secret("relais")
    if not code or not ai.relais_url:
        return {}
    try:
        return await llm.verify_code(ai.relais_url, code, email or current_user())
    except llm.LLMError:
        return {}


async def _list(warning: str | None = None) -> PeopleOut:
    known = people.load()
    emails = sorted(set(known) | people.admins())
    answers = await asyncio.gather(*(_relay(e) for e in emails))
    out = []
    for email, answer in zip(emails, answers, strict=True):
        person = known.get(email)
        cvs, applications, due = await asyncio.to_thread(_counts, email)
        out.append(
            PersonOut(
                email=email,
                invited=person.invited if person else None,
                removed=person.removed if person else None,
                last_seen=person.last_seen if person else None,
                admin=people.is_admin(email),
                cvs=cvs,
                applications=applications,
                due=due,
                ai_left=answer.get("reste_jour"),
                ai_quota=answer.get("quota_jour"),
            )
        )
    first = next((a for a in answers if a), {})
    return PeopleOut(
        people=out,
        spent=first.get("depense_mois"),
        budget=first.get("budget_mois"),
        cloudflare=people.cloudflare_ready(),
        warning=warning,
    )


async def _synced() -> str | None:
    try:
        await asyncio.to_thread(people.sync)
    except people.SyncError as error:
        return f"{error}. Le changement vaut dans l'appli ; réessaie pour Cloudflare."
    return None


@router.get("/people")
async def list_people() -> PeopleOut:
    return await _list()


@router.post("/people")
async def invite(body: InviteIn) -> PeopleOut:
    email = _email(body.email)
    people.invite(email)
    return await _list(await _synced())


@router.delete("/people/{email}")
async def remove(email: str) -> PeopleOut:
    email = _email(email)
    if people.is_admin(email):
        raise HTTPException(409, "L'administrateur ne peut pas se retirer lui-même.")
    try:
        people.remove(email)
    except KeyError:
        raise HTTPException(404, "Personne inconnue.") from None
    return await _list(await _synced())


@router.delete("/people/{email}/data")
async def erase(email: str) -> PeopleOut:
    """Efface pour de bon les données d'une personne dont l'accès est déjà retiré."""
    email = _email(email)
    person = people.load().get(email)
    if person is None or person.removed is None:
        raise HTTPException(409, "Retire d'abord l'accès de cette personne.")
    shutil.rmtree(_folder(email), ignore_errors=True)
    people.forget(email)
    return await _list()


class PersonDetail(BaseModel):
    email: str
    cvs: list[CVSummary]


@router.get("/people/{email}")
def person(email: str) -> PersonDetail:
    email = _email(email)
    if not (_folder(email) / "base").is_dir():
        return PersonDetail(email=email, cvs=[])
    with as_user(email):
        return PersonDetail(email=email, cvs=[summary(slug) for slug, _ in cv_store.list_all()])


@router.get("/people/{email}/cvs/{slug}/pdf")
def person_pdf(email: str, slug: str) -> FileResponse:
    email = _email(email)
    with as_user(email):
        try:
            pdf = cv_store.folder(slug) / cv_store.PDF
        except cv_store.UnknownCV:
            raise HTTPException(404, "CV introuvable") from None
    if not pdf.exists():
        raise HTTPException(404, "Ce CV n'a pas encore de PDF.")
    return FileResponse(pdf, media_type="application/pdf", headers={"Cache-Control": "no-store"})


@router.get("/people/{email}/export")
def person_export(email: str) -> FileResponse:
    email = _email(email)
    handle = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    handle.close()
    target = Path(handle.name)
    with as_user(email):
        build_zip(user_root(), target)
    return FileResponse(
        target,
        media_type="application/zip",
        filename=f"cv-builder-pro-{email}.zip",
        background=BackgroundTask(target.unlink, missing_ok=True),
    )
