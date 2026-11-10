"""Les fournisseurs de modèles de langage, derrière une même interface.

Chaque fournisseur reçoit une consigne (système), un message (utilisateur) et
un schéma JSON, et rend le texte JSON produit. ``generate`` s'occupe du reste :

- validation de la réponse par le modèle Pydantic attendu ;
- nouvel essai si la réponse est invalide (avec l'erreur rappelée au modèle) ;
- attente puis nouvel essai si le fournisseur est surchargé ou limite le
  débit (429, 500, 503, délai dépassé) ;
- pour Gemini, passage au modèle suivant de la liste quand le premier est
  surchargé ou que son quota gratuit du jour est épuisé (voir ``quota``).

Les clés ne sont jamais écrites dans un journal ni dans un message d'erreur.
"""

import asyncio
import hashlib
import json
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app import settings as settings_module
from app.ai import quota
from app.paths import DEMO_DIR, LOCAL_DIR, current_user, server_mode
from app.settings import AISettings

Notify = Callable[[str], Awaitable[None]]

TIMEOUT = httpx.Timeout(120, connect=15)
# Attentes successives quand le fournisseur est surchargé.
BACKOFF = (3, 10, 25)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.thinking_tokens += other.thinking_tokens


@dataclass
class Completion:
    text: str
    usage: Usage
    model: str


@dataclass
class LLMResult[T: BaseModel]:
    data: T
    usage: Usage
    model: str
    seconds: float
    attempts: int = 1
    notes: list[str] = field(default_factory=list)


class LLMError(Exception):
    """Une erreur du fournisseur. ``retryable`` : réessayer plus tard a un sens."""

    def __init__(
        self,
        message: str,
        retryable: bool = False,
        status: int | None = None,
        quota_until: float | None = None,
        auth: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.status = status
        # Quota du jour épuisé : l'instant (epoch) où il revient.
        self.quota_until = quota_until
        # Le fournisseur refuse la clé d'API.
        self.auth = auth


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    async def complete(
        self, system: str, user: str, schema: dict[str, Any], notify: "Notify | None" = None
    ) -> Completion: ...


def _retry_delay(error: dict[str, Any], message: str) -> float | None:
    """Le délai avant de réessayer, en secondes (RetryInfo, sinon « retry in 12h3m4s »)."""
    for detail in error.get("details") or []:
        if str(detail.get("@type", "")).endswith("RetryInfo"):
            found = re.match(r"([\d.]+)s", str(detail.get("retryDelay", "")))
            if found:
                return float(found.group(1))
    found = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", message)
    if found and any(found.groups()):
        h, m, sec = (float(x or 0) for x in found.groups())
        return h * 3600 + m * 60 + sec
    return None


def _http_error(provider: str, response: httpx.Response, model: str = "") -> LLMError:
    error: dict[str, Any] = {}
    try:
        body = response.json()
        if isinstance(body.get("error"), dict):
            error = body["error"]
            message = error.get("message", "")
        else:
            message = body.get("message") or body.get("error")
    except ValueError:
        message = response.text[:200]
    status = response.status_code
    retryable = status in (429, 500, 502, 503, 504)
    # Gemini répond 400 « API key not valid » à une clé fausse.
    auth = status in (401, 403) or (
        status == 400 and ("API key" in str(message) or "API_KEY_INVALID" in response.text)
    )
    if auth:
        return LLMError(
            f"{provider} refuse la clé d'API (Réglages) : {message}", status=status, auth=True
        )
    if status == 429:
        delay = _retry_delay(error, str(message))
        daily = any(
            "PerDay" in str(v.get("quotaId", ""))
            for d in error.get("details") or []
            for v in d.get("violations") or []
        )
        if daily or (delay is not None and delay > 120):
            until = time.time() + (delay or 3600)
            return LLMError(
                f"{provider} : quota gratuit du jour épuisé pour {model}, "
                f"de retour vers {datetime.fromtimestamp(until):%H:%M}.",
                status=status,
                quota_until=until,
            )
    return LLMError(f"{provider} ({status}) : {message}", retryable=retryable, status=status)


class GeminiProvider(LLMProvider):
    name = "gemini"
    label = "Gemini"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, models: list[str], temperature: float) -> None:
        self._key = api_key
        # Le premier d'abord ; les suivants quand il est surchargé ou épuisé.
        self.models = list(dict.fromkeys(m for m in models if m))
        self.model = self.models[0]
        self.temperature = temperature

    def _endpoint(self, model: str) -> str:
        return self.URL.format(model=model)

    def _headers(self) -> dict[str, str]:
        # La clé part dans un en-tête, jamais dans l'adresse.
        return {"x-goog-api-key": self._key}

    def _error(self, response: httpx.Response, model: str) -> LLMError:
        return _http_error("Gemini", response, model)

    async def _call(self, model: str, system: str, user: str, schema: dict[str, Any]) -> Completion:
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(
                    self._endpoint(model), headers=self._headers(), json=payload
                )
        except httpx.TimeoutException:
            raise LLMError(f"{self.label} ne répond pas (délai dépassé)", retryable=True) from None
        except httpx.HTTPError as error:
            raise LLMError(
                f"{self.label} injoignable : {type(error).__name__}", retryable=True
            ) from None
        if response.status_code != 200:
            raise self._error(response, model)
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates or not candidates[0].get("content", {}).get("parts"):
            reason = (candidates[0].get("finishReason") if candidates else None) or data.get(
                "promptFeedback", {}
            ).get("blockReason", "réponse vide")
            raise LLMError(f"Gemini n'a pas répondu ({reason})", retryable=True)
        text = "".join(part.get("text", "") for part in candidates[0]["content"]["parts"])
        meta = data.get("usageMetadata", {})
        usage = Usage(
            input_tokens=meta.get("promptTokenCount", 0),
            output_tokens=meta.get("candidatesTokenCount", 0),
            thinking_tokens=meta.get("thoughtsTokenCount", 0),
        )
        return Completion(text=text, usage=usage, model=model)

    async def complete(
        self, system: str, user: str, schema: dict[str, Any], notify: Notify | None = None
    ) -> Completion:
        busy: LLMError | None = None
        for n, model in enumerate(self.models):
            if quota.is_blocked(model):
                continue
            try:
                return await self._call(model, system, user, schema)
            except LLMError as error:
                if error.quota_until:
                    quota.block(model, error.quota_until)
                elif not error.retryable:
                    raise
                else:
                    busy = busy or error
                following = next((m for m in self.models[n + 1 :] if not quota.is_blocked(m)), None)
                if following and notify:
                    why = "quota du jour épuisé" if error.quota_until else "surchargé"
                    await notify(f"{model} : {why}, je passe à {following}…")
        if busy:
            raise busy
        back = min(quota.blocked().get(m, 0) for m in self.models)
        raise LLMError(
            "Quota gratuit du jour épuisé pour tous les modèles Gemini "
            f"({', '.join(self.models)}), "
            f"de retour vers {datetime.fromtimestamp(back):%H:%M}. En attendant, choisis Mistral "
            "ou Ollama dans Réglages."
        )


