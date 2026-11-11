"""Les CV scannés : lus par Tesseract, puis clonés d'après leur image."""

import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.models.content import CVContent
from app.paths import DEMO_DIR
from app.services import cv_import, ocr
from app.services.clone import build, likeness, scan
from tests.conftest import needs_latex
from tests.test_import import isolated  # noqa: F401

SAMPLE = DEMO_DIR / "cv-exemple.pdf"
TSV = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    "5\t1\t1\t1\t1\t1\t300\t400\t500\t80\t95\tCAMILLE\n"
    "5\t1\t1\t1\t1\t2\t850\t400\t500\t80\t94\tLAURENT\n"
    "5\t1\t1\t1\t1\t3\t1400\t400\t50\t80\t12\t~\n"
    "5\t1\t2\t1\t1\t1\t300\t900\t400\t40\t90\tFormation\n"
)


def test_tesseract_lines_are_grouped_and_put_in_points() -> None:
    lines = ocr._lines(TSV, 72 / 300)
    assert [line.text for line in lines] == ["CAMILLE LAURENT", "Formation"]
    first = lines[0]
    assert (round(first.x, 1), round(first.y, 1)) == (72.0, 96.0)
    assert round(first.w, 1) == round((1350 - 300) * 72 / 300, 1)
    assert ocr.text([ocr.ScannedPage(595, 842, "p.png", lines)]).startswith(
        "CAMILLE LAURENT\n\nFormation"
    )


def _fake_scan(folder: Path) -> ocr.ScannedPage:
    """Le CV d'exemple en image, et une « lecture » tirée des mots de son PDF."""
    (folder / "scan").mkdir(parents=True)
    subprocess.run(
        [
            "pdftoppm",
            "-r",
            "300",
            "-png",
            "-singlefile",
            str(SAMPLE),
            str(folder / "scan" / "page-1"),
        ],
        check=True,
    )
    image = Image.open(folder / "scan" / "page-1.png").convert("RGB")
    image.save(folder / "source.pdf", resolution=300)
    out = subprocess.run(
        ["pdftotext", "-bbox-layout", "-f", "1", "-l", "1", str(SAMPLE), "-"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    root = ET.fromstring(
        re.sub(r"<!DOCTYPE[^>]*>", "", out).replace('xmlns="http://www.w3.org/1999/xhtml"', "")
    )
    lines = []
    for line in root.iter("line"):
        words = [
            (
                w.text,
                float(w.get("xMin")),
                float(w.get("yMin")),
                float(w.get("xMax")) - float(w.get("xMin")),
                float(w.get("yMax")) - float(w.get("yMin")),
            )
            for w in line.iter("word")
        ]
        x0, y0 = min(w[1] for w in words), min(w[2] for w in words)
        x1, y1 = max(w[1] + w[3] for w in words), max(w[2] + w[4] for w in words)
        lines.append(
            {
                "text": " ".join(w[0] for w in words),
                "x": x0,
                "y": y0,
                "w": x1 - x0,
                "h": y1 - y0,
                "words": words,
            }
        )
    page = {
        "width": image.width * 72 / 300,
        "height": image.height * 72 / 300,
        "image": "page-1.png",
        "lines": lines,
    }
    (folder / ocr.OCR_FILE).write_text(json.dumps([page]))
    return ocr.load(folder)[0]


def test_a_scan_page_gives_shapes_and_the_font(tmp_path: Path) -> None:
    scanned = _fake_scan(tmp_path)
    page = scan.page(scanned, tmp_path, online=False)
    # La police devinée aux largeurs des mots : PT Serif, celle du CV d'exemple.
    assert page.runs[0].font == "PTSerif"
    # Le fond de la colonne de gauche et des filets, trouvés dans l'image.
    assert any(s.kind == "rect" and (s.box[3] - s.box[1]) > 500 for s in page.shapes)
    assert sum(1 for s in page.shapes if s.kind == "line") >= 4
    names = [r for r in page.runs if r.text == "CAMILLE LAURENT"]
    assert names and names[0].color != "000000" and names[0].size > 18


@needs_latex
def test_a_scan_is_cloned(tmp_path: Path) -> None:
    scanned = _fake_scan(tmp_path)
    content = CVContent.model_validate_json((DEMO_DIR / "content.json").read_text())
    content.header.photo = ""
    out = tmp_path / "clone"
    out.mkdir()
    page = scan.page(scanned, tmp_path, online=False)
    result = build.clone_into(
        out, tmp_path / "source.pdf", content, False, page, scan.words(scanned)
    )
    assert result.ok
    measured = likeness.measure(tmp_path / "source.pdf", out / "cv.pdf", scan.words(scanned))
    assert measured.score >= 75, measured


def test_without_tesseract_a_scan_is_refused_with_the_command(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ocr, "available", lambda: False)
    monkeypatch.setattr(cv_import, "is_demo_pdf", lambda data: True)
    image = Image.new("RGB", (600, 800), "white")
    pdf = Path(cv_import.IMPORTS_DIR).parent / "scan.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    image.save(pdf)
    answer = client.post("/api/welcome/import", files={"file": ("cv.pdf", pdf.read_bytes())})
    assert answer.status_code == 422 and "tesseract-ocr" in answer.json()["detail"]


def test_a_scan_is_read_by_ocr(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _fake_scan(tmp_path / "lecture")
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr, "read", lambda pdf, folder: [fake])
    monkeypatch.setattr(cv_import, "is_demo_pdf", lambda data: True)
    data = (tmp_path / "lecture" / "source.pdf").read_bytes()
    reading = client.post("/api/welcome/import", files={"file": ("cv.pdf", data)}).json()
    assert reading["scanned"] is True and reading["photo"] is False and reading["words"] > 300
    assert "CAMILLE LAURENT" in cv_import.text_of(reading["id"])


@pytest.mark.skipif(shutil.which("tesseract") is None, reason=f"Tesseract absent ({ocr.INSTALL})")
def test_real_tesseract_reads_the_sample_scan(tmp_path: Path) -> None:
    _fake_scan(tmp_path)
    (tmp_path / "lu").mkdir()
    pages = ocr.read(tmp_path / "source.pdf", tmp_path / "lu")
    words = ocr.text(pages)
    assert "CAMILLE" in words and "FORMATION" in words and "TrafficLens" in words
