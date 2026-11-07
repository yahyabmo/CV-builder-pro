"""Les idées de projet d'un CV ciblé : proposées une fois, gardées, et leur cahier des charges."""

import json

import pytest
from fastapi.testclient import TestClient

from app.ai import llm
from app.storage import cv_store


@pytest.fixture
def targeted(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> str:
    """Un CV ciblé sur l'offre d'exemple, et le mode démo (réponses enregistrées)."""
    monkeypatch.setattr(llm, "provider_from_settings", lambda *_: llm.DemoProvider())
    monkeypatch.setattr("app.api.project_ideas.usage_log.record", lambda *_: None)
    answers = json.loads(llm.DEMO_ANSWERS.read_text(encoding="utf-8"))
    slug = cv_store.create("Nordia", cv_store.BASE_SLUG)
    analysis = {"analysis": answers["OfferAnalysis"], "plan": answers["TargetPlan"]}
    (cv_store.folder(slug) / "analysis.json").write_text(json.dumps(analysis), encoding="utf-8")
    return slug


def test_ideas_are_proposed_then_kept(client: TestClient, targeted: str) -> None:
    assert client.get(f"/api/cvs/{targeted}/project-ideas").json()["ideas"] == []
    made = client.post(f"/api/cvs/{targeted}/project-ideas").json()
    assert len(made["ideas"]) == 3 and made["created_at"]
    first = made["ideas"][0]
    assert first["keywords"] and first["steps"] and first["cv_line"]
    assert client.get(f"/api/cvs/{targeted}/project-ideas").json() == made


def test_brief_is_a_markdown_file(client: TestClient, targeted: str) -> None:
    client.post(f"/api/cvs/{targeted}/project-ideas")
    answer = client.get(f"/api/cvs/{targeted}/project-ideas/0/brief")
    assert answer.status_code == 200
    assert answer.headers["content-type"].startswith("text/markdown")
    assert "cahier-des-charges-assistant-de-maintenance" in answer.headers["content-disposition"]
    text = answer.text
    assert text.startswith("# Assistant de maintenance sur notices")
    for heading in ("## Ce que fait le projet", "## Étapes", "## Sur ton CV, une fois fait"):
        assert heading in text
    assert "Nordia" in text
    assert client.get(f"/api/cvs/{targeted}/project-ideas/7/brief").status_code == 404


def test_a_cv_without_offer_has_no_ideas(client: TestClient) -> None:
    assert client.get("/api/cvs/base/project-ideas").status_code == 404
    assert client.post("/api/cvs/base/project-ideas").status_code == 404
