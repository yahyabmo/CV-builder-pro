"""La lecture d'un CV scanné (une image dans un PDF) : Tesseract, sans IA.

Chaque page est rendue à 300 ppp (pdftoppm), puis lue par Tesseract en français et en
anglais. On garde le texte, pour l'import, et chaque ligne avec sa place (en points,
comme le reste de l'appli), pour ranger le contenu et repérer le style. Tesseract est
facultatif : sans lui, un scan reste refusé avec la commande à lancer.
"""

import csv
import io
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

DPI = 300
PAGES = 3
OCR_FILE = "ocr.json"
# Un mot lu avec moins de confiance (sur 100) est écarté, sauf s'il a au moins trois lettres.
MIN_CONFIDENCE = 30
INSTALL = "sudo apt install -y tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng"


class OcrError(RuntimeError):
    pass


@dataclass
class Line:
    text: str
    x: float
    y: float
    w: float
    h: float
    # Les mots de la ligne : (texte, x, y, largeur, hauteur), en points.
    words: list[tuple[str, float, float, float, float]] = field(default_factory=list)


@dataclass
class ScannedPage:
    width: float
    height: float
    image: str
    lines: list[Line] = field(default_factory=list)


def available() -> bool:
    return shutil.which("tesseract") is not None


def languages() -> str:
    try:
        out = subprocess.run(
            ["tesseract", "--list-langs"], capture_output=True, text=True, timeout=10
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return "eng"
    found = [lang for lang in ("fra", "eng") if lang in out.split()]
    return "+".join(found) or "eng"


def _lines(tsv: str, scale: float) -> list[Line]:
    """Les lignes du TSV de Tesseract (niveau 5 = un mot), regroupées bloc, paragraphe, ligne."""
    groups: dict[tuple[int, int, int], list[dict[str, str]]] = {}
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        if row.get("level") != "5" or not (row.get("text") or "").strip():
            continue
        try:
            confidence = float(row["conf"])
        except (KeyError, ValueError):
            continue
        # Un mot peu sûr est gardé s'il a au moins trois lettres ou chiffres (une adresse
        # e-mail précédée d'une icône, une petite étiquette) ; un signe isolé, non.
        letters = sum(ch.isalnum() for ch in row["text"])
        if confidence < MIN_CONFIDENCE and letters < 3:
            continue
        groups.setdefault(
            (int(row["block_num"]), int(row["par_num"]), int(row["line_num"])), []
        ).append(row)
    lines = []
    for _, rows in sorted(groups.items()):
        words = [
            (
                r["text"].strip(),
                int(r["left"]) * scale,
                int(r["top"]) * scale,
                int(r["width"]) * scale,
                int(r["height"]) * scale,
            )
            for r in sorted(rows, key=lambda r: int(r["left"]))
        ]
        x0 = min(w[1] for w in words)
        y0 = min(w[2] for w in words)
        x1 = max(w[1] + w[3] for w in words)
        y1 = max(w[2] + w[4] for w in words)
        lines.append(Line(" ".join(w[0] for w in words), x0, y0, x1 - x0, y1 - y0, words))
    return sorted(lines, key=lambda line: (round(line.y), line.x))


def read(pdf: Path, folder: Path) -> list[ScannedPage]:
    """Lit les premières pages du scan ; garde leurs images et ``ocr.json`` dans ``folder``."""
    if not available():
        raise OcrError(f"Tesseract manque pour lire un scan : {INSTALL}")
    target = folder / "scan"
    target.mkdir(exist_ok=True)
    subprocess.run(
        ["pdftoppm", "-r", str(DPI), "-png", "-l", str(PAGES), str(pdf), str(target / "page")],
        capture_output=True,
        timeout=120,
        check=True,
    )
    langs = languages()
    scale = 72 / DPI
    pages = []
    for image in sorted(target.glob("page*.png")):
        run = subprocess.run(
            ["tesseract", str(image), "stdout", "-l", langs, "--psm", "3", "tsv"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if run.returncode != 0:
            raise OcrError("Tesseract n'a pas pu lire ce scan.")
        from PIL import Image

        with Image.open(image) as opened:
            width, height = opened.size
        pages.append(
            ScannedPage(
                width=width * scale,
                height=height * scale,
                image=image.name,
                lines=_lines(run.stdout, scale),
            )
        )
    (folder / OCR_FILE).write_text(
        json.dumps([asdict(p) for p in pages], ensure_ascii=False), encoding="utf-8"
    )
    return pages


def text(pages: list[ScannedPage]) -> str:
    """Le texte lu, une ligne par ligne, une ligne vide entre deux blocs éloignés."""
    out: list[str] = []
    for page in pages:
        previous: Line | None = None
        for line in page.lines:
            if previous is not None and line.y - previous.y > 2.2 * max(previous.h, 4):
                out.append("")
            out.append(line.text)
            previous = line
        out.append("")
    return "\n".join(out).strip() + "\n"


def load(folder: Path) -> list[ScannedPage] | None:
    file = folder / OCR_FILE
    if not file.is_file():
        return None
    data = json.loads(file.read_text(encoding="utf-8"))
    return [
        ScannedPage(
            width=p["width"],
            height=p["height"],
            image=p["image"],
            lines=[
                Line(
                    text=line["text"],
                    x=line["x"],
                    y=line["y"],
                    w=line["w"],
                    h=line["h"],
                    words=[tuple(w) for w in line["words"]],
                )
                for line in p["lines"]
            ],
        )
        for p in data
    ]
