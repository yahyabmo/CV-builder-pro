import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import settings
from app.ai import quota, usage_log
from app.ai.schemas import ImportedCV
from app.models.content import CVContent, ExperienceSection, GridSection
from app.paths import DEMO_DIR
from app.services import cv_import, rules
from app.services.library_import import split_skills
from app.storage import cv_store, library_store
from tests.conftest import needs_latex

DEMO_PDF = DEMO_DIR / "cv-exemple.pdf"


def demo_reading() -> ImportedCV:
    answers = json.loads((DEMO_DIR / "reponses-ia.json").read_text(encoding="utf-8"))
    return ImportedCV.model_validate(answers["ImportedCV"])


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cv_import, "IMPORTS_DIR", tmp_path / "imports")
    monkeypatch.setattr(library_store, "LIBRARY_DIR", tmp_path / "library")
    monkeypatch.setattr(cv_store, "TRASH_DIR", tmp_path / "corbeille")
    monkeypatch.setattr(usage_log, "USAGE_FILE", tmp_path / "usage.json")
    monkeypatch.setattr(quota, "QUOTA_FILE", tmp_path / "quota.json")
    monkeypatch.setattr(rules, "RULES_DIR", tmp_path / "rules")
    file = tmp_path / "settings.json"
    file.write_text(json.dumps({"provider": "demo"}), encoding="utf-8")
    monkeypatch.setattr(settings, "SETTINGS_FILE", file)


def test_a_text_pdf_gives_its_words_and_its_photo() -> None:
    reading = cv_import.read_pdf(DEMO_PDF.read_bytes())
    assert reading.words > 300 and reading.pages == 1 and reading.photo
    assert "CAMILLE LAURENT" in cv_import.text_of(reading.id)


def test_a_scan_or_another_file_is_refused() -> None:
    with pytest.raises(cv_import.UnreadablePdf, match="pas un PDF"):
        cv_import.read_pdf(b"bonjour")
    scan = io.BytesIO()
    Image.new("RGB", (600, 800), "white").save(scan, "PDF")
    with pytest.raises(cv_import.UnreadablePdf, match="scan"):
        cv_import.read_pdf(scan.getvalue())
    assert not list(cv_import.IMPORTS_DIR.iterdir())


def test_the_reading_fills_the_sections_of_the_app(base_content: CVContent) -> None:
    content = cv_import.to_content(demo_reading(), with_photo=True)
    assert content.header.name == base_content.header.name and content.header.photo == "photo.jpg"
    assert (
        content.header.contact_lines[0][0].bold
        and content.header.contact_lines[0][0].text == "Lyon, France"
    )
    imported = {s.id: s for s in content.sections}
    for section in base_content.sections:
        assert imported[section.id].visible
        assert len(imported[section.id].items) == len(section.items)
    assert isinstance(imported["associatif"], ExperienceSection)
    assert imported["associatif"].layout == "compact"
    assert isinstance(imported["soft-skills"], GridSection)
    skills = next(s for s in base_content.sections if s.kind == "skills")
    total = sum(len(split_skills(group.text)) for group in skills.items)
    assert cv_import.counts(content) == {"skills": total, "experiences": 3, "projects": 4}


def test_an_empty_section_is_hidden_and_titles_follow_the_language() -> None:
    reading = demo_reading().model_copy(update={"projects": [], "language": "en"})
    sections = {s.id: s for s in cv_import.to_content(reading, with_photo=False).sections}
    assert not sections["projets"].visible and sections["formation"].title == "EDUCATION"


def test_every_word_must_come_from_the_pdf() -> None:
    reading = cv_import.read_pdf(DEMO_PDF.read_bytes())
    source = cv_import.text_of(reading.id)
    assert cv_import.checks(demo_reading(), source) == []
    invented = demo_reading()
    invented.experience[0].bullets[2] += " Orchestration Kubernetes."
    invented.unplaced = ["Permis B · disponible en février"]
    found = cv_import.checks(invented, source)
    assert [(c.kind, c.where) for c in found] == [
        ("absent", "Expérience 1, puce 3"),
        ("unplaced", "Sans rubrique"),
    ]
    assert "« Orchestration », « Kubernetes »" in found[0].text


