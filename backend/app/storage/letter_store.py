"""La lettre de motivation d'un CV : letter.json, lettre.tex et lettre.pdf dans son dossier."""

import json
from pathlib import Path

from app.latex.letter import render_letter
from app.models.letter import LetterContent
from app.storage import cv_store

LETTER = "letter.json"
TEX = "lettre.tex"
PDF = "lettre.pdf"


def load(path: Path) -> LetterContent | None:
    file = path / LETTER
    if not file.exists():
        return None
    return LetterContent.model_validate_json(file.read_text(encoding="utf-8"))


def save(path: Path, letter: LetterContent) -> None:
    tmp = path / (LETTER + ".tmp")
    tmp.write_text(
        json.dumps(letter.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path / LETTER)


def render(path: Path, letter: LetterContent) -> str:
    content, style = cv_store.load(path)
    return render_letter(letter, content, style)


def write_tex(path: Path) -> Path:
    """Régénère lettre.tex depuis letter.json et le haut du CV."""
    letter = load(path)
    if letter is None:
        raise FileNotFoundError(LETTER)
    tex = path / TEX
    tex.write_text(render(path, letter), encoding="utf-8")
    return tex


def plain_text(letter: LetterContent) -> str:
    """Le corps de la lettre, à coller dans un formulaire ou un mail."""
    parts = [letter.salutation, *letter.paragraphs, letter.closing, letter.signature]
    return (
        "\n\n".join(p.replace("**", "").replace("__", "").strip() for p in parts if p.strip())
        + "\n"
    )


def pdf_version(path: Path) -> int | None:
    pdf = path / PDF
    return pdf.stat().st_mtime_ns if pdf.exists() else None
