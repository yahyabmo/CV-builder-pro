"""L'écran de démarrage : clés d'API écrites dans .env, état de l'accueil, machine."""

import json
import stat
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import settings
from app.ai import llm
from app.services import machine

SECRET = "AIzaSyFausseCleDEssaiAbcdefGhijklmnopqr"


def _answer(monkeypatch: pytest.MonkeyPatch, error: llm.LLMError | None = None) -> list[str]:
    """Remplace l'appel au fournisseur ; renvoie la liste des clés essayées."""
    tried: list[str] = []

    async def fake(provider: str, key: str, *_: object) -> llm.Completion:
        tried.append(key)
        if error:
            raise error
        return llm.Completion(
            text='{"ok": true, "langue": "français"}', usage=llm.Usage(), model="m"
        )

    monkeypatch.setattr(llm, "try_key", fake)
    return tried


def test_write_key_keeps_the_rest_of_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text("# mes réglages\nLLM_PROVIDER=gemini\nGEMINI_API_KEY=ancienne\nAUTRE=1\n")
    monkeypatch.setattr(settings, "ENV_FILE", env)
    settings.write_key("gemini", "nouvelle-cle-123")
    assert env.read_text() == (
        "# mes réglages\nLLM_PROVIDER=gemini\nAUTRE=1\nGEMINI_API_KEY=nouvelle-cle-123\n"
    )
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    settings.delete_key("gemini")
    assert env.read_text() == "# mes réglages\nLLM_PROVIDER=gemini\nAUTRE=1\n"


def test_key_from_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Une clé passée en variable d'environnement (image Docker) compte, même sans .env."""
    monkeypatch.setattr(settings, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setenv("MISTRAL_API_KEY", "cle-de-l-environnement")
    assert settings.has_key("mistral")
    assert settings.key_from_environment("mistral")


def test_a_good_key_is_saved_and_never_returned(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tried = _answer(monkeypatch)
    answer = client.put("/api/settings/keys/gemini", json={"key": f"  {SECRET}\n"})
    assert answer.status_code == 200
    assert answer.json()["ok"] and answer.json()["saved"]
    assert tried == [SECRET]
    assert f"GEMINI_API_KEY={SECRET}" in settings.ENV_FILE.read_text()
    shown = client.get("/api/settings")
    assert shown.json()["keys"]["gemini"] is True
    assert SECRET not in answer.text + shown.text


def test_a_refused_key_is_not_saved(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _answer(monkeypatch, llm.LLMError("refusée", status=400, auth=True))
    answer = client.put("/api/settings/keys/gemini", json={"key": SECRET}).json()
    assert answer["ok"] is False and answer["saved"] is False
    assert "refuse cette clé" in answer["message"]
    assert not settings.ENV_FILE.exists()


def test_a_key_over_quota_is_good(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un quota épuisé prouve que la clé est acceptée : elle est enregistrée."""
    _answer(monkeypatch, llm.LLMError("quota", status=429, quota_until=1.0))
    answer = client.put("/api/settings/keys/mistral", json={"key": SECRET}).json()
    assert answer["ok"] and answer["saved"]
    assert "MISTRAL_API_KEY=" in settings.ENV_FILE.read_text()


def test_unreachable_provider_saves_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answer(monkeypatch, llm.LLMError("Gemini injoignable : ConnectError", retryable=True))
    answer = client.put("/api/settings/keys/gemini", json={"key": SECRET}).json()
    assert answer == {
        "ok": False,
        "saved": False,
        "model": "",
        "seconds": answer["seconds"],
        "message": "Gemini injoignable : ConnectError. Rien n'a été enregistré.",
    }
    assert not settings.ENV_FILE.exists()


@pytest.mark.parametrize("key", ["", "trop court", "avec espace au milieu", "a=b\nAUTRE=1"])
def test_odd_keys_are_refused(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    tried = _answer(monkeypatch)
    assert client.put("/api/settings/keys/gemini", json={"key": key}).status_code == 422
    assert tried == []


def test_only_keyed_providers(client: TestClient) -> None:
    assert client.put("/api/settings/keys/ollama", json={"key": SECRET}).status_code == 404
    assert client.delete("/api/settings/keys/demo").status_code == 404


def test_delete_a_key(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    settings.write_key("gemini", SECRET)
    answer = client.delete("/api/settings/keys/gemini")
    assert answer.status_code == 200 and answer.json()["keys"]["gemini"] is False
    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    refused = client.delete("/api/settings/keys/gemini")
    assert refused.status_code == 409 and "variable d'environnement" in refused.json()["detail"]


def test_gemini_bad_key_is_an_auth_error() -> None:
    """Gemini répond 400 « API key not valid » à une clé fausse."""
    body = {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key."}}
    error = llm._http_error("Gemini", httpx.Response(400, json=body))
    assert error.auth and not error.retryable
    other = llm._http_error("Gemini", httpx.Response(400, json={"error": {"message": "schema"}}))
    assert not other.auth


def test_setup_step_comes_first(client: TestClient) -> None:
    """Tant que l'accueil s'ouvre et que le démarrage n'est pas passé, il vient d'abord."""
    assert client.get("/api/welcome").json() == {"show": True, "setup": True}
    assert client.post("/api/welcome/setup").json() == {"show": True, "setup": False}
    assert json.loads(settings.SETUP_FILE.read_text())["done"]
    client.post("/api/welcome/dismiss")
    assert client.get("/api/welcome").json() == {"show": False, "setup": False}


def test_machine_check(client: TestClient) -> None:
    found = client.get("/api/system/check").json()
    assert [c["id"] for c in found["checks"]] == ["latex", "packages", "poppler"]
    assert found["ok"] == all(c["ok"] for c in found["checks"])


def test_machine_check_without_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rien d'installé : la commande apt à copier, sous Linux comme sous Windows (WSL)."""
    monkeypatch.setattr(machine.shutil, "which", lambda _: None)
    for kind in ("linux", "wsl"):
        monkeypatch.setattr(machine, "system", lambda kind=kind: kind)
        found = machine.check()
        latex, packages, poppler = found.checks
        assert not found.ok
        assert latex.ok is False and latex.fix.startswith("sudo apt install -y texlive-xetex")
        assert packages.ok is None and packages.fix is None
        assert poppler.fix == "sudo apt install -y poppler-utils"
