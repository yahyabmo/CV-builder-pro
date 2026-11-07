"""« make doctor » : ce qui manque sur cette machine pour lancer CV Builder Pro.

Il ne modifie rien : il vérifie, puis affiche la commande exacte pour chaque
manque, sous Linux (Ubuntu, Debian) ou Windows (WSL). Seule la bibliothèque
standard de Python : il tourne avant toute installation.

    python3 scripts/doctor.py
"""

import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_MIN = (3, 12)
NODE_MIN = (20, 19)
POPPLER = ("pdftotext", "pdftoppm", "pdftohtml", "pdfimages", "pdfinfo", "pdffonts")
LATEX_FILES = (
    "fontspec.sty",
    "enumitem.sty",
    "tikz.sty",
    "hyperref.sty",
    "xcolor.sty",
    "french.ldf",
)
APT = (
    "sudo apt install -y texlive-xetex texlive-latex-extra texlive-pictures "
    "texlive-lang-french latexmk poppler-utils make"
)
NVM = (
    "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash"
    ' && . "$HOME/.nvm/nvm.sh" && nvm install --lts'
)

GREEN, YELLOW, RED, DIM, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[0m"
if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    GREEN = YELLOW = RED = DIM = RESET = ""


def system() -> str:
    if sys.platform.startswith("linux"):
        try:
            if "microsoft" in Path("/proc/version").read_text().lower():
                return "wsl"
        except OSError:
            pass
        return "linux"
    return "autre"


def run(*command: str) -> str:
    try:
        out = subprocess.run(command, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (out.stdout + out.stderr).strip()


def env_value(name: str) -> str:
    """La valeur d'une variable de .env (ou de l'environnement), jamais affichée."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name and value.strip().strip("\"'"):
                return value.strip()
    return os.environ.get(name, "")


def ours(port: int) -> bool:
    """CV Builder Pro répond-il sur ce port (et pas une autre appli) ?"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as reply:
            return json.load(reply).get("app") == "cv-builder-pro"
    except (OSError, ValueError, AttributeError):
        return False


def version(text: str) -> tuple[int, ...]:
    found = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    return tuple(int(part) for part in found.groups() if part) if found else ()


class Report:
    def __init__(self) -> None:
        self.fixes: list[str] = []
        self.blocking = False

    def ok(self, label: str, detail: str = "") -> None:
        print(f"  {GREEN}✓{RESET} {label}{f' {DIM}({detail}){RESET}' if detail else ''}")

    def bad(self, label: str, fix: str | None, detail: str = "") -> None:
        print(f"  {RED}✗{RESET} {label}{f' {DIM}({detail}){RESET}' if detail else ''}")
        self.blocking = True
        if fix and fix not in self.fixes:
            self.fixes.append(fix)

    def note(self, label: str, detail: str = "") -> None:
        print(f"  {YELLOW}!{RESET} {label}{f' {DIM}({detail}){RESET}' if detail else ''}")


def main() -> int:
    kind = system()
    names = {"linux": "Linux", "wsl": "Windows (WSL)", "autre": platform.system()}
    print(f"CV Builder Pro · vérification de la machine ({names[kind]})\n")
    report = Report()
    if kind == "autre":
        report.note(
            "Système non pris en charge : Linux, ou Windows avec WSL",
            "sous Windows, installe WSL (wsl --install) puis lance ce script dans Ubuntu",
        )

    print("Logiciels")
    found = version(run(sys.executable, "--version"))
    if found >= PYTHON_MIN:
        report.ok("Python", ".".join(map(str, found)))
    else:
        # Ubuntu 22.04 n'a que Python 3.10 : le dépôt deadsnakes apporte 3.13.
        fix = (
            "sudo add-apt-repository -y ppa:deadsnakes/ppa"
            " && sudo apt install -y python3.13 python3.13-venv"
        )
        report.bad("Python 3.12 ou plus récent", fix, ".".join(map(str, found)) or "absent")
    if found >= PYTHON_MIN and run(sys.executable, "-c", "import ensurepip"):
        # Sans ce module, « make install » ne peut pas créer .venv.
        package = f"python{found[0]}.{found[1]}-venv"
        report.bad("Module venv de Python", f"sudo apt install -y {package}", "absent")

    node = version(run("node", "--version"))
    if node >= NODE_MIN:
        report.ok("Node.js", ".".join(map(str, node)))
    else:
        report.bad("Node.js 20.19 ou plus récent", NVM, ".".join(map(str, node)) or "absent")

    latex_fix = APT
    for tool in ("xelatex", "latexmk"):
        if shutil.which(tool):
            report.ok(tool)
        else:
            report.bad(tool, latex_fix, "absent")
    if shutil.which("kpsewhich"):
        missing = [name for name in LATEX_FILES if not run("kpsewhich", name)]
        if missing:
            report.bad("Paquets LaTeX du CV", latex_fix, "manquants : " + ", ".join(missing))
        else:
            report.ok("Paquets LaTeX du CV", "fontspec, enumitem, tikz, hyperref, xcolor, français")

    absent = [tool for tool in POPPLER if not shutil.which(tool)]
    if absent:
        report.bad("Outils PDF (poppler)", APT, "manquants : " + ", ".join(absent))
    else:
        report.ok("Outils PDF (poppler)")

    print("\nProjet")
    venv = ROOT / ".venv" / "bin" / "python"
    if venv.exists() and not run(str(venv), "-c", "import fastapi, uvicorn, jinja2, pydantic, PIL"):
        report.ok("Environnement Python (.venv)")
    else:
        report.bad("Environnement Python (.venv) et ses dépendances", "make install")
    if (ROOT / "frontend" / "node_modules").is_dir():
        report.ok("Dépendances de l'interface (frontend/node_modules)")
    else:
        report.bad("Dépendances de l'interface", "make install")
    if (ROOT / "frontend" / "dist" / "index.html").exists():
        report.ok("Interface construite", "make start la reconstruit si besoin")
    else:
        report.note("Interface pas encore construite", "make start s'en charge")

    print("\nRéglages")
    found_keys = [k for k in ("GEMINI_API_KEY", "MISTRAL_API_KEY") if env_value(k)]
    if found_keys:
        report.ok("Clé d'IA", ", ".join(found_keys) + ", valeur jamais affichée")
    else:
        report.note(
            "Pas encore de clé d'IA",
            "saisis-la dans Réglages, ou essaie le fournisseur Démo, sans clé",
        )
    with socket.socket() as probe:
        free = probe.connect_ex(("127.0.0.1", 8000)) != 0
    if free:
        report.ok("Port 8000 libre")
    elif ours(8000):
        report.ok("CV Builder Pro tourne déjà", "http://localhost:8000")
    else:
        report.note(
            "Le port 8000 est pris par un autre programme",
            "le raccourci prendra le port libre suivant ; make start : PORT=8010 make start",
        )

    print()
    if report.fixes:
        print("Pour corriger, dans l'ordre :")
        for fix in report.fixes:
            print(f"  {fix}")
        print("\nPuis relance « make doctor ».")
        return 1
    print(f"{GREEN}Tout est prêt.{RESET} Lance « make start », ou le raccourci du bureau.")
    return 1 if report.blocking else 0


if __name__ == "__main__":
    sys.exit(main())
