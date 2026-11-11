"""Le clonage d'un CV importé : la forme de son PDF recopiée en LaTeX, puis gardée."""

import shutil
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.models.content import CVContent
from app.paths import DEMO_DIR
from app.services import cv_import
from app.services.clone import build, likeness
from app.services.clone import page as pages
from app.services.clone.layout import infer, key
from app.storage import cv_store
from tests.conftest import needs_latex
from tests.test_import import isolated  # noqa: F401

SAMPLE = DEMO_DIR / "cv-exemple.pdf"


def _demo() -> CVContent:
    content = CVContent.model_validate_json((DEMO_DIR / "content.json").read_text())
    content.header.photo = "photo.jpg"
    return content


def test_page_is_read_with_its_shapes_and_photo() -> None:
    page = pages.read(SAMPLE)
    texts = {key(r.text) for r in page.runs}
    assert "camillelaurent" in texts and "formation" in texts
    # Le fond de la colonne de gauche et les filets sous les titres.
    assert any(s.fill and s.h > 500 for s in page.shapes)
    assert sum(1 for s in page.shapes if s.kind == "line" or s.h < 2) >= 6
    assert page.pictures and page.pictures[0].box[0] > 300


def test_family_names_and_merged_pieces() -> None:
    assert pages.family_name("ABCDEF+Poppins-BoldItalic") == "Poppins"
    assert pages.family_name("ArialMT") == "Arial"
    a = pages.Run("Inès ", 10, 10, 20, 12, "Ubuntu", "Ubuntu", 21.7, "000000", True, False)
    b = pages.Run("Moreau", 30.5, 9, 40, 14, "Ubuntu", "Ubuntu", 17.3, "000000", True, False)
    merged = pages.merge([b, a])
    assert [r.text for r in merged] == ["Inès Moreau"]


def test_layout_finds_columns_titles_and_rules() -> None:
    layout = infer(pages.read(SAMPLE), _demo(), online=False)
    columns = [f for f in layout.frames if any(b.kind == "section" for b in f.blocks)]
    assert len(columns) == 2 and columns[0].x < columns[1].x
    assert {look.deco.kind for look in layout.looks} == {"rule"}
    # Le fond de colonne reste une forme fixe ; les filets suivent leurs titres.
    assert any(p.fill and (p.y1 - p.y0) > 500 for p in layout.paints)
    # Seul le filet sous l'en-tête reste fixe (il n'appartient à aucun titre).
    assert [round(p.x1 - p.x0) for p in layout.paints if p.kind == "line"] == [538]
    assert layout.fonts["PTSerif"] == ("PTSerif", "identique")


@needs_latex
def test_the_sample_is_cloned_closely(tmp_path: Path) -> None:
    shutil.copy(DEMO_DIR / "imgcv.jpg", tmp_path / "photo.jpg")
    result = build.clone_into(tmp_path, SAMPLE, _demo(), online=False)
    assert result.ok and result.pages == 1
    measured = likeness.measure(SAMPLE, tmp_path / "cv.pdf")
    assert measured.score >= 85, measured
    tex = (tmp_path / "main.tex").read_text()
    # Les repères du clic sur l'aperçu sont là, et rien du contenu ne manque.
    assert "%@ item experience 0" in tex and "%@ bullet experience 0 1" in tex
    words = {key(w.text) for w in likeness.words(tmp_path / "cv.pdf")}
    assert {"trafficlens", "escalade", "tresorerie"} <= words


@needs_latex
def test_import_with_clone_keeps_the_form(client: TestClient) -> None:
    sample = client.get("/api/welcome/demo-pdf").content
    reading = client.post("/api/welcome/import", files={"file": ("cv.pdf", sample)}).json()
    content = client.post(f"/api/welcome/import/{reading['id']}/read").json()["content"]
    out = client.post(f"/api/welcome/import/{reading['id']}/clone", json={"content": content})
    clone = out.json()
    assert clone["available"] and clone["ok"] and clone["likeness"] >= 80, clone
    assert any("Police" in k for k in clone["kept"])
    assert client.get(f"/api/welcome/import/{reading['id']}/clone.pdf").content[:4] == b"%PDF"

    applied = client.post(
        "/api/welcome/apply",
        json={"content": content, "import_id": reading["id"], "clone": True},
    ).json()
    assert applied["compile"]["ok"]
    base = cv_store.folder("base")
    assert (base / cv_store.CLONE).is_file()
    assert "CV cloné" in client.get("/api/cvs/base/source").json()["tex"]
    # Un CV ciblé fait à partir de lui garde sa forme.
    slug = client.post("/api/cvs", json={"name": "Offre"}).json()["slug"]
    assert (cv_store.folder(slug) / cv_store.CLONE).is_file()

    # Revalidé au style de l'appli : le clone part.
    client.post("/api/welcome/apply", json={"content": content, "import_id": reading["id"]})
    assert not (base / cv_store.CLONE).exists()
    assert "CV cloné" not in client.get("/api/cvs/base/source").json()["tex"]


def test_a_two_page_pdf_is_not_cloned_yet(client: TestClient, tmp_path: Path) -> None:
    sample = client.get("/api/welcome/demo-pdf").content
    reading = client.post("/api/welcome/import", files={"file": ("cv.pdf", sample)}).json()
    content = client.post(f"/api/welcome/import/{reading['id']}/read").json()["content"]
    # Un PDF de deux pages : la même page deux fois.
    two = tmp_path / "deux.pdf"
    subprocess.run(["pdfunite", str(SAMPLE), str(SAMPLE), str(two)], check=True)
    shutil.copy(two, cv_import.folder(reading["id"]) / cv_import.SOURCE)
    clone = client.post(
        f"/api/welcome/import/{reading['id']}/clone", json={"content": content}
    ).json()
    assert clone["available"] is False and "2 pages" in clone["reason"]