def test_blank_cv_has_every_section_hidden(client: TestClient) -> None:
    blank = CVContent.model_validate(client.get("/api/welcome/blank").json())
    assert blank.header.name == "" and not blank.header.photo
    assert blank.sections and not any(s.visible or s.items for s in blank.sections)


def test_dismissing_the_welcome(client: TestClient) -> None:
    assert client.get("/api/welcome").json() == {"show": True, "setup": True}
    assert client.post("/api/welcome/dismiss").json() == {"show": False, "setup": False}
    assert client.get("/api/welcome").json() == {"show": False, "setup": False}


def test_demo_mode_reads_only_the_sample_pdf(client: TestClient) -> None:
    scan = io.BytesIO()
    Image.new("RGB", (200, 200)).save(scan, "PDF")
    refused = client.post("/api/welcome/import", files={"file": ("cv.pdf", scan.getvalue())})
    assert refused.status_code == 422 and "mode démo" in refused.json()["detail"]


@needs_latex
def test_import_review_and_apply(client: TestClient) -> None:
    sample = client.get("/api/welcome/demo-pdf").content
    reading = client.post("/api/welcome/import", files={"file": ("cv.pdf", sample)}).json()
    assert reading["photo"] and reading["words"] > 300
    result = client.post(f"/api/welcome/import/{reading['id']}/read").json()
    assert result["checks"] == [] and result["counts"]["projects"] == 4
    assert client.get(f"/api/welcome/import/{reading['id']}").json() == result

    preview = client.post(
        f"/api/welcome/import/{reading['id']}/preview", json={"content": result["content"]}
    )
    assert preview.json()["ok"] and preview.json()["pages"] == 1

    content = result["content"]
    content["header"]["headline"] = "Data Science & IA (relu)"
    out = client.post(
        "/api/welcome/apply", json={"content": content, "import_id": reading["id"]}
    ).json()
    assert out["compile"]["ok"] and out["added"]["projects"] == 4 and out["added"]["skills"] > 15
    base = client.get("/api/cvs/base").json()
    assert base["content"]["header"]["headline"] == "Data Science & IA (relu)"
    assert base["content"]["header"]["photo"] == "photo.jpg"
    assert client.get("/api/welcome").json() == {"show": False, "setup": False}
    # L'ancienne version classique est gardée dans la corbeille.
    assert [p.name.startswith("base-") for p in cv_store.TRASH_DIR.iterdir()] == [True]


@needs_latex
def test_a_hand_written_cv_has_no_photo(client: TestClient, base_content: CVContent) -> None:
    out = client.post("/api/welcome/apply", json={"content": base_content.model_dump()}).json()
    assert out["compile"]["ok"]
    assert not client.get("/api/cvs/base").json()["content"]["header"].get("photo")


@needs_latex
def test_import_keeps_the_style_of_the_pdf(client: TestClient) -> None:
    """Le style repéré : listé, montré dans l'aperçu, appliqué à la validation, clé par clé."""
    sample = client.get("/api/welcome/demo-pdf").content
    reading = client.post("/api/welcome/import", files={"file": ("cv.pdf", sample)}).json()
    result = client.post(f"/api/welcome/import/{reading['id']}/read").json()
    findings = client.get(f"/api/welcome/import/{reading['id']}/style").json()["findings"]
    keys = {f["key"] for f in findings}
    assert {"font", "colors", "photo", "columns", "titles", "order"} <= keys
    font = next(f for f in findings if f["key"] == "font")
    assert font["badge"] == "identique" and "PT Serif" in font["done"]

    preview = client.post(
        f"/api/welcome/import/{reading['id']}/preview",
        json={"content": result["content"], "keep": sorted(keys)},
    )
    assert preview.json()["ok"]
    out = client.post(
        "/api/welcome/apply",
        json={"content": result["content"], "import_id": reading["id"], "keep": ["font", "colors"]},
    ).json()
    assert out["compile"]["ok"]
    style = client.get("/api/cvs/base").json()["style"]
    assert style["fonts"]["main"] == "PTSerif" and style["palette"]["primary"] in (
        "792D1F",
        "7A2E1F",
    )
    # Les colonnes n'étaient pas cochées : celles de l'appli restent.
    assert style["columns"]["left_width"] == 0.41
