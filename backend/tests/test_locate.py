"""Du clic sur l'aperçu à l'élément du contenu : repères du .tex et fichier SyncTeX."""

import re
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.latex.compile import compile_tex
from app.latex.render import render
from app.models.content import CVContent
from app.models.style import CVStyle
from app.services.locate import hit, locate, markers, parse, span
from app.storage.cv_store import write_tex
from tests.conftest import needs_latex


def test_tex_marks_every_item(base_content: CVContent, base_style: CVStyle) -> None:
    marks = markers(render(base_content, base_style))
    kinds = [(kind, *args) for _, kind, args in marks]
    assert kinds[0] == ("header",)
    assert ("contact", "0") in kinds and ("contact", "1") in kinds
    for section in base_content.sections:
        if not section.visible:
            continue
        assert ("section", section.id) in kinds
        if section.kind != "grid":
            for index in range(len(section.items)):
                assert ("item", section.id, str(index)) in kinds
    experience = next(s for s in base_content.sections if s.kind == "experience")
    assert ("bullet", experience.id, "0", "1") in kinds


def test_span_of_a_bullet_is_its_experience() -> None:
    marks = [
        (10, "section", ["exp"]),
        (12, "item", ["exp", "0"]),
        (14, "bullet", ["exp", "0", "0"]),
        (15, "bullet", ["exp", "0", "1"]),
        (17, "item", ["exp", "1"]),
        (20, "none", []),
    ]
    assert span(marks, 3) == (12, 17)
    assert span(marks, 0) == (10, 20)
    assert span(marks, 4) == (17, 20)


SYNCTEX = """SyncTeX Version:1
Input:1:/tmp/cv/./main.tex
Input:2:/usr/share/texlive/article.cls
Unit:1
X Offset:0
Y Offset:0
Content:
{1
[1,5:0,0:6578176,6578176,0
(1,8:0,657818:3289088,657818,0
g1,7:657818,657818
g1,9:1973453,657818
)
(2,1:0,1315636:3289088,657818,0
k1,12:0,1315636:100
)
]
}1
"""


def test_parse_and_hit_on_a_tiny_page() -> None:
    nodes = parse(SYNCTEX)
    # Un point d'échelle TeX par 1/65781,76 de point : la ligne fait 50 pt de large.
    line = nodes[1]
    assert (round(line.x), round(line.top), round(line.width), round(line.bottom)) == (0, 0, 50, 10)
    # Le point le plus à gauche du clic donne la ligne du .tex.
    assert hit(nodes, 5, 5) == 7
    assert hit(nodes, 40, 5) == 9
    # Une boîte d'un autre fichier : la ligne de son point du .tex.
    assert hit(nodes, 5, 15) == 12
    assert hit(nodes, 5, 60) is None


def _words(pdf: Path) -> list[tuple[float, float, str]]:
    run = subprocess.run(["pdftotext", "-bbox", str(pdf), "-"], capture_output=True, text=True)
    box = r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)<'
    found = re.findall(box, run.stdout)
    return [((float(a) + float(c)) / 2, (float(b) + float(d)) / 2, w) for a, b, c, d, w in found]


@needs_latex
def test_click_finds_the_item_and_its_frame(cv_folder: Path) -> None:
    result = compile_tex(write_tex(cv_folder))
    assert result.ok and result.pdf
    words = _words(result.pdf)

    def at(word: str):
        x, y, _ = next(w for w in words if w[2] == word)
        return x, y, locate(cv_folder, x, y)

    _, _, name = at("CAMILLE")
    assert name and name.area == "header"
    _, _, phone = at("Téléphone")
    assert phone and phone.area == "contact" and phone.line == 0

    x, y, job = at("Logistica")
    assert job and (job.section, job.item) == ("experience", 0)
    assert job.box
    assert job.box.x <= x <= job.box.x + job.box.w and job.box.y <= y <= job.box.y + job.box.h

    # Le titre d'un projet est dans le cadre de son projet.
    title = next(w for w in words if w[2] == "Assistant")
    _, _, project = at("pgvector,")
    assert project and (project.section, project.item) == ("projets", 1)
    assert project.box and project.box.y <= title[1]

    _, _, bullet = at("Docker.")
    assert bullet and bullet.section == "experience" and bullet.bullet is not None


@needs_latex
def test_locate_route(client: TestClient) -> None:
    assert client.post("/api/cvs/base/compile").json()["ok"]
    found = client.get("/api/cvs/base/locate", params={"x": 60, "y": 45}).json()
    assert found["area"] == "header" and found["box"]["w"] > 100
    assert client.get("/api/cvs/base/locate", params={"x": 5, "y": 5}).json() is None
