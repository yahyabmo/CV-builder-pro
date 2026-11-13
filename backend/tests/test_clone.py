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
    # Les polices cm-super d'un CV fait en LaTeX : Latin Modern, pas une autre.
    assert reading.family_name("ABCDEF+SFRM1000") == "LMRoman"
    assert reading.family_name("SFXC1000") == "LMRomanCaps"
    assert reading.family_name("SFSS1200") == "LMSans"


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
def test_a_click_on_a_clone_frames_its_entry_inside_its_column(tmp_path: Path) -> None:
    from app.services import locate

    content = _demo()
    content.header.photo = ""
    assert build.clone_into(tmp_path, SAMPLE, content, online=False).ok
    placed = locate.positions(tmp_path)
    assert placed, "LaTeX écrit la place de chaque unité"
    layout = cv_store.load_clone(tmp_path)
    bullet = next(u for u in layout.units if u.mark == "bullet experience 0 1")
    where = next(p for p in placed if p.unit == str(bullet.id))
    found = locate.locate(tmp_path, (where.x0 + where.x1) / 2, (where.top + where.bottom) / 2)
    assert found is not None and (found.section, found.item, found.bullet) == ("experience", 0, 1)
    # Le cadre de l'entrée : dans la colonne de droite, pas sur toute la page.
    box = found.box
    assert box is not None and box.x > 200 and box.w < 0.6 * layout.pages[0].width, box
    assert box.x <= where.x0 and where.x1 <= box.x + box.w


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
def test_a_field_empty_when_cloned_shows_once_filled(tmp_path: Path) -> None:
    """La mention vide d'une expérience n'avait pas de place sur la page : remplie après le
    clonage, elle s'écrit sur la ligne de son entrée, sans rien chevaucher."""
    from app.latex.compile import compile_tex

    content = _demo()
    content.header.photo = ""
    assert build.clone_into(tmp_path, SAMPLE, content, online=False).ok
    layout = cv_store.load_clone(tmp_path)
    assert layout.snapshot and "experience.1.tag" not in layout.snapshot
    experience = next(s for s in content.sections if s.id == "experience")
    experience.items[1].tag = "Mention ajoutée"
    result = compile_tex(build.write(tmp_path, layout, content))
    assert result.ok
    texts = " ".join(line.text for line in reading.read(tmp_path / "cv.pdf")[0].lines)
    assert "Mention ajoutée" in texts
    diff = report.compare(reading.read(SAMPLE), tmp_path / "cv.pdf")
    assert not diff.overlaps, diff.overlaps[:5]


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
    # Le contrôle est parfait : le clone est proposé par défaut, sans avertissement.
    assert clone["recommended"] is True and clone["warning"] is None
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

    # La forme de l'appli, puis retour au clone : il reste gardé.
    out = client.put("/api/cvs/base/shape", json={"shape": "app"}).json()
    assert out["ok"] and (base / cv_store.CLONE).is_file()
    assert "CV cloné" not in client.get("/api/cvs/base/source").json()["tex"]
    assert client.get("/api/cvs/base").json()["shape"] == "app"
    assert client.put("/api/cvs/base/shape", json={"shape": "clone"}).json()["ok"]
    assert "CV cloné" in client.get("/api/cvs/base/source").json()["tex"]

    # Validé dans notre forme : le clone est gardé à côté, pour plus tard.
    client.post(
        "/api/welcome/apply",
        json={
            "content": content,
            "import_id": reading_out["id"],
            "clone": True,
            "clone_active": False,
        },
    )
    assert (base / cv_store.CLONE).is_file()
    assert "CV cloné" not in client.get("/api/cvs/base/source").json()["tex"]

    # Revalidé au style de l'appli, sans clone : le clone part.
    client.post("/api/welcome/apply", json={"content": content, "import_id": reading_out["id"]})
    assert not (base / cv_store.CLONE).exists()
    assert "CV cloné" not in client.get("/api/cvs/base/source").json()["tex"]
    assert client.put("/api/cvs/base/shape", json={"shape": "clone"}).status_code == 409


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


def _line(text: str, x0: float, top: float, width: float, size: float = 9.0) -> reading.Line:
    words, x = [], x0
    step = width / max(len(text.split()), 1)
    for part in text.split():
        words.append(
            reading.Word(
                part,
                x,
                x + step - 2,
                top,
                top + size,
                top + 0.8 * size,
                "A",
                "A",
                size,
                "000000",
                False,
                False,
            )  # fmt: skip
        )
        x += step
    return reading.Line(words)


