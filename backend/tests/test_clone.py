"""Le clonage d'un CV importé : la forme de son PDF recopiée en LaTeX, mot à mot, puis gardée."""

import shutil
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.models.content import CVContent
from app.paths import DEMO_DIR
from app.services import cv_import
from app.services.clone import build, fill, likeness, reading, report, structure
from app.services.clone import fields as F
from app.services.clone.model import CloneLayout
from app.services.clone.plan import AnchoredLayout
from app.storage import cv_store
from tests.conftest import needs_latex
from tests.test_import import isolated  # noqa: F401

SAMPLE = DEMO_DIR / "cv-exemple.pdf"


def _demo() -> CVContent:
    content = CVContent.model_validate_json((DEMO_DIR / "content.json").read_text())
    content.header.photo = "photo.jpg"
    return content


def test_page_is_read_word_by_word_with_its_shapes_and_photo() -> None:
    page = reading.read(SAMPLE)[0]
    texts = [line.text for line in page.lines]
    assert "CAMILLE LAURENT" in texts and "FORMATION" in texts
    name = next(line for line in page.lines if line.text == "CAMILLE LAURENT")
    first = name.words[0]
    # La police, la graisse, la couleur et la ligne de base exactes du PDF.
    assert (first.font, first.bold, first.color) == ("PTSerif", True, "7A2E1F")
    assert abs(first.baseline - 55.96) < 0.05
    # Une date alignée à droite est un segment à part de son intitulé.
    assert any(line.text == "Juin 2026 – Août 2026" for line in page.lines)
    # Le fond de la colonne de gauche, les filets, la photo et les liens.
    assert any(s.fill and s.h > 500 for s in page.shapes)
    assert sum(1 for s in page.shapes if s.kind == "line") >= 6
    assert page.pictures and page.pictures[0].box[0] > 300 and page.pictures[0].data
    assert any("github.com" in url for *_, url in page.links)


def test_family_names() -> None:
    assert reading.family_name("ABCDEF+Poppins-BoldItalic") == "Poppins"
    assert reading.family_name("ArialMT") == "Arial"


def test_structure_finds_columns_titles_and_sections() -> None:
    found = structure.analyse(reading.read(SAMPLE))
    assert len(found.lanes[0]) == 2
    titles = [b.title_text for b in found.blocks]
    assert titles[:3] == ["EXPÉRIENCE PROFESSIONNELLE", "FORMATION", "COMPÉTENCES"]
    assert "CENTRES D’INTÉRÊT" in titles
    # Ce qui précède tout titre est l'en-tête ; le texte pour l'IA est rangé par rubrique.
    assert any(line.text == "CAMILLE LAURENT" for line in found.header)
    text = structure.text(found)
    assert text.startswith("[En-tête]\nCAMILLE LAURENT")
    assert "## PROJETS\nTrafficLens" in text


def test_every_field_is_found_on_the_page() -> None:
    content = _demo()
    found = structure.analyse(reading.read(SAMPLE), [s.title for s in content.sections])
    hits = F.Locator(found, content).locate()
    assert {p for p, _, _ in F.paths(content)} == set(hits)
    assert F.uncovered(found, hits) == []


