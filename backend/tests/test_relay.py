"""Le choix « Gemini de Yahya » : le relais (dossier relais/) et son code d'accès.

Le relais est simulé au niveau HTTP : aucun appel réel, aucune vraie clé.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app import settings
from app.ai import llm

URL = "https://relais.exemple.dev"
CODE = "cvb-abcd-efgh-jkmn-pqrs"


def _relay(monkeypatch: pytest.MonkeyPatch, reply: httpx.Response) -> list[httpx.Request]:
    """Remplace le réseau par un faux relais ; renvoie les requêtes reçues."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return reply

    real = httpx.AsyncClient

    def client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        return real(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(llm.httpx, "AsyncClient", client)
    return seen


def _gemini_answer(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [{"content": {"parts": [{"text": text}]}}],
            "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 30},
        },
    )


def _refusal(status: int, kind: str, message: str) -> httpx.Response:
    return httpx.Response(
        status, json={"error": {"code": status, "message": message, "status": kind}}
    )


def test_the_relay_gets_the_code_not_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _relay(monkeypatch, _gemini_answer('{"ok": true}'))
    provider = llm.RelayProvider(URL + "/", CODE, "gemini-3.5-flash-lite", 0.2)
    completion = asyncio.run(provider.complete("système", "question", {"type": "object"}))
    assert completion.text == '{"ok": true}'
    assert completion.usage.input_tokens == 120
    request = seen[0]
    assert str(request.url) == f"{URL}/v1beta/models/gemini-3.5-flash-lite:generateContent"
    assert request.headers["authorization"] == f"Bearer {CODE}"
    assert "x-goog-api-key" not in request.headers
    assert json.loads(request.content)["contents"][0]["parts"][0]["text"] == "question"


@pytest.mark.parametrize(
    ("reply", "auth", "retryable", "words"),
    [
        (_refusal(401, "CODE", "inconnu"), True, False, "Code d'accès refusé"),
        (
            _refusal(429, "QUOTA_JOUR", "Tes 20 demandes du jour sont utilisées."),
            False,
            False,
            "20 demandes",
        ),
        (
            _refusal(429, "PLAFOND_MOIS", "Le crédit offert ce mois-ci est épuisé."),
            False,
            False,
            "crédit",
        ),
        (_refusal(503, "UNAVAILABLE", "Le modèle est surchargé."), False, True, "surchargé"),
    ],
)
def test_relay_refusals_read_plainly(
    monkeypatch: pytest.MonkeyPatch, reply: httpx.Response, auth: bool, retryable: bool, words: str
) -> None:
    _relay(monkeypatch, reply)
    provider = llm.RelayProvider(URL, CODE, "gemini-3.5-flash-lite", 0.2)
    with pytest.raises(llm.LLMError) as caught:
        asyncio.run(provider.complete("s", "u", {}))
    assert caught.value.auth is auth
    assert caught.value.retryable is retryable
    assert words in caught.value.message


def test_provider_needs_a_code_and_an_address(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ai = settings.AISettings(provider="relais", relais_url=URL)
    with pytest.raises(llm.LLMError, match="Pas de code d'accès"):
        llm.provider_from_settings(ai)
    settings.write_key("relais", CODE)
    provider = llm.provider_from_settings(ai)
    assert isinstance(provider, llm.RelayProvider)
    assert provider.base == URL
    with pytest.raises(llm.LLMError, match="pas encore en service"):
        llm.provider_from_settings(settings.AISettings(provider="relais", relais_url=""))


def test_relay_address_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setenv("RELAIS_URL", URL)
    assert settings.load().relais_url == URL
    assert settings.load().model_for("relais") == "gemini-3.5-flash-lite"


def _ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RELAIS_URL", URL)


def test_a_good_code_is_checked_by_the_relay_then_saved(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready(monkeypatch)
    seen = _relay(
        monkeypatch,
        httpx.Response(
            200,
            json={
                "ok": True,
                "nom": "Karim",
                "reste_jour": 20,
                "quota_jour": 20,
                "credit_epuise": False,
                "modele": "gemini-3.5-flash-lite",
            },
        ),
    )
    answer = client.put("/api/settings/keys/relais", json={"key": f" {CODE}\n"}).json()
    assert answer["ok"] and answer["saved"]
    assert (
        answer["message"]
        == "Bienvenue Karim : le code est bon. Il te reste 20 demandes aujourd'hui."
    )
    assert str(seen[0].url) == f"{URL}/v1/verifier"
    assert settings.secret("relais") == CODE
    out = client.get("/api/settings").json()
    assert out["keys"]["relais"] is True and out["relay_ready"] is True
    assert CODE not in json.dumps(out)


def test_an_unknown_code_is_not_saved(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    _relay(monkeypatch, _refusal(401, "CODE", "Code d'accès inconnu ou retiré."))
    answer = client.put("/api/settings/keys/relais", json={"key": CODE}).json()
    assert not answer["ok"] and not answer["saved"]
    assert "n'est pas reconnu" in answer["message"]
    assert settings.secret("relais") is None


def test_no_relay_yet(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un relais sans adresse (réglage vidé) : le choix reste visible, mais rien ne part."""
    monkeypatch.delenv("RELAIS_URL", raising=False)
    local = tmp_path / "settings.json"
    local.write_text('{"relais_url": ""}', encoding="utf-8")
    monkeypatch.setattr(settings, "SETTINGS_FILE", local)
    answer = client.put("/api/settings/keys/relais", json={"key": CODE}).json()
    assert not answer["saved"]
    assert "pas encore en service" in answer["message"]
    assert client.get("/api/settings").json()["relay_ready"] is False


def test_a_code_with_spaces_inside_is_refused_before_any_call(client: TestClient) -> None:
    answer = client.put("/api/settings/keys/relais", json={"key": "cvb abcd efgh"})
    assert answer.status_code == 422
    assert "code d'accès" in answer.json()["detail"]
