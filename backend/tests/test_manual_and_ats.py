from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models.content import CVContent
from app.services import ats
from app.storage import cv_store, library_store
from tests.conftest import needs_latex


@pytest.fixture
def cv(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Un CV d'essai, copie compilée de la version classique."""
    monkeypatch.setattr(library_store, "LIBRARY_DIR", tmp_path / "library")
    return client.post("/api/cvs", json={"name": "Essai LaTeX"}).json()["slug"]


@needs_latex
def test_manual_mode_round_trip(client: TestClient, cv: str) -> None:
    source = client.get(f"/api/cvs/{cv}/source").json()
    assert source["mode"] == "visual" and source["tex"].startswith("% Généré par CV Builder")

    # Le même code, renvoyé tel quel : rien ne change.
    same = client.put(f"/api/cvs/{cv}/source", json={"tex": source["tex"]}).json()
    assert same["mode"] == "visual"

    # Modifié à la main : mode manuel, le .tex devient la source.
    edited = source["tex"].replace("Data Science", "Data Science (édité à la main)", 1)
    manual = client.put(f"/api/cvs/{cv}/source", json={"tex": edited}).json()
    assert manual["mode"] == "manual" and manual["compile"]["ok"]
    assert "édité à la main" in ats.pdf_text(cv_store.folder(cv) / cv_store.PDF)
    assert client.get(f"/api/cvs/{cv}").json()["meta"]["mode"] == "manual"
    assert client.get(f"/api/cvs/{cv}/source").json()["tex"] == edited

    # Le contenu, le style et la photo sont verrouillés.
    detail = client.get(f"/api/cvs/{cv}").json()
    assert client.put(f"/api/cvs/{cv}/content", json=detail["content"]).status_code == 409
    assert client.put(f"/api/cvs/{cv}/style", json=detail["style"]).status_code == 409
    photo = client.post(f"/api/cvs/{cv}/photo", files={"file": ("p.jpg", b"x", "image/jpeg")})
    assert photo.status_code == 409

    # Une copie garde le code LaTeX et le mode manuel.
    copy = client.post("/api/cvs", json={"name": "Copie", "source": cv}).json()
    assert copy["meta"]["mode"] == "manual"
    assert client.get(f"/api/cvs/{copy['slug']}/source").json()["tex"] == edited

    # Retour au mode visuel : le .tex est refait depuis le contenu.
    back = client.post(f"/api/cvs/{cv}/visual").json()
    assert back["mode"] == "visual" and back["compile"]["ok"]
    assert "édité à la main" not in ats.pdf_text(cv_store.folder(cv) / cv_store.PDF)


@needs_latex
def test_manual_errors_point_to_the_line(client: TestClient, cv: str) -> None:
    tex = client.get(f"/api/cvs/{cv}/source").json()["tex"]
    lines = tex.split("\n")
    at = next(i for i, line in enumerate(lines) if line.startswith(r"\begin{document}")) + 2
    lines.insert(at, r"\commandeinconnue")
    result = client.put(f"/api/cvs/{cv}/source", json={"tex": "\n".join(lines)}).json()
    assert not result["compile"]["ok"]
    [error] = result["compile"]["errors"]
    assert error["line"] == at + 1 and "inconnue" in error["message"].lower()


@needs_latex
def test_base_stays_visual(client: TestClient) -> None:
    tex = client.get("/api/cvs/base/source").json()["tex"]
    refused = client.put("/api/cvs/base/source", json={"tex": tex + "\n% retouche"})
    assert refused.status_code == 409 and "Duplique" in refused.json()["detail"]


@needs_latex
def test_ats_report(client: TestClient, cv: str, base_content: CVContent) -> None:
    report = client.get(f"/api/cvs/{cv}/ats").json()
    status = {c["id"]: c["status"] for c in report["checks"]}
    assert {
        k: status[k] for k in ("text", "pages", "fonts", "ligatures", "chars", "words", "contact")
    } == {
        "text": "ok",
        "pages": "ok",
        "fonts": "ok",
        "ligatures": "ok",
        "chars": "ok",
        "words": "ok",
        "contact": "ok",
    }
    assert report["words"]["missing"] == [] and report["words"]["total"] > 250
    # Deux colonnes : FORMATION se lit entremêlée avec EXPÉRIENCE.
    assert (
        status["order"] == "warn"
        and "FORMATION" in next(c for c in report["checks"] if c["id"] == "order")["detail"]
    )
    assert "Diplôme" in report["text"]

    terms = client.post(
        f"/api/cvs/{cv}/ats/terms", json={"terms": ["Python", "tests automatisés", "Kubernetes"]}
    ).json()
    assert terms == {"present": ["Python", "tests automatisés"], "absent": ["Kubernetes"]}
    assert client.get("/api/cvs/inconnu/ats").status_code == 404


def test_reading_order_and_tokens(base_content: CVContent) -> None:
    # Apostrophe typographique, gras et ligature n'empêchent pas de retrouver les mots.
    assert ats._tokens("L’IA **générative** : C++ et ﬁchiers") == [
        "ia",
        "générative",
        "et",
        "fichiers",
    ]
    text = "FORMATION\nEXPÉRIENCE PROFESSIONNELLE\nDiplôme d'ingénieur\nStage Data Scientist\n"
    good, mixed = ats.reading_order(base_content, text)
    assert "FORMATION" in mixed and "EXPÉRIENCE PROFESSIONNELLE" in good
