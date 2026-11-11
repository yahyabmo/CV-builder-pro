"""Ce que la machine doit avoir pour produire le PDF et lire les CV importés.

L'écran de démarrage et Réglages l'affichent, avec la commande à copier pour ce
qui manque. Même vérification que ``make doctor``, côté serveur.
"""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

System = Literal["linux", "wsl", "docker", "autre"]

LATEX_FILES = (
    "fontspec.sty",
    "enumitem.sty",
    "tikz.sty",
    "hyperref.sty",
    "xcolor.sty",
    "french.ldf",
)
POPPLER = ("pdftotext", "pdftoppm", "pdftohtml")
# Linux et Windows (WSL, qui est un Ubuntu) : les mêmes commandes apt.
LATEX_FIX = (
    "sudo apt install -y texlive-xetex texlive-latex-extra texlive-pictures "
    "texlive-lang-french latexmk"
)
POPPLER_FIX = "sudo apt install -y poppler-utils"
OCR_FIX = "sudo apt install -y tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng"


class Check(BaseModel):
    id: str
    label: str
    # None : pas vérifiable tant qu'un autre élément manque.
    ok: bool | None
    detail: str
    fix: str | None = None
    # Facultatif : son absence ne bloque pas l'appli (la lecture des scans).
    optional: bool = False


class Machine(BaseModel):
    system: System
    ok: bool
    checks: list[Check]


def system() -> System:
    if Path("/.dockerenv").exists():
        return "docker"
    if sys.platform.startswith("linux"):
        try:
            if "microsoft" in Path("/proc/version").read_text().lower():
                return "wsl"
        except OSError:
            pass
        return "linux"
    return "autre"


def _found(name: str) -> bool:
    try:
        out = subprocess.run(["kpsewhich", name], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return bool(out.stdout.strip())


def check() -> Machine:
    kind = system()
    checks: list[Check] = []

    missing = [tool for tool in ("xelatex", "latexmk") if not shutil.which(tool)]
    checks.append(
        Check(
            id="latex",
            label="Compilation du PDF",
            ok=not missing,
            detail="manquant : " + ", ".join(missing) if missing else "xelatex · latexmk",
            fix=LATEX_FIX if missing else None,
        )
    )
    if shutil.which("kpsewhich"):
        absent = [name for name in LATEX_FILES if not _found(name)]
        checks.append(
            Check(
                id="packages",
                label="Paquets LaTeX du CV",
                ok=not absent,
                detail="manquants : " + ", ".join(absent)
                if absent
                else "fontspec · enumitem · tikz · hyperref · français",
                fix=LATEX_FIX if absent else None,
            )
        )
    else:
        checks.append(
            Check(
                id="packages",
                label="Paquets LaTeX du CV",
                ok=None,
                detail="vérifiés après l'installation de LaTeX",
            )
        )
    gone = [tool for tool in POPPLER if not shutil.which(tool)]
    checks.append(
        Check(
            id="poppler",
            label="Lecture des PDF importés",
            ok=not gone,
            detail="manquants : " + ", ".join(gone) if gone else " · ".join(POPPLER),
            fix=POPPLER_FIX if gone else None,
        )
    )
    checks.append(
        Check(
            id="ocr",
            label="Lecture des CV scannés (facultatif)",
            ok=shutil.which("tesseract") is not None,
            detail="tesseract" if shutil.which("tesseract") else "manquant : tesseract",
            fix=None if shutil.which("tesseract") else OCR_FIX,
            optional=True,
        )
    )
    return Machine(system=kind, ok=all(c.ok for c in checks if not c.optional), checks=checks)
