"""Routes des réglages de l'IA : fournisseur, modèles, clés, essai de connexion, consommation.

Les clés entrent (vérifiées, puis écrites dans .env) mais ne sortent jamais :
l'API dit seulement si chacune est présente.
"""

import time
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import settings, user_keys
from app.ai import llm, quota, usage_log
from app.paths import current_user, server_mode
from app.settings import AISettings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class Usage(BaseModel):
    month: str
    calls: int
    input: int
    output: int
    cost: float | None
    last: str | None


class Online(BaseModel):
    """En ligne : l'IA de Yahya, et ce qu'il reste à la personne connectée aujourd'hui."""

    ok: bool
    left: int | None = None
    quota: int | None = None
    exhausted: bool = False
    message: str = ""


class SettingsOut(BaseModel):
    ai: AISettings
    keys: dict[str, bool]
    usage: Usage
    # Modèles au quota du jour épuisé → heure de retour (ISO).
    blocked: dict[str, str]
    # Le relais de Yahya a une adresse : le choix « Gemini de Yahya » est utilisable.
    relay_ready: bool
    # Présent en mode serveur seulement.
    online: Online | None = None


def _out() -> SettingsOut:
    ai = settings.load()
    if server_mode():
        # La consommation est celle de tout le serveur : elle n'est pas montrée. Les clés
        # sont celles de la personne connectée (présentes ou non, jamais leur valeur).
        return SettingsOut(
            ai=ai,
            keys={p: settings.has_key(p) for p in ("relais", "gemini", "mistral")},
            usage=Usage(month="", calls=0, input=0, output=0, cost=None, last=None),
            blocked={},
            relay_ready=True,
        )
    return SettingsOut(
        ai=ai,
        keys={p: settings.has_key(p) for p in ("relais", "gemini", "mistral", "ollama", "demo")},
        usage=Usage(**usage_log.summary()),
        blocked={
            model: datetime.fromtimestamp(until).isoformat(timespec="minutes")
            for model, until in quota.blocked().items()
        },
        relay_ready=bool(ai.relais_url),
    )


async def _online() -> Online:
    """Le reste du jour de la personne connectée, demandé au relais (sans dépense)."""
    ai = settings.load()
    code = settings.secret("relais")
    if not code or not ai.relais_url:
        return Online(ok=False, message="L'IA n'est pas encore prête sur ce serveur.")
    try:
        answer = await llm.verify_code(ai.relais_url, code, current_user())
    except llm.LLMError as error:
        return Online(ok=False, message=error.message)
    left, total = answer.get("reste_jour"), answer.get("quota_jour")
    return Online(
        ok=True,
        left=left if isinstance(left, int) else None,
        quota=total if isinstance(total, int) else None,
        exhausted=bool(answer.get("credit_epuise")),
    )


def _relay_locked(provider: str) -> None:
    """En ligne, le code du relais est celui du serveur : personne ne le change d'ici."""
    if server_mode() and provider == "relais":
        raise HTTPException(403, "En ligne, le relais de Yahya est déjà prêt : rien à coller.")


@router.get("")
async def get_settings() -> SettingsOut:
    out = _out()
    if server_mode():
        out.online = await _online()
    return out


@router.put("")
def put_settings(ai: AISettings) -> SettingsOut:
    if server_mode() and ai.provider not in user_keys.ONLINE_PROVIDERS:
        raise HTTPException(
            422, "En ligne : Gemini de Yahya, ta clé Gemini ou ta clé Mistral seulement."
        )
    if ai.provider == "fake":
        raise HTTPException(422, "Le faux modèle ne sert qu'aux tests.")
    settings.save(ai)
    return _out()


class _Ping(BaseModel):
    ok: bool = Field(description="Toujours vrai.")
    langue: str = Field(description="Le mot « français ».")


class TestOut(BaseModel):
    ok: bool
    model: str = ""
    seconds: float = 0
    message: str = ""


@router.post("/test")
async def test_connection() -> TestOut:
    """Un petit appel structuré au fournisseur choisi."""
    started = time.monotonic()
    try:
        provider = llm.provider_from_settings()
        result = await llm.generate(
            provider,
            "Tu réponds en JSON selon le schéma.",
            "Réponds ok=true et langue=français.",
            _Ping,
            attempts=1,
        )
    except llm.LLMError as error:
        return TestOut(
            ok=False, seconds=round(time.monotonic() - started, 1), message=error.message
        )
    usage_log.record(provider.name, result.model, result.usage, "Essai de connexion")
    return TestOut(ok=True, model=result.model, seconds=round(time.monotonic() - started, 1))