class RelayProvider(GeminiProvider):
    """Gemini par le relais de Yahya (dossier relais/) : un code d'accès au lieu d'une clé.

    Le relais imite l'adresse de Google, impose son modèle et applique un quota par
    jour et un plafond par mois ; ses refus arrivent au format des erreurs de Gemini.
    """

    name = "relais"
    label = "Le relais de Yahya"

    def __init__(
        self, url: str, code: str, model: str, temperature: float, user: str | None = None
    ) -> None:
        super().__init__(code, [model], temperature)
        self.base = url.rstrip("/")
        # En ligne : l'e-mail de la personne connectée, pour son quota du jour.
        self.user = user

    def _endpoint(self, model: str) -> str:
        return f"{self.base}/v1beta/models/{model}:generateContent"

    def _headers(self) -> dict[str, str]:
        return relay_headers(self._key, self.user)

    def _error(self, response: httpx.Response, model: str) -> LLMError:
        return relay_error(response, model)

    async def complete(
        self, system: str, user: str, schema: dict[str, Any], notify: Notify | None = None
    ) -> Completion:
        # Un seul modèle, celui du relais : pas de repli d'un modèle à l'autre.
        return await self._call(self.model, system, user, schema)


def relay_headers(code: str, user: str | None = None) -> dict[str, str]:
    """Le code d'accès, et en ligne l'empreinte de l'e-mail : le relais ne voit pas l'adresse."""
    headers = {"authorization": f"Bearer {code}"}
    if user:
        headers["x-cvb-utilisateur"] = hashlib.sha256(user.encode()).hexdigest()
    return headers


def relay_error(response: httpx.Response, model: str = "") -> LLMError:
    """Un refus du relais : code inconnu, quota du jour, crédit du mois ; sinon, Google."""
    try:
        error = response.json().get("error") or {}
    except ValueError:
        error = {}
    kind = error.get("status", "") if isinstance(error, dict) else ""
    message = error.get("message", "") if isinstance(error, dict) else ""
    if response.status_code == 401 or kind == "CODE":
        return LLMError(
            "Code d'accès refusé : vérifie-le dans Réglages, ou demande-en un à Yahya.",
            status=response.status_code,
            auth=True,
        )
    if kind in ("QUOTA_JOUR", "PLAFOND_MOIS"):
        return LLMError(message, status=response.status_code)
    return _http_error("Gemini (relais de Yahya)", response, model)


