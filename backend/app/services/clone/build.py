"""Cloner un CV : du PDF d'origine et du contenu lu, un .tex qui reproduit sa forme.

1. ``reading`` lit chaque page au centième de point (mots, formes, images, liens).
2. ``structure`` en tire les colonnes et les rubriques ; ``fields`` retrouve chaque champ.
3. ``anchor`` en fait la mise en page ancrée ; ``render`` écrit le .tex.

Les places viennent de la page elle-même : rien à caler après coup.
"""

import shutil
from pathlib import Path

from app.latex.compile import CompileResult, compile_tex
from app.models.content import CVContent
from app.services.clone import anchor, reading, render, structure
from app.services.clone import fields as F
from app.services.clone.plan import AnchoredLayout

TEX = "main.tex"
PDF = "cv.pdf"
LAYOUT = "clone.json"
PHOTO = "photo.jpg"


def write(folder: Path, layout: AnchoredLayout, content: CVContent) -> Path:
    photo = content.header.photo
    image = photo if photo and (folder / photo).is_file() else None
    path = folder / TEX
    path.write_text(render.render(layout, content, image), encoding="utf-8")
    return path


def plan(
    folder: Path,
    pdf: Path,
    content: CVContent,
    online: bool = True,
    pages: list[reading.Page] | None = None,
    scanned: bool = False,
) -> tuple[AnchoredLayout, structure.Structure, dict[str, F.Hit]]:
    """La mise en page ancrée du PDF pour ce contenu ; ``pages`` : déjà lues (celles d'un
    scan viennent de Tesseract)."""
    pages = pages if pages is not None else reading.read(pdf)
    found = structure.analyse(pages, [s.title for s in content.sections if s.visible])
    hits = F.Locator(found, content).locate()
    shutil.rmtree(folder / anchor.ASSETS, ignore_errors=True)
    layout = anchor.infer(
        pages, found, hits, content, folder, None if scanned else pdf, online=online
    )
    return layout, found, hits


def clone_into(
    folder: Path,
    pdf: Path,
    content: CVContent,
    online: bool = True,
    pages: list[reading.Page] | None = None,
    scanned: bool = False,
) -> CompileResult:
    """Écrit le clone dans ``folder`` (clone.json, ses images, main.tex, cv.pdf) et le compile."""
    layout, _, _ = plan(folder, pdf, content, online, pages, scanned)
    (folder / LAYOUT).write_text(layout.model_dump_json(), encoding="utf-8")
    return compile_tex(write(folder, layout, content))
