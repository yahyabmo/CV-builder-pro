import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai import letter as letter_ai
from app.ai import llm, usage_log
from app.models.content import CVContent
from app.models.letter import LetterContent
from app.services import ats
from app.storage import cv_store, letter_store, library_store
from tests.conftest import needs_latex

DRAFT = {
    "recipient": ["Nordia – Équipe Data & IA", "Grenoble", ""],
    "subject": "Candidature au stage « **Agent IA** analyste de la documentation technique »",
    "salutation": "Madame, Monsieur,",
    "paragraphs": [
        "C'est avec un grand intérêt que je lis votre sujet — un agent qui prouve ses chiffres.",
        "Votre équipe utilise MCP pour outiller l'agent. J'ai déployé Kubernetes en production.",
        "Pendant mon stage, j'ai conçu seul TrafficLens, un outil de **vision** en production.",
    ],
    "closing": "Je vous prie d'agréer, Madame, Monsieur, mes salutations distinguées.",
}
ANALYSIS = {
    "is_job_offer": True,
    "job_title": "Agent IA analyste de la documentation technique",
    "company": "Nordia",
    "location": "Grenoble",
    "offer_language": "fr",
    "required_languages": [],
    "technologies": ["MCP", "Kubernetes"],
    "tools": [],
    "methods": [],
    "skills": [],
    "soft_skills": [],
    "summary": "Construire un agent IA.",
    "keywords": [
        {"term": "MCP", "importance": 2, "category": "techno"},
        {"term": "Kubernetes", "importance": 2, "category": "outil"},
        {"term": "RAG", "importance": 2, "category": "techno"},
    ],
}