async def verify_code(url: str, code: str, user: str | None = None) -> dict[str, Any]:
    """Le relais reconnaît-il ce code ? Sans appel au modèle, donc sans dépense."""
    if not url:
        raise LLMError("Le relais de Yahya n'est pas encore en service")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{url.rstrip('/')}/v1/verifier", headers=relay_headers(code, user)
            )
    except httpx.HTTPError as error:
        raise LLMError(
            f"Le relais de Yahya est injoignable ({type(error).__name__})", retryable=True
        ) from None
    if response.status_code != 200:
        raise relay_error(response)
    return response.json()


class MistralProvider(LLMProvider):
    name = "mistral"
    URL = "https://api.mistral.ai/v1/chat/completions"

    def __init__(self, api_key: str, model: str, temperature: float) -> None:
        self._key = api_key
        self.model = model
        self.temperature = temperature

    async def complete(
        self, system: str, user: str, schema: dict[str, Any], notify: Notify | None = None
    ) -> Completion:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema.get("title", "reponse"), "schema": schema},
            },
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(
                    self.URL, headers={"Authorization": f"Bearer {self._key}"}, json=payload
                )
        except httpx.TimeoutException:
            raise LLMError("Mistral ne répond pas (délai dépassé)", retryable=True) from None
        except httpx.HTTPError as error:
            raise LLMError(
                f"Mistral injoignable : {type(error).__name__}", retryable=True
            ) from None
        if response.status_code != 200:
            raise _http_error("Mistral", response)
        data = response.json()
        usage = data.get("usage", {})
        return Completion(
            text=data["choices"][0]["message"]["content"],
            usage=Usage(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)),
            model=data.get("model", self.model),
        )


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, url: str, model: str, temperature: float) -> None:
        self.url = url.rstrip("/")
        self.model = model
        self.temperature = temperature

    async def complete(
        self, system: str, user: str, schema: dict[str, Any], notify: Notify | None = None
    ) -> Completion:
        payload = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "options": {"temperature": self.temperature},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        try:
            # Sur le processeur seul, un modèle local peut prendre plusieurs minutes.
            async with httpx.AsyncClient(timeout=httpx.Timeout(900, connect=10)) as client:
                response = await client.post(f"{self.url}/api/chat", json=payload)
        except httpx.ConnectError:
            raise LLMError(
                "Ollama ne tourne pas : lance « sudo systemctl start ollama »."
            ) from None
        except httpx.TimeoutException:
            raise LLMError("Ollama ne répond pas (délai dépassé)", retryable=True) from None
        if response.status_code != 200:
            raise _http_error("Ollama", response)
        data = response.json()
        return Completion(
            text=data["message"]["content"],
            usage=Usage(data.get("prompt_eval_count", 0), data.get("eval_count", 0)),
            model=self.model,
        )


