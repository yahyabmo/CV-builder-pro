"""D'un clic sur l'aperçu au champ du contenu.

XeLaTeX écrit, à côté du PDF, un fichier SyncTeX : chaque boîte de la page y
porte la ligne du .tex d'où elle vient. Le .tex généré porte des repères
(« %@ item experience 0 », voir ``render.mark``) : le dernier repère avant la
ligne cliquée dit quel élément du contenu a été touché. Le cadre de cet élément
sur la page est l'union des lignes de texte qui viennent de ses lignes du .tex.

Le fichier SyncTeX est lu ici directement : l'outil ``synctex`` ne rend qu'une
boîte par ligne, parfois la colonne entière.
"""

import gzip
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.latex.compile import BUILD

TEX = "main.tex"
SYNCTEX = "main.synctex.gz"
# Un CV cloné : LaTeX y écrit la boîte de chaque unité, une fois posée (voir clone/render).
POSITIONS = "main.pos"
_CLONE_HEADER = "% CV cloné"
# Un point TeX (pt) en point PostScript (bp).
_BP_PER_PT = 72 / 72.27

_MARK = re.compile(r"^%@ (\w+)((?: [\w-]+)*)$")
# « (1,82:h,v:W,H,D » : sorte, fichier, ligne, position, puis taille d'une boîte.
_RECORD = re.compile(
    r"^([(\[hvgkx$r])(\d+),(\d+):(-?\d+),(-?\d+)(?::(-?\d+)(?:,(-?\d+),(-?\d+))?)?"
)
_SETTING = re.compile(r"^(Input|Unit|Magnification|X Offset|Y Offset):(.*)$")
# Un point PostScript (bp) en points d'échelle TeX (sp).
_SP_PER_BP = 65781.76
# Au-delà, une boîte est une colonne entière, pas une ligne de texte.
_TALLEST_BP = 400
# Un clic entre deux lignes touche encore la plus proche, à cette distance.
_NEAR_BP = 6


class Box(BaseModel):
    """Un rectangle de la page, en points, depuis le coin haut gauche."""

    x: float
    y: float
    w: float
    h: float


class Location(BaseModel):
    """Ce qu'un clic a touché, et son cadre sur la page."""

    area: Literal["header", "contact", "section"]
    section: str | None = None
    item: int | None = None
    bullet: int | None = None
    # Une ligne de coordonnées (en partant de 0).
    line: int | None = None
    box: Box | None = None


@dataclass
class Node:
    """Une boîte (« ( » ligne de texte, « [ » bloc) ou un point de la page."""

    kind: str
    # Ligne du .tex ; 0 si elle vient d'un autre fichier (paquet, classe).
    line: int
    x: float
    top: float
    bottom: float
    width: float
    parent: int | None

    @property
    def height(self) -> float:
        return self.bottom - self.top

    def contains(self, x: float, y: float, slack: float = 0) -> bool:
        across = self.x - slack <= x <= self.x + self.width + slack
        return across and self.top - slack <= y <= self.bottom + slack


def parse(text: str, page: int = 1) -> list[Node]:
    """Les boîtes et les points d'une page du fichier SyncTeX (décompressé)."""
    unit, magnification, x_offset, y_offset = 1.0, 1000.0, 0.0, 0.0
    tag: str | None = None
    nodes: list[Node] = []
    stack: list[int] = []
    current = 0
    for raw in text.splitlines():
        setting = _SETTING.match(raw)
        if setting:
            key, value = setting[1], setting[2]
            if key == "Input":
                number, _, path = value.partition(":")
                if tag is None and Path(path).name == TEX:
                    tag = number
            elif key == "Unit":
                unit = float(value)
            elif key == "Magnification":
                magnification = float(value)
            elif key == "X Offset":
                x_offset = float(value)
            elif key == "Y Offset":
                y_offset = float(value)
            continue
        if raw.startswith("{"):
            current = int(raw[1:] or 0)
            stack = []
            continue
        if current != page:
            continue
        if raw[:1] in ")]":
            if stack:
                stack.pop()
            continue
        record = _RECORD.match(raw)
        if not record:
            continue
        kind, source, line, h, v, w, hh, d = record.groups()
        scale = unit * magnification / 1000 / _SP_PER_BP
        x = (int(h) + x_offset) * scale
        y = (int(v) + y_offset) * scale
        width = int(w) * scale if w else 0.0
        above = int(hh) * scale if hh else 0.0
        below = int(d) * scale if d else 0.0
        nodes.append(
            Node(
                kind=kind,
                line=int(line) if source == tag else 0,
                x=x,
                top=y - above,
                bottom=y + below,
                width=width,
                parent=stack[-1] if stack else None,
            )
        )
        if kind in "([":
            stack.append(len(nodes) - 1)
    return nodes


