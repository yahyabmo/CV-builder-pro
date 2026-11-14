"""Le clonage d'un CV importé : la forme de son PDF recopiée en LaTeX, mot à mot, puis gardée."""

from app.models.content import CVContent
from app.paths import DEMO_DIR
from app.services.pdfread import fields as F
from app.services.pdfread import fill, reading, structure
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
    from app.services.pdfread import scan

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


def test_a_title_that_lost_its_first_letter_gets_it_back() -> None:
    assert structure.restore_first_letter("OMPÉTENCES") == "COMPÉTENCES"
    assert structure.restore_first_letter("ANGUES") == "LANGUES"
    assert structure.restore_first_letter("Profil") == "Profil"


def test_one_page_list_split_by_the_ai_keeps_its_line_labels() -> None:
    """Une liste « Compétences » de la page dont l'IA a sorti les langues : la rubrique des
    langues prend le libellé de sa ligne, et ce libellé ne revient pas comme une langue."""
    from app.models.content import Language, SkillGroup

    lines = [_styled("COMPÉTENCES", 40, 90, 90, 11, True, "1F4E79")]
    lines.append(_styled("• Outils : Git, Docker, Linux", 42, 110, 200, 9.5, False, "333333"))
    lines.append(
        _styled("• Langues : Anglais (C1), Espagnol (B1)", 42, 124, 220, 9.5, False, "333333")
    )
    page = reading.Page(1, 595, 842, lines)
    content = CVContent.model_validate_json((DEMO_DIR / "content.json").read_text())
    for section in content.sections:
        section.items, section.visible = [], False
    skills = next(s for s in content.sections if s.kind == "skills")
    skills.title, skills.visible = "COMPÉTENCES", True
    skills.items = [SkillGroup(label="Outils", text="Git, Docker, Linux")]
    languages = next(s for s in content.sections if s.kind == "languages")
    languages.title, languages.visible = "COMPÉTENCES", True
    languages.items = [Language(name="Anglais", level="C1"), Language(name="Espagnol", level="B1")]
    fixed, _ = fill.complete(content, [page])
    out = next(s for s in fixed.sections if s.kind == "languages")
    assert out.title == "Langues"
    assert [(i.name, i.level) for i in out.items] == [("Anglais", "C1"), ("Espagnol", "B1")]
    assert [g.label for g in next(s for s in fixed.sections if s.kind == "skills").items] == [
        "Outils"
    ]


def test_a_contact_that_repeats_its_label_loses_the_repeat() -> None:
    from app.models.content import ContactItem

    content = _demo()
    content.header.contact_lines = [[ContactItem(text="LinkedIn : prenom-nom", label="LinkedIn")]]
    fill._no_repeated_label(content)
    assert content.header.contact_lines[0][0].text == "prenom-nom"


def test_education_bullets_are_rendered_by_our_template() -> None:
    from app.latex.render import render
    from app.models.style import CVStyle

    content = _demo()
    education = next(s for s in content.sections if s.kind == "education")
    education.items[0].bullets = ["Cours de recherche opérationnelle", "Mention bien"]
    tex = render(content, CVStyle())
    assert "%@ bullet formation 0 1" in tex and "Mention bien" in tex


def test_a_bulleted_education_description_becomes_bullets() -> None:
    from app.models.content import EducationItem

    lines = [_styled("FORMATION", 40, 90, 90, 11, True, "1F4E79")]
    lines.append(_styled("Licence d'informatique", 40, 108, 150, 10, True, "333333"))
    lines.append(_styled("• Niveau actuel : deuxième année", 42, 122, 200, 9.5, False, "333333"))
    lines.append(_styled("• Acquis : algorithmique et réseaux", 42, 136, 210, 9.5, False, "333333"))
    page = reading.Page(1, 595, 842, lines)
    content = CVContent.model_validate_json((DEMO_DIR / "content.json").read_text())
    for section in content.sections:
        section.items, section.visible = [], False
    education = next(s for s in content.sections if s.kind == "education")
    education.title, education.visible = "FORMATION", True
    education.items = [
        EducationItem(
            title="Licence d'informatique",
            place="",
            dates="",
            description="Niveau actuel : deuxième année\nAcquis : algorithmique et réseaux",
        )
    ]
    fixed, _ = fill.complete(content, [page])
    item = next(s for s in fixed.sections if s.kind == "education").items[0]
    assert item.description == ""
    assert item.bullets == ["Niveau actuel : deuxième année", "Acquis : algorithmique et réseaux"]


def test_sub_bullets_merged_by_the_ai_are_split_again() -> None:
    """« Sport » puis trois puces sur la page, écrits par l'IA en un seul élément."""
    lines = [_styled("CENTRES D'INTÉRÊT", 40, 90, 120, 11, True, "1F4E79")]
    lines.append(_styled("Sport", 40, 108, 40, 9.5, True, "333333"))
    for n, word in enumerate(("Football", "Boxe", "Natation")):
        lines.append(_styled(f"• {word}", 50, 122 + 14 * n, 60, 9.5, False, "333333"))
    lines.append(_styled("• Lecture de romans", 42, 170, 120, 9.5, False, "333333"))
    page = reading.Page(1, 595, 842, lines)
    content = CVContent.model_validate_json((DEMO_DIR / "content.json").read_text())
    for section in content.sections:
        section.items, section.visible = [], False
    interests = next(s for s in content.sections if s.kind == "bullets")
    interests.title, interests.visible = "CENTRES D'INTÉRÊT", True
    interests.items = ["Sport : Football, Boxe, Natation", "Lecture de romans"]
    fixed, _ = fill.complete(content, [page])
    items = next(s for s in fixed.sections if s.kind == "bullets").items
    assert items[1:] == ["Football", "Boxe", "Natation", "Lecture de romans"]


def test_a_bullet_copied_into_the_text_is_dropped() -> None:
    """« • Test logiciel » : notre liste met déjà sa puce."""
    content = _demo()
    section = next(s for s in content.sections if s.kind == "bullets")
    section.items = ["• Test logiciel", "- DevOps", "C++ - avancé"]
    fill._no_leading_marker(content)
    assert section.items == ["Test logiciel", "DevOps", "C++ - avancé"]


def test_an_old_clone_setting_is_forgotten() -> None:
    """Le clone est retiré : un meta.json qui garde « shape » se lit encore."""
    from app.models.meta import CVMeta

    meta = CVMeta.model_validate({"name": "CV", "shape": "clone"})
    assert "shape" not in meta.model_dump()