@pytest.fixture
def cv(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setattr(library_store, "LIBRARY_DIR", tmp_path / "library")
    monkeypatch.setattr(usage_log, "USAGE_FILE", tmp_path / "usage.json")
    provider = llm.FakeProvider(lambda *_: DRAFT)
    monkeypatch.setattr(llm, "provider_from_settings", lambda: provider)
    slug = client.post("/api/cvs", json={"name": "Nordia lettre"}).json()["slug"]
    folder = cv_store.folder(slug)
    (folder / "analysis.json").write_text(json.dumps({"analysis": ANALYSIS, "plan": {}}))
    (folder / "offer.txt").write_text(
        "Stage : agent IA analyste de la documentation technique chez Nordia."
    )
    return {"slug": slug, "folder": folder, "provider": provider}


@needs_latex
def test_generate_edit_and_export(client: TestClient, cv: dict[str, Any]) -> None:
    slug, folder = cv["slug"], cv["folder"]
    assert client.get(f"/api/cvs/{slug}/letter").json()["letter"] is None

    out = client.post(
        f"/api/cvs/{slug}/letter/generate",
        json={"why": "J'ai déjà mis un assistant en production."},
    ).json()
    letter = out["state"]["letter"]
    # Ses réponses partent au modèle ; le gras ajouté et les lignes vides disparaissent.
    assert "J'ai déjà mis un assistant en production." in cv["provider"].calls[0][1]
    assert letter["recipient"] == ["Nordia – Équipe Data & IA", "Grenoble"]
    assert "**" not in letter["subject"] and "**" not in letter["paragraphs"][2]
    assert letter["signature"] == "Camille Laurent" and letter["place_date"].startswith("Lyon, le ")
    assert letter["why"] == "J'ai déjà mis un assistant en production."

    checks = [c["text"] for c in out["state"]["checks"]]
    assert any("grand intérêt" in c for c in checks) and any("Tiret cadratin" in c for c in checks)
    # Kubernetes, affirmé à la première personne, est signalé ; MCP, qui décrit l'offre, non.
    assert any("Kubernetes" in c for c in checks) and not any("MCP" in c for c in checks)
    assert any(c["kind"] == "longueur" for c in out["state"]["checks"])

    assert out["compile"]["ok"] and out["compile"]["pages"] == 1
    text = ats.pdf_text(folder / letter_store.PDF)
    assert "CAMILLE LAURENT" in text and "Objet" in text and "TrafficLens" in text
    assert out["state"]["file_stem"].startswith("camille_laurent_lettre_agent-ia")
    copied = client.get(f"/api/cvs/{slug}/letter/text").json()["text"]
    assert copied.startswith("Madame, Monsieur,") and copied.rstrip().endswith("Camille Laurent")
    assert "Objet" not in copied

    # Une retouche : la tournure corrigée n'est plus signalée.
    letter["paragraphs"][0] = "Votre sujet m'a arrêté : un agent qui prouve ses chiffres."
    state = client.put(f"/api/cvs/{slug}/letter", json=letter).json()
    assert not any("grand intérêt" in c["text"] or "cadratin" in c["text"] for c in state["checks"])
    assert client.post(f"/api/cvs/{slug}/letter/compile").json()["ok"]
    assert "un agent qui prouve ses chiffres" in ats.pdf_text(folder / letter_store.PDF)


@needs_latex
def test_letter_manual_mode(client: TestClient, cv: dict[str, Any]) -> None:
    slug, folder = cv["slug"], cv["folder"]
    client.post(f"/api/cvs/{slug}/letter/generate", json={})
    source = client.get(f"/api/cvs/{slug}/letter/source").json()
    assert source["mode"] == "visual" and "Lettre de motivation" in source["tex"]
    download = client.get(f"/api/cvs/{slug}/letter/tex")
    assert download.text == source["tex"] and "_lettre_" in download.headers["content-disposition"]
    edited = source["tex"].replace(
        r"\end{document}", "Post-scriptum écrit à la main.\n\\end{document}"
    )
    manual = client.put(f"/api/cvs/{slug}/letter/source", json={"tex": edited}).json()
    assert manual["mode"] == "manual" and manual["compile"]["ok"]
    assert "Post-scriptum" in ats.pdf_text(folder / letter_store.PDF)
    letter = client.get(f"/api/cvs/{slug}/letter").json()["letter"]
    assert client.put(f"/api/cvs/{slug}/letter", json=letter).status_code == 409
    back = client.post(f"/api/cvs/{slug}/letter/visual").json()
    assert back["mode"] == "visual" and "Post-scriptum" not in ats.pdf_text(
        folder / letter_store.PDF
    )


def test_letter_needs_an_offer(client: TestClient, cv: dict[str, Any]) -> None:
    state = client.get("/api/cvs/base/letter").json()
    assert state["available"] is False and state["letter"] is None
    assert client.post("/api/cvs/base/letter/generate", json={}).status_code == 409
    assert client.get(f"/api/cvs/{cv['slug']}/letter").json()["available"] is True


def test_place_date(base_content: CVContent) -> None:
    assert letter_ai.place_date(base_content, date(2026, 10, 1)) == "Lyon, le 1er octobre 2026"
    english = base_content.model_copy(update={"language": "en"})
    assert letter_ai.place_date(english, date(2026, 10, 23)) == "Lyon, 23 October 2026"


def _letter(paragraphs: list[str]) -> LetterContent:
    return LetterContent(
        recipient=["Nordia", "Équipe Data", "Lyon"],
        place_date="Lyon, le 4 novembre 2026",
        subject="Candidature au stage Data Scientist",
        paragraphs=paragraphs,
        signature="Camille Laurent",
    )


def test_letter_layout_follows_its_length() -> None:
    from app.latex.letter import layout

    short = layout(_letter(["Une phrase courte."]))
    long = layout(_letter(["mot " * 400]))
    assert float(short["size"]) == 12 and float(short["leading"]) > 1
    assert float(long["size"]) == 10.5 and float(long["leading"]) == 1


@needs_latex
def test_short_letter_spreads_over_the_page(tmp_path: Path, base_content: CVContent) -> None:
    """Destinataire aligné à droite ; une lettre courte occupe la page, pas son seul haut."""
    import re
    import subprocess

    from app.latex.compile import compile_tex
    from app.latex.letter import render_letter
    from app.models.style import CVStyle
    from app.paths import DEMO_DIR

    style = CVStyle.model_validate_json((DEMO_DIR / "style.json").read_text(encoding="utf-8"))
    letter = _letter(["Je serais heureuse de vous rencontrer pour en parler.", "Merci."])
    tex = tmp_path / "lettre.tex"
    tex.write_text(render_letter(letter, base_content, style), encoding="utf-8")
    result = compile_tex(tex, pdf_name="lettre.pdf")
    assert result.ok and result.pdf and result.pages == 1, result.errors
    xml = subprocess.run(
        ["pdftotext", "-bbox", str(result.pdf), "-"], capture_output=True, text=True
    ).stdout
    box = r'yMin="([\d.]+)" xMax="([\d.]+)"[^>]*>([^<]*)<'
    words = [(w, float(x1), float(y0)) for y0, x1, w in re.findall(box, xml)]
    right_margin = 595.28 - 2.3 / 2.54 * 72
    for line_end in ("Nordia", "Data", "Lyon", "2026"):
        # Le dernier mot de chaque ligne du bloc touche la marge de droite.
        assert any(w == line_end and abs(x1 - right_margin) < 1.5 for w, x1, _ in words), line_end
    # La signature descend dans le bas de la page.
    signature = [y0 for w, _, y0 in words if w == "Laurent"]
    assert signature and signature[-1] > 0.6 * 841.89