class FakeProvider(LLMProvider):
    """Réponses prévues d'avance, pour les tests : une fonction (titre du schéma → objet)."""

    name = "fake"
    model = "faux-modele"

    def __init__(self, answer: Callable[[str, str, dict[str, Any]], Any]) -> None:
        self.answer = answer
        self.calls: list[tuple[str, str]] = []

    async def complete(
        self, system: str, user: str, schema: dict[str, Any], notify: Notify | None = None
    ) -> Completion:
        self.calls.append((schema.get("title", ""), user))
        produced = self.answer(schema.get("title", ""), user, schema)
        text = produced if isinstance(produced, str) else json.dumps(produced, ensure_ascii=False)
        return Completion(text=text, usage=Usage(len(user) // 4, len(text) // 4), model=self.model)


# Réponses enregistrées du faux modèle (titre du schéma → réponse), écrites par
# les essais de l'interface (frontend/scripts/e2e-target.mjs).
FAKE_ANSWERS = LOCAL_DIR / "fake-llm.json"
# Le mode démo : des réponses enregistrées pour l'offre d'exemple et le CV fictif.
DEMO_ANSWERS = DEMO_DIR / "reponses-ia.json"
DEMO_OFFER = DEMO_DIR / "offre-exemple.txt"


class DemoProvider(FakeProvider):
    """Rejoue les réponses de ``demo/`` : on essaie l'appli sans clé d'API."""

    name = "demo"
    model = "réponses enregistrées"

    def __init__(self) -> None:
        answers = json.loads(DEMO_ANSWERS.read_text(encoding="utf-8"))

        def answer(title: str, *_: Any) -> Any:
            if title not in answers:
                raise LLMError(
                    "Le mode démo n'a de réponses que pour le ciblage et la lettre de "
                    "l'offre d'exemple. Choisis un vrai modèle dans Réglages."
                )
            return answers[title]

        super().__init__(answer)


def provider_from_settings(ai: AISettings | None = None) -> LLMProvider:
    ai = ai or settings_module.load()
    if server_mode() and ai.provider == "relais":
        # En ligne, le relais de Yahya au nom de la personne connectée (son quota du jour).
        code = settings_module.secret("relais")
        user = current_user()
        if not code or not ai.relais_url or not user:
            raise LLMError("L'IA n'est pas encore prête sur ce serveur : préviens Yahya.")
        return RelayProvider(ai.relais_url, code, ai.relais_model, ai.temperature, user)
    if server_mode() and ai.provider not in ("gemini", "mistral"):
        raise LLMError("En ligne : choisis Gemini de Yahya, ta clé Gemini ou ta clé Mistral.")
    if ai.provider == "relais":
        code = settings_module.secret("relais")
        if not code:
            raise LLMError("Pas de code d'accès au relais de Yahya : ajoute-le dans Réglages.")
        if not ai.relais_url:
            raise LLMError(
                "Le relais de Yahya n'est pas encore en service : choisis ta propre clé "
                "Gemini dans Réglages."
            )
        return RelayProvider(ai.relais_url, code, ai.relais_model, ai.temperature)
    if ai.provider == "gemini":
        key = settings_module.secret("gemini")
        if not key:
            raise LLMError("Pas de clé Gemini : ajoute-la dans Réglages.")
        return GeminiProvider(key, [ai.gemini_model, *ai.gemini_fallbacks], ai.temperature)
    if ai.provider == "mistral":
        key = settings_module.secret("mistral")
        if not key:
            raise LLMError("Pas de clé Mistral : ajoute-la dans Réglages.")
        return MistralProvider(key, ai.mistral_model, ai.temperature)
    if ai.provider == "ollama":
        return OllamaProvider(ai.ollama_url, ai.ollama_model, ai.temperature)
    if ai.provider == "demo":
        return DemoProvider()
    if FAKE_ANSWERS.exists():
        answers = json.loads(FAKE_ANSWERS.read_text(encoding="utf-8"))
        return FakeProvider(lambda title, *_: answers[title])
    raise LLMError("Le faux modèle ne sert qu'aux tests.")


async def try_key(
    provider: str, key: str, system: str, user: str, schema: dict[str, Any]
) -> Completion:
    """Un seul appel avec cette clé, sans repli ni nouvel essai : la clé marche-t-elle ?

    Pour Gemini, le modèle le plus léger de la liste : le quota du modèle principal
    reste aux vraies demandes.
    """
    ai = settings_module.load()
    if provider == "gemini":
        model = ai.gemini_fallbacks[-1] if ai.gemini_fallbacks else ai.gemini_model
        return await GeminiProvider(key, [model], ai.temperature)._call(model, system, user, schema)
    if provider == "mistral":
        return await MistralProvider(key, ai.mistral_model, ai.temperature).complete(
            system, user, schema
        )
    raise LLMError(f"Pas de clé pour {provider}.")


async def _quiet(_: str) -> None:
    return None


async def generate[T: BaseModel](
    provider: LLMProvider,
    system: str,
    user: str,
    expected: type[T],
    notify: Notify = _quiet,
    attempts: int = 3,
) -> LLMResult[T]:
    """Un appel structuré : la réponse est validée par ``expected``."""
    schema = expected.model_json_schema()
    usage = Usage()
    started = time.monotonic()
    notes: list[str] = []
    message = user
    waits = list(BACKOFF)
    attempt = 0
    while True:
        attempt += 1
        try:
            completion = await provider.complete(system, message, schema, notify)
        except LLMError as error:
            if error.retryable and waits:
                wait = waits.pop(0)
                notes.append(error.message)
                await notify(
                    f"{provider.name.capitalize()} est surchargé, nouvel essai dans {wait} s…"
                )
                await asyncio.sleep(wait)
                continue
            raise
        usage.add(completion.usage)
        try:
            data = expected.model_validate_json(completion.text)
        except ValidationError as error:
            if attempt >= attempts:
                detail = error.errors()[0]["msg"]
                raise LLMError(
                    f"Réponse du modèle invalide après {attempt} essais : {detail}"
                ) from None
            notes.append(f"réponse invalide (essai {attempt})")
            await notify("Réponse incomplète du modèle, nouvel essai…")
            message = (
                f"{user}\n\nTa réponse précédente ne respectait pas le schéma JSON "
                f"({error.errors()[0]['loc']} : {error.errors()[0]['msg']}). "
                "Réponds de nouveau, en JSON valide et complet."
            )
            continue
        return LLMResult(
            data=data,
            usage=usage,
            model=completion.model,
            seconds=round(time.monotonic() - started, 2),
            attempts=attempt,
            notes=notes,
        )