def test_columns_are_found_under_a_full_width_header_and_footer() -> None:
    """Un en-tête et des publications sur toute la largeur traversent le couloir : les
    colonnes existent quand même, là où elles sont côte à côte."""
    lines = [_line("Prénom Nom en très grand titre centré", 40, 30, 500)]
    lines += [_line("Ville | Téléphone : 06 | Email : adresse", 40, 50, 500)]
    lines += [_line("LinkedIn : profil | GitHub : compte en ligne", 40, 62, 500)]
    for n in range(14):
        lines.append(_line(f"Gauche ligne {n} avec des mots", 40, 90 + 14 * n, 150))
        lines.append(
            _line(f"Droite ligne {n} avec bien plus de mots encore", 230, 90 + 14 * n, 320)
        )
    lines += [
        _line(f"Publication {n} sur toute la largeur de la page", 40, 310 + 12 * n, 500)
        for n in range(3)
    ]
    page = reading.Page(1, 595, 842, lines)
    lanes = structure.find_lanes(page)
    assert len(lanes) == 2 and 190 < lanes[0][1] < 230, lanes


def test_scan_bullets_and_icons_read_as_letters_are_recognised() -> None:
    from app.services.clone import scan

    # Les mesures d'un vrai scan : une puce de 3 pt suivie d'un blanc deux fois plus large.
    bullet = [
        ("e", 275, 100, 2.9, 2.9),
        ("Conception", 284.6, 98, 40, 8),
        ("des", 328, 98, 12, 8),
        ("pièces", 343.4, 98, 22, 8),
    ]
    icon = [("GC", 30, 96, 15, 15), ("06.00.00.00.00", 56, 100, 50, 8)]
    word = [("R", 30, 98, 6, 8), ("Studio", 40, 98, 25, 8), ("(Statistiques)", 69, 98, 45, 8)]
    assert scan._glyph(bullet, 0) == "marker"
    assert scan._glyph(icon, 0) == "icon"
    assert scan._glyph(word, 0) is None


def _styled(text: str, x0: float, top: float, width: float, size: float, bold: bool, color: str):
    line = _line(text, x0, top, width, size)
    for w in line.words:
        w.bold, w.color = bold, color
    return line


def test_a_lone_section_name_in_the_side_column_is_a_title() -> None:
    """Un scan : « À PROPOS » d'une autre couleur que les titres de droite, dans une colonne
    dont la lecture met du gras au hasard : c'est un titre quand même ; les coordonnées
    au-dessus vont dans l'en-tête, pas dans une rubrique de droite."""
    green, grey = "2E7D5B", "333333"
    lines = []
    y = 90.0
    for title in ("COMPÉTENCES", "EXPÉRIENCE", "FORMATION", "LANGUES"):
        lines.append(_styled(title, 220, y, 80, 11, True, green))
        y += 18
        for n in range(4):
            lines.append(
                _styled(
                    f"• Ligne {n} de la rubrique {title.lower()}", 222, y, 300, 9.5, False, grey
                )
            )
            y += 14
        y += 10
    lines.append(_styled("Adresse : 69000 Lyon", 15, 100, 115, 11, False, grey))
    lines.append(_styled("Email : prenom@example.com", 15, 118, 130, 11, False, grey))
    lines.append(_styled("A PROPOS", 15, 160, 48, 11, True, "1F4E79"))
    for n in range(12):
        lines.append(
            _styled(
                f"Phrase {n} du profil, assez longue", 15, 178 + 14 * n, 160, 11, n % 3 == 0, grey
            )
        )
    page = reading.Page(1, 612, 792, sorted(lines, key=lambda line: line.top))
    found = structure.analyse([page])
    assert "A PROPOS" in [b.title_text for b in found.blocks]
    header = " ".join(line.text for line in found.header)
    assert "Adresse" in header and "Email" in header
    right = next(b for b in found.blocks if b.title_text == "COMPÉTENCES")
    assert all("Phrase" not in line.text for line in right.lines)


