"""Le style repéré dans un CV PDF importé, et son application au CV de base."""

import json
import shutil
from pathlib import Path

import pytest

from app.ai.schemas import ImportedCV
from app.latex.compile import compile_tex
from app.models.content import CVContent
from app.models.style import CVStyle, Palette
from app.paths import DEMO_DIR
from app.services import cv_import
from app.services.cv_style import (
    KEYS,
    Guess,
    apply_guess,
    guess,
    match_font,
    section_kind,
    tighter,
)
from app.storage.cv_store import save, write_tex
from tests.conftest import needs_latex

needs_poppler = pytest.mark.skipif(
    shutil.which("pdftohtml") is None or shutil.which("pdftoppm") is None,
    reason="pdftohtml ou pdftoppm absent (sudo apt install poppler-utils)",
)


def _example_content() -> CVContent:
    cv = ImportedCV.model_validate(
        json.loads((DEMO_DIR / "reponses-ia.json").read_text())["ImportedCV"]
    )
    return cv_import.to_content(cv, True)


@pytest.mark.parametrize(
    ("family", "font", "badge"),
    [
        ("PTSerif", "PTSerif", "identique"),
        ("Lato", "Lato", "identique"),
        ("Montserrat", "Poppins", "approché"),
        ("Arial", "NotoSans", "approché"),
        ("TimesNewRoman", "NotoSerif", "approché"),
        ("Calibri", "Lato", "approché"),
    ],
)
def test_match_font(family: str, font: str, badge: str) -> None:
    found, found_badge, _ = match_font(family)
    assert (found, found_badge) == (font, badge)


def test_section_kind() -> None:
    assert section_kind("EXPÉRIENCE PROFESSIONNELLE") == "experience"
    assert section_kind("TRAVAIL ASSOCIATIF") == "associative"
    assert section_kind("CENTRES D’INTÉRÊT") == "interests"
    assert section_kind("Diplôme d’ingénieur obtenu en 2027 avec mention très bien") is None


@needs_poppler
def test_guess_the_example_pdf() -> None:
    found = guess(DEMO_DIR / "cv-exemple.pdf", _example_content(), True)
    assert found.font == "PTSerif"
    assert found.layout == "two" and found.band and found.band[1] == "left"
    assert found.titles == "rule" and found.photo == (True, "right") and found.bullet == "bullet"
    assert found.palette and found.palette["primary"] in ("792D1F", "7A2E1F")
    assert (
        found.order
        and found.order[0] == ("formation", "left")
        and ("associatif", "right") in found.order
    )
    assert {f.key for f in found.findings} >= {
        "font",
        "colors",
        "photo",
        "columns",
        "titles",
        "order",
    }


@needs_latex
@needs_poppler
def test_guess_a_one_column_cv(
    tmp_path: Path, base_content: CVContent, base_style: CVStyle
) -> None:
    """Un CV fabriqué par l'appli : une colonne, Poppins, titres en bandeau, tirets, sans photo."""
    style = base_style.model_copy(deep=True)
    style.columns.layout = "one"
    style.header.align = "center"
    style.photo.visible = False
    style.band.visible = False
    style.fonts.main = "Poppins"
    style.palette = Palette(
        primary="0F6E76",
        secondary="3F8F96",
        text="1F2A2E",
        accent="0F6E76",
        band="EEF6F7",
        muted="56656A",
        title_band="E3F1F2",
        link="0F6E76",
    )
    style.section_titles.variant = "band"
    style.section_titles.band_color = "title_band"
    style.section_titles.band_text_color = "primary"
    style.lists.bullet = "dash"
    folder = tmp_path / "cv"
    save(folder, base_content, style)
    result = compile_tex(write_tex(folder))
    assert result.ok and result.pdf
    found = guess(result.pdf, base_content, False)
    assert found.layout == "one" and found.font == "Poppins" and found.titles == "band"
    assert found.centered and found.photo == (False, "right") and found.bullet == "dash"
    assert found.order and [sid for sid, _ in found.order][:2] == ["formation", "competences"]


