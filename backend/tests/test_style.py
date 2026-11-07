"""Les options de forme : rendu identique par défaut, et chaque option compile."""

from pathlib import Path

import pytest

from app import fonts
from app.latex.compile import compile_tex
from app.latex.render import render
from app.models.content import CVContent
from app.models.style import CVStyle, TextStyle
from app.paths import DEMO_DIR
from app.storage.cv_store import save, write_tex
from app.tools.make_demo import portable
from tests.conftest import needs_latex


def test_default_style_renders_the_committed_base(
    base_content: CVContent, base_style: CVStyle
) -> None:
    """Garde-fou : le générateur ne doit pas changer la version classique par accident.

    Si un changement est voulu, régénérer avec ``make base`` et vérifier la comparaison.
    """
    snapshot = (DEMO_DIR / "main.tex").read_text(encoding="utf-8")
    assert portable(render(base_content, base_style)) == snapshot


def test_font_registry_has_complete_families() -> None:
    found = fonts.families()
    assert {"Lato", "FiraSans", "PTSerif", "NotoSans"} <= set(found)
    for family in found.values():
        assert family.id.isalpha()


def test_band_title_text_has_its_own_color(base_content: CVContent, base_style: CVStyle) -> None:
    base_style.section_titles.variant = "band"
    tex = render(base_content, base_style)
    assert r"\color{cvhexFFFFFF}#2" in tex
    assert r"fill=cvprimary" in tex


def test_unknown_font_is_refused(base_content: CVContent, base_style: CVStyle) -> None:
    base_style.blocks.name.font = "Comic"
    with pytest.raises(fonts.UnknownFont):
        render(base_content, base_style)


def test_block_font_declares_a_family(base_content: CVContent, base_style: CVStyle) -> None:
    base_style.blocks.section_title.font = "FiraSans"
    tex = render(base_content, base_style)
    assert r"\newfontfamily\cvfontFiraSans{FiraSans}[" in tex
    assert r"\cvfontFiraSans" in tex


def _variants() -> dict[str, CVStyle]:
    """Une variante par option, chacune doit compiler sur une page."""
    out: dict[str, CVStyle] = {}

    s = CVStyle()
    s.fonts.main = "PTSans"  # préfixe de fichier avec un « _ »
    s.blocks.name = TextStyle(size=26, leading=30, bold=True, color="primary", font="Spectral")
    s.blocks.section_title.letter_spacing = 8
    s.blocks.section_title.uppercase = True
    out["polices"] = s

    s = CVStyle()
    s.section_titles.variant = "band"
    s.lists.bullet = "chevron"
    s.lists.bullet_color = "primary"
    out["bandeau"] = s

    s = CVStyle()
    s.section_titles.variant = "plain"
    s.summary_frame.visible = True
    s.summary_frame.background_color = "band"
    s.lists.bullet = "square"
    out["cadre"] = s

    s = CVStyle()
    s.photo.shape = "circle"
    s.photo.border_pt = 1.2
    s.photo.position = "left"
    s.photo.offset_x_pt = 2
    s.photo.offset_y_pt = 3
    out["photo-ronde"] = s

    s = CVStyle()
    s.photo.shape = "rounded"
    s.photo.size_mode = "fixed"
    s.photo.size_cm = 2.5
    s.palette.primary = "8B1E3F"
    s.page.margin_cm = 1.3
    s.page.line_spread = 1.05
    s.columns.left_width = 0.36
    s.columns.right_width = 0.6
    s.band.visible = False
    out["mise-en-page"] = s
    return out


@needs_latex
@pytest.mark.parametrize("name", list(_variants()))
def test_style_variant_compiles(name: str, tmp_path: Path, base_content: CVContent) -> None:
    folder = tmp_path / name
    save(folder, base_content, _variants()[name])
    (folder / "imgcv.jpg").write_bytes((DEMO_DIR / "imgcv.jpg").read_bytes())
    result = compile_tex(write_tex(folder))
    assert result.ok, result.errors
    assert result.pages == 1
