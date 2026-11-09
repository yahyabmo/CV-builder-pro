import subprocess
from pathlib import Path

from app.latex.compile import compile_tex, parse_errors
from app.storage.cv_store import write_tex
from tests.conftest import needs_latex


def test_parse_errors_reads_line_and_message() -> None:
    log = "./main.tex:42: Undefined control sequence.\nl.42 \\foo\n                {bar}\n"
    [error] = parse_errors(log)
    assert error.line == 42
    assert error.message.startswith("Commande inconnue")
    assert error.context == "\\foo"


@needs_latex
def test_base_compiles_to_one_page(cv_folder: Path) -> None:
    result = compile_tex(write_tex(cv_folder))
    assert result.ok, result.errors
    assert result.pages == 1


@needs_latex
def test_broken_tex_gives_readable_error(cv_folder: Path) -> None:
    tex = write_tex(cv_folder)
    tex.write_text(tex.read_text(encoding="utf-8").replace(r"\rubrique{LANGUES}", r"\inconnue"))
    result = compile_tex(tex)
    assert not result.ok
    assert result.errors[0].line is not None
    assert "Commande inconnue" in result.errors[0].message


@needs_latex
def test_pdf_text_is_ats_readable(cv_folder: Path) -> None:
    """Le texte extrait du PDF a des lettres normales, dans le bon ordre."""
    result = compile_tex(write_tex(cv_folder))
    text = subprocess.run(
        ["pdftotext", str(result.pdf), "-"], capture_output=True, text=True, check=True
    ).stdout
    for ligature in "ﬁﬂﬀﬃﬄ":
        assert ligature not in text
    for keyword in ("apprentissage automatique", "fin", "FastAPI", "PostgreSQL", "LightGBM"):
        assert keyword in text
    # Une colonne est lue d'un bloc : la formation avant les compétences, et
    # l'expérience avant les projets.
    assert text.index("FORMATION") < text.index("COMPÉTENCES")
    assert text.index("EXPÉRIENCE") < text.index("PROJETS")


@needs_latex
def test_new_palette_roles_compile(cv_folder: Path) -> None:
    """Titres en bandeau sur « fond des titres », dates en texte discret, liens colorés."""
    from app.storage.cv_store import load, save

    content, style = load(cv_folder)
    style.section_titles.variant = "band"
    style.section_titles.band_color = "title_band"
    style.section_titles.band_text_color = "primary"
    style.blocks.date.color = "muted"
    style.links.color = "link"
    save(cv_folder, content, style)
    result = compile_tex(write_tex(cv_folder))
    assert result.ok, result.errors
    assert result.pages == 1


@needs_latex
def test_one_column_centered_header(cv_folder: Path) -> None:
    """Une colonne, en-tête centré : une page, les rubriques dans l'ordre du contenu."""
    from app.services.locate import markers
    from app.storage.cv_store import load, save

    content, style = load(cv_folder)
    style.columns.layout = "one"
    style.header.align = "center"
    style.photo.visible = False
    save(cv_folder, content, style)
    tex = write_tex(cv_folder)
    text = tex.read_text(encoding="utf-8")
    assert r"\begin{minipage}[t][\hauteurcol]" not in text
    order = [args[0] for _, kind, args in markers(text) if kind == "section"]
    assert order == [s.id for s in content.sections if s.visible]
    result = compile_tex(tex)
    assert result.ok, result.errors


@needs_latex
def test_tex_cannot_read_outside_its_folder_nor_run_commands(tmp_path: Path) -> None:
    """En ligne, n'importe qui écrit le .tex : ni fichier du système, ni commande."""
    secret = tmp_path / "secret.tex"
    secret.write_text("SECRET", encoding="utf-8")
    for name, body in {
        "absolu": rf"\input{{{secret}}}",
        "parent": r"\input{../secret.tex}",
    }.items():
        folder = tmp_path / name
        folder.mkdir()
        tex = folder / "cv.tex"
        tex.write_text(rf"\documentclass{{article}}\begin{{document}}X{body}\end{{document}}")
        assert not compile_tex(tex).ok, name
    folder = tmp_path / "commande"
    folder.mkdir()
    tex = folder / "cv.tex"
    tex.write_text(
        r"\documentclass{article}\begin{document}X\immediate\write18{touch PIRATE}\end{document}"
    )
    assert compile_tex(tex).ok
    assert not (folder / "PIRATE").exists()
