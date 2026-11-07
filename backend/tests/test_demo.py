"""Le mode démo : le ciblage et la lettre de l'offre d'exemple, sans clé d'API."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import settings
from app.ai import letter as letter_ai
from app.ai import llm, quota, targeting, usage_log
from app.ai.schemas import LetterDraft, OfferAnalysis
from app.ai.targeting import TargetOptions
from app.models.content import CVContent
from app.models.letter import LetterContent
from app.models.library import Library
from app.offer.fetch import Offer
from app.services import rules
from app.settings import AISettings


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(targeting, "DRAFTS_DIR", tmp_path / "drafts")
    monkeypatch.setattr(usage_log, "USAGE_FILE", tmp_path / "usage.json")
    monkeypatch.setattr(quota, "QUOTA_FILE", tmp_path / "quota.json")
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(rules, "RULES_DIR", tmp_path / "rules")


async def _quiet(_: dict[str, Any]) -> None:
    return None


def test_demo_needs_no_key() -> None:
    assert settings.has_key("demo")
    provider = llm.provider_from_settings(AISettings(provider="demo"))
    assert isinstance(provider, llm.DemoProvider) and provider.name == "demo"


def test_demo_targets_the_sample_offer(base_content: CVContent) -> None:
    offer = Offer(text=llm.DEMO_OFFER.read_text(encoding="utf-8"))
    draft = asyncio.run(
        targeting.run(
            "base",
            base_content,
            Library(),
            offer,
            TargetOptions(),
            llm.DemoProvider(),
            _quiet,
        )
    )
    by_id = {c.id: c for c in draft.changes}
    assert draft.analysis.company == "Nordia"
    # Ce que le CV fictif n'a pas arrive « à confirmer », jamais d'office.
    pending = {term for change in draft.changes for term in change.pending}
    assert "LangChain" in pending
    assert by_id["exp-experience-0"].after.count("\n") == 3
    # Sans confirmation, le score ne baisse pas ; LangChain manque tant qu'il n'est pas confirmé.
    assert draft.score_after.score >= draft.score_before.score
    assert "LangChain" in draft.score_after.absent


def test_demo_letter_has_no_alert(base_content: CVContent) -> None:
    answers = json.loads(llm.DEMO_ANSWERS.read_text(encoding="utf-8"))
    draft = LetterDraft.model_validate(answers["LetterDraft"])
    letter = LetterContent(**draft.model_dump())
    analysis = OfferAnalysis.model_validate(answers["OfferAnalysis"])
    # Ni tournure « IA », ni longueur hors norme, ni terme absent du CV fictif.
    assert letter_ai.checks(letter, base_content, Library(), analysis) == []


def test_demo_says_what_it_cannot_do() -> None:
    with pytest.raises(llm.LLMError, match="mode démo"):
        asyncio.run(llm.DemoProvider().complete("", "", {"title": "ProjectDraft"}))


def test_sample_offer_route(client: TestClient) -> None:
    assert "Nordia" in client.get("/api/target/demo-offer").json()["text"]