PROVIDER_NAMES = {"relais": "Le relais de Yahya", "gemini": "Google", "mistral": "Mistral"}


class KeyIn(BaseModel):
    key: str = Field(max_length=400)


class KeyOut(BaseModel):
    ok: bool
    saved: bool
    model: str = ""
    seconds: float = 0
    message: str = ""


def _key_provider(provider: str) -> settings.Provider:
    if provider not in settings.KEYS:
        raise HTTPException(404, f"Pas de clé pour « {provider} ».")
    return provider  # type: ignore[return-value]


@router.put("/keys/{provider}")
async def save_key(provider: str, body: KeyIn) -> KeyOut:
    """Essaie la clé par un petit appel, puis l'écrit dans .env si le fournisseur l'accepte.

    Un quota épuisé prouve que la clé est bonne : elle est enregistrée quand même.
    Une clé refusée, ou un fournisseur injoignable : rien n'est écrit.
    """
    _relay_locked(provider)
    name = _key_provider(provider)
    key = body.key.strip()
    if not settings.KEY_PATTERN.fullmatch(key):
        what = "un code d'accès : copie-le" if name == "relais" else "une clé d'API : copie-la"
        raise HTTPException(422, f"Ça ne ressemble pas à {what} d'un bloc, sans espace.")
    if name == "relais":
        return await _save_code(key)
    started = time.monotonic()
    try:
        completion = await llm.try_key(
            name,
            key,
            "Tu réponds en JSON selon le schéma.",
            "Réponds ok=true et langue=français.",
            _Ping.model_json_schema(),
        )
    except llm.LLMError as error:
        seconds = round(time.monotonic() - started, 1)
        if error.auth:
            return KeyOut(
                ok=False,
                saved=False,
                seconds=seconds,
                message=f"{PROVIDER_NAMES[name]} refuse cette clé. Elle est sans doute "
                "incomplète : recopie-la avec le bouton de copie. Rien n'a été enregistré.",
            )
        if error.status == 429:
            settings.write_key(name, key)
            return KeyOut(
                ok=True,
                saved=True,
                seconds=seconds,
                message="Quota du moment épuisé, mais la clé est bonne : elle est enregistrée.",
            )
        return KeyOut(
            ok=False,
            saved=False,
            seconds=seconds,
            message=f"{error.message}. Rien n'a été enregistré.",
        )
    settings.write_key(name, key)
    usage_log.record(name, completion.model, completion.usage, "Vérification de la clé")
    return KeyOut(
        ok=True, saved=True, model=completion.model, seconds=round(time.monotonic() - started, 1)
    )


async def _save_code(code: str) -> KeyOut:
    """Le code d'accès au relais : vérifié par le relais (sans appel au modèle), puis écrit."""
    started = time.monotonic()
    ai = settings.load()
    try:
        answer = await llm.verify_code(ai.relais_url, code)
    except llm.LLMError as error:
        seconds = round(time.monotonic() - started, 1)
        if error.auth:
            message = (
                "Ce code d'accès n'est pas reconnu : recopie-le d'un bloc, ou demande-en un à "
                "Yahya. Rien n'a été enregistré."
            )
        else:
            message = f"{error.message}. Rien n'a été enregistré."
        return KeyOut(ok=False, saved=False, seconds=seconds, message=message)
    settings.write_key("relais", code)
    name = str(answer.get("nom") or "").strip()
    left = answer.get("reste_jour")
    message = f"Bienvenue{' ' + name if name else ''} : le code est bon."
    if answer.get("credit_epuise"):
        message += " Le crédit offert ce mois-ci est épuisé ; il revient le 1er du mois."
    elif isinstance(left, int):
        message += f" Il te reste {left} demande{'s' if left != 1 else ''} aujourd'hui."
    return KeyOut(
        ok=True,
        saved=True,
        model=str(answer.get("modele") or ai.relais_model),
        seconds=round(time.monotonic() - started, 1),
        message=message,
    )


@router.delete("/keys/{provider}")
def delete_key(provider: str) -> SettingsOut:
    _relay_locked(provider)
    name = _key_provider(provider)
    if settings.key_from_environment(name):
        raise HTTPException(
            409,
            f"Cette clé vient de la variable d'environnement {settings.KEYS[name]} : "
            "retire-la là où elle est définie.",
        )
    settings.delete_key(name)
    return _out()
