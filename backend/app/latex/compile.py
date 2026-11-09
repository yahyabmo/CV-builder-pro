"""Compilation d'un .tex en PDF par latexmk (XeLaTeX).

Les fichiers auxiliaires vont dans ``build/`` à côté du .tex ; seul le PDF
est copié à côté, sous le nom ``cv.pdf``. Une erreur LaTeX est rendue en
« ligne + message lisible », jamais en log brut.
"""

import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

BUILD = "build"
PDF = "cv.pdf"

# Le .tex se modifie dans l'appli (onglet LaTeX) : en ligne, n'importe qui en écrit. LaTeX
# n'y lit (\input, \openin) ni n'y écrit que dans le dossier du CV et ses sous-dossiers,
# jamais un fichier caché ni un chemin qui remonte (« paranoïaque » pour kpathsea).
# Compilations simultanées au plus : en ligne, dix personnes qui compilent en même temps ne
# font pas tomber le serveur ; les suivantes attendent leur tour.
_SLOTS = threading.BoundedSemaphore(int(os.environ.get("CVB_COMPILES", "3")))
SAFE_ENV = {**os.environ, "openin_any": "p", "openout_any": "p", "shell_escape": "f"}

# Messages LaTeX fréquents, en clair.
_READABLE = {
    "Undefined control sequence": "Commande inconnue",
    "Missing $ inserted": "Caractère réservé aux maths (_ ou ^ ?) hors d'une formule",
    "Missing } inserted": "Accolade fermante manquante",
    "Extra }, or forgotten": "Accolade fermante en trop",
    "File `": "Fichier introuvable",
    "Misplaced alignment tab character &": "« & » utilisé hors d'un tableau (écrire \\&)",
    "Runaway argument": "Argument non fermé (accolade manquante)",
    "Emergency stop": "Arrêt de la compilation",
    "Paragraph ended before": "Paragraphe coupé au milieu d'une commande",
    "Package fontspec Error": "Police introuvable",
}

_FILE_LINE = re.compile(r"^(?:\./)?(?P<file>[^:\n]+\.tex):(?P<line>\d+): (?P<message>.+)$", re.M)
_BANG = re.compile(r"^! (?P<message>.+)$", re.M)
_CONTEXT = re.compile(r"^l\.(?P<line>\d+) (?P<context>.*)$", re.M)


@dataclass
class LatexError:
    message: str
    line: int | None = None
    context: str = ""
    raw: str = ""