def test_the_page_fixes_what_the_ai_got_wrong() -> None:
    content = _demo()
    experience = next(s for s in content.sections if s.kind == "experience")
    bullet = experience.items[0].bullets[0]
    cut = bullet.index(" ", len(bullet) // 2)
    # Une puce coupée en deux, une rubrique oubliée : les fautes vues sur un vrai CV.
    experience.items[0].bullets[0:1] = [bullet[:cut], bullet[cut + 1 :]]
    content.sections = [s for s in content.sections if s.kind != "languages"]
    fixed, done = fill.complete(content, reading.read(SAMPLE))
    experience = next(s for s in fixed.sections if s.kind == "experience")
    assert experience.items[0].bullets[0] == bullet and done.merged == 1
    # La rubrique oubliée revient sous son titre, ligne à ligne, gras compris.
    languages = next(s for s in fixed.sections if s.title == "LANGUES")
    assert languages.items == [
        "**Français** : langue maternelle",
        "**Anglais** : courant (C1, TOEIC 945)",
        "**Espagnol** : intermédiaire (B1)",
        "**Italien** : notions",
    ]
    assert done.coverage == 1.0 and done.misplaced == 0 and done.left == []


def test_bold_words_and_links_come_back_from_the_page() -> None:
    content = _demo()
    for item in content.header.contact_lines[1]:
        item.url = None
    fixed, done = fill.complete(content, reading.read(SAMPLE))
    assert any(item.url and "github.com" in item.url for item in fixed.header.contact_lines[1])
    assert done.links >= 1


def test_marks_are_put_where_the_page_is_bold() -> None:
    words = [
        reading.Word("Budget", 0, 10, 0, 10, 8, "A", "A", 10, "000000", False, False),
        reading.Word("de", 12, 20, 0, 10, 8, "A", "A", 10, "000000", False, False),
        reading.Word("600", 22, 40, 0, 10, 8, "A", "A-Bold", 10, "000000", True, False),
        reading.Word("k€", 42, 55, 0, 10, 8, "A", "A-Bold", 10, "000000", True, False),
        reading.Word("tenu.", 57, 80, 0, 10, 8, "A", "A", 10, "000000", False, False),
    ]
    marks = F.marks_for(words)
    assert marks == [("**", "600 k€")]
    assert F.apply_marks("Budget de 600 k€ tenu.", marks) == "Budget de **600 k€** tenu."


@needs_latex
def test_the_sample_is_cloned_word_for_word(tmp_path: Path) -> None:
    shutil.copy(DEMO_DIR / "imgcv.jpg", tmp_path / "photo.jpg")
    result = build.clone_into(tmp_path, SAMPLE, _demo(), online=False)
    assert result.ok and result.pages == 1
    measured = likeness.measure(SAMPLE, tmp_path / "cv.pdf")
    assert measured.score >= 98, measured
    diff = report.compare(reading.read(SAMPLE), tmp_path / "cv.pdf")
    # Chaque ligne à sa place au point près, sans style perdu ni texte qui se chevauche.
    assert diff.in_place == 1.0 and diff.max_shift <= 1.0, diff.moved[:5]
    assert not diff.missing and not diff.restyled and not diff.overlaps and not diff.overflow
    tex = (tmp_path / "main.tex").read_text()
    # Les repères du clic sur l'aperçu sont là.
    assert "%@ item experience 0" in tex and "%@ bullet experience 0 1" in tex
    assert isinstance(cv_store.load_clone(tmp_path), AnchoredLayout)


@needs_latex
def test_an_edited_clone_reflows_without_overlap(tmp_path: Path) -> None:
    from app.latex.compile import compile_tex

    content = _demo()
    content.header.photo = ""
    assert build.clone_into(tmp_path, SAMPLE, content, online=False).ok
    layout = cv_store.load_clone(tmp_path)
    experience = next(s for s in content.sections if s.kind == "experience")
    # Une puce rallongée, une puce ajoutée, une entrée et une compétence retirées.
    experience.items[0].bullets[1] += " Et une phrase de plus, assez longue pour couler."
    experience.items[0].bullets.append("Une puce toute neuve, ajoutée après le clonage.")
    experience.items.pop(1)
    skills = next(s for s in content.sections if s.kind == "skills")
    skills.items.pop(1)
    result = compile_tex(build.write(tmp_path, layout, content))
    assert result.ok and result.overflow_pt == 0
    diff = report.compare(reading.read(SAMPLE), tmp_path / "cv.pdf")
    assert not diff.overlaps, diff.overlaps[:5]
    assert not diff.overflow
    clone = reading.read(tmp_path / "cv.pdf")[0]
    texts = " ".join(line.text for line in clone.lines)
    assert "Une puce toute neuve" in texts and "Data & IA" not in texts
    assert "Conseil en librairie" not in texts
    # L'en-tête, au-dessus de tout changement, reste à sa place exacte.
    head = next(line for line in clone.lines if line.text == "CAMILLE LAURENT")
    assert abs(head.baseline - 55.96) < 0.05


@needs_latex
def test_a_clone_that_grows_says_it_overflows(tmp_path: Path) -> None:
    from app.latex.compile import compile_tex

    content = _demo()
    content.header.photo = ""
    assert build.clone_into(tmp_path, SAMPLE, content, online=False).ok
    layout = cv_store.load_clone(tmp_path)
    projects = next(s for s in content.sections if s.kind == "projects")
    for n in range(3):
        projects.items.append(projects.items[0].model_copy(update={"title": f"Projet {n}"}))
    result = compile_tex(build.write(tmp_path, layout, content))
    assert result.ok and result.overflow_pt > 0
    diff = report.compare(reading.read(SAMPLE), tmp_path / "cv.pdf")
    assert not diff.overlaps, diff.overlaps[:5]
    assert "Projet 2" in " ".join(line.text for line in reading.read(tmp_path / "cv.pdf")[0].lines)


@needs_latex
def test_import_with_clone_keeps_the_form(client: TestClient) -> None:
    sample = client.get("/api/welcome/demo-pdf").content
    reading_out = client.post("/api/welcome/import", files={"file": ("cv.pdf", sample)}).json()
    read = client.post(f"/api/welcome/import/{reading_out['id']}/read").json()
    content = read["content"]
    assert not [c for c in read["checks"] if c["kind"] == "unplaced"]
    out = client.post(f"/api/welcome/import/{reading_out['id']}/clone", json={"content": content})
    clone = out.json()
    assert clone["available"] and clone["ok"] and clone["likeness"] >= 95, clone
    assert any("place exacte" in k for k in clone["kept"]), clone["kept"]
    assert client.get(f"/api/welcome/import/{reading_out['id']}/clone.pdf").content[:4] == b"%PDF"

    applied = client.post(
        "/api/welcome/apply",
        json={"content": content, "import_id": reading_out["id"], "clone": True},
    ).json()
    assert applied["compile"]["ok"]
    base = cv_store.folder("base")
    assert (base / cv_store.CLONE).is_file()
    assert "CV cloné" in client.get("/api/cvs/base/source").json()["tex"]
    # Un CV ciblé fait à partir de lui garde sa forme.
    slug = client.post("/api/cvs", json={"name": "Offre"}).json()["slug"]
    assert (cv_store.folder(slug) / cv_store.CLONE).is_file()

    # Revalidé au style de l'appli : le clone part.
    client.post("/api/welcome/apply", json={"content": content, "import_id": reading_out["id"]})
    assert not (base / cv_store.CLONE).exists()
    assert "CV cloné" not in client.get("/api/cvs/base/source").json()["tex"]


@needs_latex
def test_a_two_page_pdf_is_cloned_page_by_page(client: TestClient, tmp_path: Path) -> None:
    sample = client.get("/api/welcome/demo-pdf").content
    reading_out = client.post("/api/welcome/import", files={"file": ("cv.pdf", sample)}).json()
    content = client.post(f"/api/welcome/import/{reading_out['id']}/read").json()["content"]
    # Un PDF de deux pages : la même page deux fois.
    two = tmp_path / "deux.pdf"
    subprocess.run(["pdfunite", str(SAMPLE), str(SAMPLE), str(two)], check=True)
    shutil.copy(two, cv_import.folder(reading_out["id"]) / cv_import.SOURCE)
    clone = client.post(
        f"/api/welcome/import/{reading_out['id']}/clone", json={"content": content}
    ).json()
    assert clone["available"] and clone["ok"], clone
    assert "2 pages, chacune à sa forme" in clone["kept"]
    pdf = cv_import.folder(reading_out["id"]) / "clone" / "cv.pdf"
    assert likeness.pages(pdf) == 2


def test_a_first_version_clone_still_renders(tmp_path: Path) -> None:
    """Les CV clonés avant la mise en page ancrée gardent leur forme."""
    content = _demo()
    cv_store.save(tmp_path, content, cv_store.load(DEMO_DIR)[1])
    (tmp_path / cv_store.CLONE).write_text(CloneLayout().model_dump_json())
    assert isinstance(cv_store.load_clone(tmp_path), CloneLayout)
    tex = cv_store.generated(tmp_path)
    assert "CV cloné" in tex and "\\cvline" not in tex