_CACHE: dict[Path, tuple[int, int, list[Node]]] = {}


def nodes_of(synctex: Path, page: int) -> list[Node]:
    """Les nœuds d'une page, relus seulement si le fichier a changé."""
    stamp = synctex.stat().st_mtime_ns
    cached = _CACHE.get(synctex)
    if cached and cached[0] == stamp and cached[1] == page:
        return cached[2]
    with gzip.open(synctex, "rt", encoding="utf-8", errors="replace") as file:
        found = parse(file.read(), page)
    _CACHE[synctex] = (stamp, page, found)
    return found


def _lines(nodes: list[Node]) -> list[int]:
    """Les lignes de texte de la page (pas les colonnes entières)."""
    return [i for i, n in enumerate(nodes) if n.kind == "(" and 0 < n.height < _TALLEST_BP]


def hit(nodes: list[Node], x: float, y: float) -> int | None:
    """La ligne du .tex sous le point (x, y)."""
    lines = _lines(nodes)
    inside = [i for i in lines if nodes[i].contains(x, y)] or [
        i for i in lines if nodes[i].contains(x, y, _NEAR_BP)
    ]
    if not inside:
        return None
    box = min(inside, key=lambda i: nodes[i].width * nodes[i].height)
    points = [n for n in nodes if n.parent == box and n.kind not in "([" and n.line]
    left = [n for n in points if n.x <= x]
    if left:
        return max(left, key=lambda n: n.x).line
    if points:
        return min(points, key=lambda n: n.x).line
    return nodes[box].line or None


def frame(nodes: list[Node], start: int, end: int | None) -> Box | None:
    """Le cadre des lignes de texte venues des lignes ]start, end[ du .tex."""
    last = end if end is not None else 10**9

    def within(line: int) -> bool:
        return start < line < last

    chosen = {i for i in _lines(nodes) if within(nodes[i].line)}
    for node in nodes:
        if node.kind not in "([" and node.parent is not None and within(node.line):
            parent = nodes[node.parent]
            # Une ligne écrasée (hauteur nulle) est un calque de la page entière, pas du texte.
            if parent.kind == "(" and 0 < parent.height < _TALLEST_BP:
                chosen.add(node.parent)
    return union([nodes[i] for i in chosen])


def union(nodes: list[Node], margin: float = 2) -> Box | None:
    if not nodes:
        return None
    left = min(n.x for n in nodes) - margin
    top = min(n.top for n in nodes) - margin
    right = max(n.x + n.width for n in nodes) + margin
    bottom = max(n.bottom for n in nodes) + margin
    return Box(
        x=round(left, 2), y=round(top, 2), w=round(right - left, 2), h=round(bottom - top, 2)
    )


Mark = tuple[int, str, list[str]]


def markers(tex: str) -> list[Mark]:
    """Les repères du .tex : (numéro de ligne, sorte, arguments)."""
    found: list[Mark] = []
    for number, line in enumerate(tex.splitlines(), 1):
        match = _MARK.match(line)
        if match:
            found.append((number, match[1], match[2].split()))
    return found


def _location(kind: str, args: list[str]) -> Location | None:
    try:
        if kind == "header":
            return Location(area="header")
        if kind == "contact":
            return Location(area="contact", line=int(args[0]))
        if kind == "section":
            return Location(area="section", section=args[0])
        if kind == "item":
            return Location(area="section", section=args[0], item=int(args[1]))
        if kind == "bullet":
            return Location(area="section", section=args[0], item=int(args[1]), bullet=int(args[2]))
    except (IndexError, ValueError):
        return None
    return None


# Où s'arrête le cadre d'un repère : au prochain repère de ces sortes (tous sinon).
_STOPS: dict[str, set[str]] = {
    "section": {"section", "none", "header", "contact"},
    "item": {"item", "section", "none", "header", "contact"},
}


def span(marks: list[Mark], index: int) -> tuple[int, int | None]:
    """Les lignes du cadre du repère ``index`` : après son début, avant sa fin.

    Une puce d'expérience a le cadre de toute l'expérience ; une rubrique
    s'étend sur tous ses éléments ; l'en-tête et les coordonnées s'arrêtent au
    repère suivant.
    """
    while marks[index][1] == "bullet" and index > 0:
        index -= 1
    start, kind, _ = marks[index]
    stops = _STOPS.get(kind)
    end = next((m[0] for m in marks[index + 1 :] if stops is None or m[1] in stops), None)
    return start, end