@dataclass
class CompileResult:
    ok: bool
    pdf: Path | None
    pages: int | None
    seconds: float
    errors: list[LatexError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Hauteur de texte qui dépasse de la page (colonnes de hauteur fixe).
    overflow_pt: float = 0
    # Le même dépassement, colonne par colonne (« left », « right »).
    overflow_columns: dict[str, float] = field(default_factory=dict)


class LatexNotInstalled(RuntimeError):
    pass


def _readable(message: str) -> str:
    for key, text in _READABLE.items():
        if key in message:
            return f"{text} — {message.strip()}"
    return message.strip()


def parse_errors(log: str) -> list[LatexError]:
    """Les erreurs d'un log XeLaTeX (lancé avec -file-line-error)."""
    errors: list[LatexError] = []
    for match in _FILE_LINE.finditer(log):
        context = _CONTEXT.search(log, match.end())
        errors.append(
            LatexError(
                message=_readable(match["message"]),
                line=int(match["line"]),
                context=context["context"].strip() if context else "",
                raw=match["message"].strip(),
            )
        )
    if not errors:
        for match in _BANG.finditer(log):
            context = _CONTEXT.search(log, match.end())
            errors.append(
                LatexError(
                    message=_readable(match["message"]),
                    line=int(context["line"]) if context else None,
                    context=context["context"].strip() if context else "",
                    raw=match["message"].strip(),
                )
            )
    return errors


def overflow(log: str) -> float:
    """Le plus grand dépassement vertical signalé, en points.

    Les colonnes ont une hauteur fixe : un contenu trop long ne passe pas en
    page 2, il déborde en bas de la page. Seul le log le dit.
    """
    found = re.findall(r"^Overfull \\vbox \(([\d.]+)pt too high\)", log, re.M)
    return max((float(value) for value in found), default=0.0)


def overflow_columns(log: str, tex: str) -> dict[str, float]:
    """Le dépassement de chaque colonne, d'après la ligne du .tex signalée par le log.

    Les deux colonnes sont les deux derniers ``\\begin{minipage}`` du fichier :
    un dépassement signalé après le début de la colonne de droite est le sien.
    """
    starts = [
        n for n, line in enumerate(tex.splitlines(), 1) if line.startswith(r"\begin{minipage}")
    ]
    if len(starts) < 2:
        return {}
    left, right = starts[-2], starts[-1]
    out: dict[str, float] = {}
    for value, line in re.findall(
        r"^Overfull \\vbox \(([\d.]+)pt too high\) detected at line (\d+)", log, re.M
    ):
        n = int(line)
        side = "right" if n > right else "left" if n > left else None
        if side:
            out[side] = max(out.get(side, 0.0), float(value))
    return out


def page_count(pdf: Path) -> int | None:
    try:
        info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    found = re.search(r"^Pages:\s+(\d+)", info.stdout, re.M)
    return int(found.group(1)) if found else None


def _silent_failure(output: str) -> LatexError:
    """Un échec sans journal (LaTeX n'a pas démarré) : la fin de la sortie de latexmk."""
    lines = [line for line in output.strip().splitlines() if line.strip()]
    tail = "\n".join(lines[-12:])
    return LatexError(message="La compilation a échoué sans message", raw=tail)


def compile_tex(tex: Path, timeout: float = 60, pdf_name: str = PDF) -> CompileResult:
    """Compile ``tex`` ; le PDF arrive à côté sous le nom ``pdf_name`` (cv.pdf par défaut)."""
    if shutil.which("latexmk") is None or shutil.which("xelatex") is None:
        raise LatexNotInstalled(
            "latexmk ou xelatex manque : sudo apt install texlive-xetex latexmk"
        )
    folder = tex.parent
    build = folder / BUILD
    build.mkdir(exist_ok=True)
    started = time.monotonic()
    command = [
        "latexmk",
        "-xelatex",
        # Jamais de commande du système lancée depuis le .tex (\write18), même autorisée.
        "-no-shell-escape",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        "-silent",
        # Pour remonter d'un clic sur l'aperçu à la ligne du .tex.
        "-synctex=1",
        f"-outdir={BUILD}",
        tex.name,
    ]
    try:
        with _SLOTS:
            run = subprocess.run(
                command, cwd=folder, capture_output=True, text=True, timeout=timeout, env=SAFE_ENV
            )
        failed = run.returncode != 0
    except subprocess.TimeoutExpired:
        return CompileResult(
            ok=False,
            pdf=None,
            pages=None,
            seconds=time.monotonic() - started,
            errors=[LatexError(message=f"Compilation trop longue (plus de {timeout:.0f} s)")],
        )
    seconds = time.monotonic() - started
    log_path = build / (tex.stem + ".log")
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    built = build / (tex.stem + ".pdf")
    if failed or not built.exists():
        errors = parse_errors(log) or [_silent_failure(run.stdout + run.stderr)]
        return CompileResult(ok=False, pdf=None, pages=None, seconds=seconds, errors=errors)
    target = folder / pdf_name
    shutil.copyfile(built, target)
    warnings = sorted(set(re.findall(r"^(Overfull \\[hv]box.*?)$", log, re.M)))
    return CompileResult(
        ok=True,
        pdf=target,
        pages=page_count(target),
        seconds=seconds,
        warnings=warnings,
        overflow_pt=overflow(log),
        overflow_columns=overflow_columns(log, tex.read_text(encoding="utf-8")),
    )
