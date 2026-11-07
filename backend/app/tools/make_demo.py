"""``make demo`` : régénère le CV fictif.

demo/content.json + demo/style.json → build/demo/main.tex → build/demo/cv.pdf. Une
copie de ``main.tex`` est gardée dans ``demo/``, le chemin des polices remplacé par
``<fonts>`` : le test de rendu la compare au gabarit, sur toute machine.
"""

import shutil
import sys

from app.latex.compile import compile_tex
from app.paths import BASE_FILES, DEMO_DIR, FONTS_DIR, ROOT
from app.storage.cv_store import write_tex

SNAPSHOT = DEMO_DIR / "main.tex"


def portable(tex: str) -> str:
    """Le .tex sans le chemin des polices de cette machine."""
    return tex.replace(str(FONTS_DIR), "<fonts>")


def main() -> int:
    work = ROOT / "build" / "demo"
    work.mkdir(parents=True, exist_ok=True)
    for name in BASE_FILES:
        shutil.copy(DEMO_DIR / name, work / name)
    tex = write_tex(work)
    SNAPSHOT.write_text(portable(tex.read_text(encoding="utf-8")), encoding="utf-8")
    result = compile_tex(tex)
    if not result.ok:
        for error in result.errors:
            where = f"ligne {error.line} : " if error.line else ""
            print(f"Erreur LaTeX — {where}{error.message}")
            if error.context or error.raw:
                print(f"    {error.context or error.raw}")
        return 1
    print(f"Compilé en {result.seconds:.1f} s : {result.pages} page(s) → {result.pdf}")
    for warning in result.warnings:
        print(f"Avertissement : {warning}")
    return 0 if result.pages == 1 else 2


if __name__ == "__main__":
    sys.exit(main())