@dataclass
class Placed:
    """Une unité d'un CV cloné, là où LaTeX l'a posée."""

    line: int
    page: int
    unit: str
    x0: float
    x1: float
    top: float
    bottom: float

    def contains(self, x: float, y: float, slack: float = 0) -> bool:
        across = self.x0 - slack <= x <= self.x1 + slack
        return across and self.top - slack <= y <= self.bottom + slack

    @property
    def area(self) -> float:
        return (self.x1 - self.x0) * (self.bottom - self.top)


def _length(text: str) -> float:
    return float(text.removesuffix("pt")) * _BP_PER_PT


def positions(folder: Path) -> list[Placed] | None:
    """Les unités posées d'un CV cloné ; None si ce n'est pas un clone (ou s'il n'est pas
    encore compilé avec ses positions)."""
    tex = folder / TEX
    file = folder / BUILD / POSITIONS
    if not tex.is_file() or not file.is_file():
        return None
    with tex.open(encoding="utf-8") as handle:
        if not handle.readline().startswith(_CLONE_HEADER):
            return None
    if file.stat().st_mtime_ns < tex.stat().st_mtime_ns:
        return None
    found = []
    for raw in file.read_text(encoding="utf-8", errors="replace").splitlines():
        bits = raw.split()
        if len(bits) != 7:
            continue
        try:
            found.append(
                Placed(
                    line=int(bits[0]),
                    page=int(bits[1]),
                    unit=bits[2],
                    x0=float(bits[3]),
                    x1=float(bits[4]),
                    top=_length(bits[5]),
                    bottom=_length(bits[6]),
                )
            )
        except ValueError:
            continue
    return found


def _same(a: Location, b: Location) -> bool:
    """Deux unités du même cadre : la même entrée (ses puces comprises), la même rubrique
    pour un titre, la même ligne de coordonnées, l'en-tête."""
    if a.area != b.area:
        return False
    if a.area == "contact":
        return a.line == b.line
    if a.area == "section":
        if a.section != b.section:
            return False
        return a.item is None or a.item == b.item
    return True


def _locate_clone(placed: list[Placed], marks: list[Mark], x: float, y: float, page: int):
    here = [p for p in placed if p.page == page]
    inside = [p for p in here if p.contains(x, y)] or [
        p for p in here if p.contains(x, y, _NEAR_BP)
    ]
    if not inside:
        return None
    lines = [m[0] for m in marks]

    def where(p: Placed) -> Location | None:
        before = [i for i, line in enumerate(lines) if line <= p.line]
        if not before:
            return None
        _, kind, args = marks[before[-1]]
        return _location(kind, args)

    clicked = min(inside, key=lambda p: p.area)
    found = where(clicked)
    if found is None:
        return None
    family = []
    for p in here:
        other = where(p)
        if other is None or not _same(found, other):
            continue
        # L'en-tête et les coordonnées d'un clone peuvent être éclatés (le nom à droite,
        # l'accroche ou l'adresse à gauche) : le cadre reste dans la colonne de la partie cliquée.
        if found.area in ("header", "contact") and not (p.x0 < clicked.x1 and p.x1 > clicked.x0):
            continue
        family.append(p)
    if family:
        left = min(p.x0 for p in family) - 2
        top = min(p.top for p in family) - 2
        right = max(p.x1 for p in family) + 2
        bottom = max(p.bottom for p in family) + 2
        found.box = Box(
            x=round(left, 2), y=round(top, 2), w=round(right - left, 2), h=round(bottom - top, 2)
        )
    return found


def locate(folder: Path, x: float, y: float, page: int = 1) -> Location | None:
    """L'élément du contenu sous le point (x, y) de la page, en points depuis le haut gauche."""
    synctex = folder / BUILD / SYNCTEX
    tex = folder / TEX
    placed = positions(folder)
    if placed is not None:
        return _locate_clone(placed, markers(tex.read_text(encoding="utf-8")), x, y, page)
    if not synctex.exists() or not tex.exists():
        return None
    nodes = nodes_of(synctex, page)
    line = hit(nodes, x, y)
    if line is None:
        return None
    marks = markers(tex.read_text(encoding="utf-8"))
    before = [i for i, mark in enumerate(marks) if mark[0] <= line]
    if not before:
        return None
    _, kind, args = marks[before[-1]]
    found = _location(kind, args)
    if found is not None:
        found.box = frame(nodes, *span(marks, before[-1]))
    return found