def test_a_bullet_list_of_skills_gives_one_group_per_bullet() -> None:
    """L'IA a écrit sept puces dans un seul groupe nommé comme la rubrique, et un libellé de
    coordonnée est resté sous la liste : une compétence par puce, le libellé dans l'en-tête."""
    from app.models.content import SkillGroup, SkillsSection

    skills = ["Accueil des clients", "Mise en rayon", "Tenue de caisse", "Inventaire"]
    lines = [_styled("COMPÉTENCES", 40, 90, 90, 11, True, "2E7D5B")]
    lines += [
        _styled(f"• {text}", 42, 110 + 14 * n, 140, 9.5, False, "333333")
        for n, text in enumerate(skills)
    ]
    lines.append(_styled("Permis :", 42, 170, 40, 9.5, False, "333333"))
    page = reading.Page(1, 595, 842, lines)
    content = CVContent.model_validate_json((DEMO_DIR / "content.json").read_text())
    for section in content.sections:
        section.items, section.visible = [], False
    section = next(s for s in content.sections if s.kind == "skills")
    section.title, section.visible = "COMPÉTENCES", True
    section.items = [SkillGroup(label="COMPÉTENCES", text=", ".join(skills))]
    fixed, done = fill.complete(content, [page])
    out = next(s for s in fixed.sections if s.kind == "skills")
    assert isinstance(out, SkillsSection)
    assert [(g.label, g.text) for g in out.items] == [("", text) for text in skills]
    assert done.split == len(skills) - 1
    assert any(
        "Permis" in (c.text + (c.label or "")) for line in fixed.header.contact_lines for c in line
    )


def test_two_sections_with_the_same_title_become_one() -> None:
    from app.models.content import ExperienceItem, ExperienceSection

    lines = [_styled("EXPÉRIENCE", 40, 90, 90, 11, True, "2E7D5B")]
    lines.append(_styled("Animateur de centre de loisirs", 40, 110, 200, 10, True, "333333"))
    lines.append(
        _styled("• Encadrement d'un groupe de douze enfants", 42, 124, 260, 9.5, False, "333333")
    )
    lines.append(_styled("Vendeur en boulangerie", 40, 145, 220, 10, True, "333333"))
    lines.append(_styled("• Conseil et vente au comptoir", 42, 159, 240, 9.5, False, "333333"))
    page = reading.Page(1, 595, 842, lines)
    content = CVContent.model_validate_json((DEMO_DIR / "content.json").read_text())
    for section in content.sections:
        section.items, section.visible = [], False
    work = [s for s in content.sections if isinstance(s, ExperienceSection)]
    work[0].title, work[1].title = "EXPÉRIENCE", "EXPÉRIENCE"
    work[0].items = [
        ExperienceItem(
            title="Vendeur en boulangerie",
            place="",
            dates="",
            bullets=["Conseil et vente au comptoir"],
        )
    ]
    work[1].items = [
        ExperienceItem(
            title="Animateur de centre de loisirs",
            place="",
            dates="",
            bullets=["Encadrement d'un groupe de douze enfants"],
        )
    ]
    work[0].visible = work[1].visible = True
    fixed, _ = fill.complete(content, [page])
    shown = [s for s in fixed.sections if s.visible and s.kind == "experience"]
    assert len(shown) == 1
    assert [it.title for it in shown[0].items] == [
        "Animateur de centre de loisirs",
        "Vendeur en boulangerie",
    ]


def test_one_column_text_does_not_stretch_to_fill_the_page() -> None:
    from app.latex.render import render
    from app.models.style import CVStyle

    def entry_gap(style: CVStyle) -> str:
        tex = render(_demo(), style)
        return tex.split("\\newcommand{\\entre}")[1].split("\n")[0]

    style = CVStyle()
    assert "fil" in entry_gap(style)
    style.columns.layout = "one"
    assert "fil" not in entry_gap(style)


def test_two_section_titles_side_by_side_each_get_their_lines() -> None:
    """En bas de page, « LANGUES » et « CENTRES D'INTÉRÊT » côte à côte : deux titres, et
    chaque ligne va sous celui qui est au-dessus d'elle."""
    lines = [_styled("COMPÉTENCES", 40, 90, 90, 11, True, "1F4E79")]
    lines += [
        _styled(f"Groupe {n} : outils et méthodes", 40, 108 + 13 * n, 300, 9.5, False, "333333")
        for n in range(3)
    ]
    lines.append(_styled("LANGUES", 40, 160, 60, 11, True, "1F4E79"))
    lines.append(_styled("CENTRES D'INTÉRÊT", 300, 160.8, 110, 11, True, "1F4E79"))
    for n, (left, right) in enumerate(
        [
            ("Anglais : courant", "Randonnée et voyages, lecture de"),
            ("Espagnol : notions", "romans, photographie"),
        ]
    ):
        lines.append(_styled(left, 40, 178 + 13 * n, 90, 9.5, False, "333333"))
        lines.append(_styled(right, 300, 178 + 13 * n, 200, 9.5, False, "333333"))
    page = reading.Page(1, 595, 842, lines)
    found = structure.analyse([page])
    blocks = {b.title_text: [line.text for line in b.lines] for b in found.blocks}
    assert blocks["LANGUES"] == ["Anglais : courant", "Espagnol : notions"]
    assert blocks["CENTRES D'INTÉRÊT"] == [
        "Randonnée et voyages, lecture de",
        "romans, photographie",
    ]
