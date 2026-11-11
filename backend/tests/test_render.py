import re

import pytest
from pydantic import ValidationError

from app.latex.render import grid_rows, pt, render
from app.models.content import CVContent, GridItem, Language
from app.models.style import CVStyle, TextStyle


def test_pt() -> None:
    assert pt(12.0) == "12"
    assert pt(1.5) == "1.5"
    assert pt(24.88) == "24.88"
    assert pt(0) == "0"


def test_grid_rows() -> None:
    items = [GridItem(text=t) for t in "ab"] + [GridItem(text="c", wide=True), GridItem(text="d")]
    assert grid_rows(items) == [("pair", "a", "b"), ("wide", "c"), ("single", "d")]
    assert grid_rows([GridItem(text="a"), GridItem(text="w", wide=True)]) == [
        ("single", "a"),
        ("wide", "w"),
    ]


def test_render_base(base_content: CVContent, base_style: CVStyle) -> None:
    tex = render(base_content, base_style)
    assert tex.count(r"\begin{document}") == 1
    assert r"\rubrique[0pt]{FORMATION}" in tex
    assert r"\rubrique[0pt]{EXPÉRIENCE PROFESSIONNELLE}" in tex
    assert r"Data Science \& IA" in tex
    assert r"\textbf{apprentissage automatique}" in tex
    assert "Ligatures={TeX, CommonOff}" in tex
    # Aucune marque de template ne doit rester.
    assert not re.search(r"\\(VAR|BLOCK)\{", tex)
    # Les accolades sont équilibrées.
    assert tex.count("{") - tex.count(r"\{") == tex.count("}") - tex.count(r"\}")


def test_render_escapes_content(base_content: CVContent, base_style: CVStyle) -> None:
    base_content.header.summary = "Budget 100% & C# en {test}_final"
    tex = render(base_content, base_style)
    assert r"Budget 100\% \& C\# en \{test\}\_final" in tex


def test_hidden_section_is_not_rendered(base_content: CVContent, base_style: CVStyle) -> None:
    for section in base_content.sections:
        if section.id == "langues":
            section.visible = False
    assert "LANGUES" not in render(base_content, base_style)


def test_text_style_and_colors(base_content: CVContent, base_style: CVStyle) -> None:
    base_style.blocks.section_title = TextStyle(size=14, bold=True, uppercase=True, color="AA0000")
    tex = render(base_content, base_style)
    assert r"\definecolor{cvhexAA0000}{HTML}{AA0000}" in tex
    assert r"\textbf{\color{cvhexAA0000}\MakeUppercase{#2}}" in tex


def test_unknown_color_is_refused(base_content: CVContent, base_style: CVStyle) -> None:
    base_style.blocks.name.color = "violet"
    with pytest.raises(ValueError, match="couleur inconnue"):
        render(base_content, base_style)


def test_content_typo_is_refused() -> None:
    with pytest.raises(ValidationError):
        CVContent.model_validate(
            {"header": {"name": "x", "headline": "y", "summary": "z", "nmae": "?"}}
        )


def test_palette_roles_and_link_color(base_content: CVContent, base_style: CVStyle) -> None:
    """Les rôles ajoutés sont déclarés sans « _ », utilisables par un bloc et par les liens."""
    style = base_style.model_copy(deep=True)
    style.blocks.date.color = "muted"
    style.section_titles.band_color = "title_band"
    style.links.color = "link"
    tex = render(base_content, style)
    assert r"\definecolor{cvtitleband}{HTML}{E3EAF6}" in tex
    assert r"\definecolor{cvmuted}{HTML}" in tex
    assert r"\color{cvmuted}" in tex
    assert r"\hypersetup{colorlinks=true, urlcolor=cvlink" in tex
    assert r"\hypersetup" not in render(base_content, base_style)


def test_language_without_level_has_no_colon(base_content: CVContent, base_style: CVStyle) -> None:
    section = next(s for s in base_content.sections if s.kind == "languages")
    section.items.append(Language(name="Allemand", level=""))
    tex = render(base_content, base_style)
    assert "Allemand}" in tex or "Allemand " in tex
    assert "Allemand :" not in tex