@needs_poppler
def test_apply_only_what_is_kept(base_style: CVStyle) -> None:
    content = _example_content()
    found = guess(DEMO_DIR / "cv-exemple.pdf", content, True)
    everything, moved = apply_guess(base_style, content, found, set(KEYS))
    assert everything.fonts.main == "PTSerif" and everything.palette.band == found.palette["band"]  # type: ignore[index]
    assert (
        everything.band.visible
        and everything.band.color == "band"
        and everything.columns.layout == "two"
    )
    assert everything.blocks.date.color == "muted" and everything.links.color == "link"
    assert [s.id for s in moved.sections if s.column == "right"][:2] == ["experience", "projets"]
    colors_only, _ = apply_guess(base_style, content, found, {"colors"})
    assert (
        colors_only.fonts.main == base_style.fonts.main
        and colors_only.palette.primary == everything.palette.primary
    )
    untouched, same = apply_guess(base_style, content, found, set())
    assert untouched == base_style and same == content


def _guess_our_own(folder: Path, content: CVContent, style: CVStyle):  # noqa: ANN202
    save(folder, content, style)
    result = compile_tex(write_tex(folder))
    assert result.ok and result.pdf
    return guess(result.pdf, content, False)


@needs_latex
def test_a_coloured_header_is_found_and_rendered(cv_folder: Path, base_content: CVContent) -> None:
    """Un en-tête sur fond coloré (CV faits sous Canva) : repéré, puis rendu par l'appli."""
    style = CVStyle.model_validate_json((cv_folder / "style.json").read_text())
    style.header.fill_color = "0F4C75"
    style.header.fill_text_color = "FFFFFF"
    style.header.rule_visible = False
    style.band.visible = False
    found = _guess_our_own(cv_folder, base_content, style)
    assert found.header_fill and found.header_fill[0] == "0F4C75"
    assert found.header_fill[1] == "FFFFFF" and found.placement == "top"
    applied, _ = apply_guess(CVStyle(), base_content, found, set(KEYS))
    assert applied.header.fill_color == "0F4C75" and not applied.header.rule_visible


@needs_latex
def test_a_side_column_with_the_header_is_found(cv_folder: Path, base_content: CVContent) -> None:
    """Photo et coordonnées en tête d'une colonne foncée, le nom en tête de l'autre."""
    style = CVStyle.model_validate_json((cv_folder / "style.json").read_text())
    style.columns.layout = "two"
    style.band.visible = True
    style.band.column = "left"
    style.palette.band = "2B2B3A"
    style.band.text_color = "FFFFFF"
    style.header.placement = "left"
    found = _guess_our_own(cv_folder, base_content, style)
    assert found.layout == "two" and found.band and found.band == ("2B2B3A", "left")
    assert found.placement == "left" and found.band_text == "FFFFFF"
    applied, _ = apply_guess(CVStyle(), base_content, found, set(KEYS))
    assert applied.header.placement == "left" and applied.band.top_offset_pt == 0
    assert applied.band.text_color == "FFFFFF" and not applied.columns.fill_page


def test_tighter_takes_space_then_margins_then_sizes() -> None:
    style = CVStyle()
    first = tighter(style, 1)
    assert first.spacing.section_gap_pt < style.spacing.section_gap_pt
    assert first.page.margin_cm == style.page.margin_cm and first.blocks.body.size is None
    second = tighter(first, 2)
    assert second.page.margin_cm < first.page.margin_cm
    third = tighter(second, 3)
    assert third.blocks.body.size and third.blocks.body.size < 10
    assert third.blocks.name.size and third.blocks.name.size < second.blocks.name.size  # type: ignore[operator]


def test_a_small_text_size_is_kept(base_content: CVContent) -> None:
    """Un PDF écrit en 9 pt : le texte courant aussi, et les autres blocs à proportion."""
    found = Guess(sizes=(20, 11, 10), text_size=9)
    style, _ = apply_guess(CVStyle(), base_content, found, {"sizes"})
    assert style.blocks.body.size == 9 and style.blocks.summary.size == 9
    assert style.blocks.experience_title.size == 9.9 and style.blocks.name.size == 20
