"""Cloner un CV : du PDF d'origine et du contenu lu, un .tex qui reproduit sa forme.

Après une première mise en page déduite du PDF, le calage compile le clone, retrouve
chaque élément dans les deux PDF et corrige les écarts (place des cadres, espaces entre
les blocs, les titres, les entrées et les puces), en quelques tours.
"""

import statistics
from pathlib import Path

from app.latex.compile import CompileResult, compile_tex
from app.models.content import CVContent
from app.services.clone import layout as inference
from app.services.clone import likeness, tex
from app.services.clone import page as pages
from app.services.clone.model import CloneLayout

TEX = "main.tex"
PDF = "cv.pdf"
ROUNDS = 3

Anchor = tuple[float, float, float]  # haut, gauche, droite


def write(folder: Path, layout: CloneLayout, content: CVContent) -> Path:
    photo = tex.PHOTO if (folder / tex.PHOTO).is_file() else None
    path = folder / TEX
    path.write_text(tex.render(layout, content, photo), encoding="utf-8")
    return path


def anchors(page: pages.Page, content: CVContent) -> dict[str, Anchor]:
    """La place de chaque élément repérable : en-tête, titres, entrées, lignes, puces."""
    m, header, found, contacts = inference.locate(page, content)
    out: dict[str, Anchor] = {}

    def put(name: str, hit: inference.Hit | None) -> None:
        if hit is not None:
            out[name] = (hit.top, hit.x0, hit.x1)

    for name, hit in header.items():
        put(name, hit)
    located = [h for h in contacts if h]
    if located:
        first = min(located, key=lambda h: (h.top, h.x0))
        out["contacts"] = (first.top, min(h.x0 for h in located), max(h.x1 for h in located))
    for sid, f in found.items():
        put(f"{sid}.title", f.title)
        for n, item in enumerate(f.items):
            flat = inference._flat(item)
            if not flat:
                continue
            first = min(flat, key=lambda h: (h.top, h.x0))
            out[f"{sid}.{n}"] = (first.top, first.x0, max(h.x1 for h in flat))
            for name, value in item.items():
                if isinstance(value, list):
                    for k, hit in enumerate(sorted(value, key=lambda h: h.top)):
                        put(f"{sid}.{n}.b{k}", hit)
                else:
                    put(f"{sid}.{n}.{name}", value)
    for run in m.leftovers():
        out.setdefault(f"label:{inference.key(run.text)}", (run.y, run.x, run.right))
    return out


def _block_key(block, layout: CloneLayout, content: CVContent) -> list[str]:
    if block.kind in ("name", "headline", "summary", "contacts"):
        return [block.kind]
    if block.kind == "label":
        return [f"label:{inference.key(block.text)}"]
    look = layout.look(block.ref)
    if look and look.title_mode == "above":
        return [f"{block.ref}.title", f"{block.ref}.0"]
    return [f"{block.ref}.0"]


def calibrate(
    layout: CloneLayout, content: CVContent, want: dict[str, Anchor], got: dict[str, Anchor]
) -> None:
    """Corrige la mise en page d'après les écarts mesurés (clone − original)."""

    def dy(name: str) -> float | None:
        if name in want and name in got:
            return got[name][0] - want[name][0]
        return None

    for frame in layout.frames:
        previous = None
        dxs = []
        for n, block in enumerate(frame.blocks):
            delta = next(
                (d for d in (dy(k) for k in _block_key(block, layout, content)) if d is not None),
                None,
            )
            # Le bord du cadre : d'après le contenu (un titre peut être décalé).
            for k in _block_key(block, layout, content):
                if k in want and k in got and block.align == "left" and not k.endswith(".title"):
                    dxs.append(got[k][1] - want[k][1])
                    break
            if delta is None:
                continue
            if previous is None:
                if n == 0:
                    frame.y = round(frame.y - delta, 2)
                else:
                    block.gap = round(block.gap - delta, 2)
            else:
                block.gap = round(block.gap - (delta - previous), 2)
            previous = delta
        if dxs:
            frame.x = round(frame.x - statistics.median(dxs), 2)

    for look in layout.looks:
        sid = look.id
        section = next((s for s in content.sections if s.id == sid), None)
        if section is None:
            continue
        title, first = dy(f"{sid}.title"), dy(f"{sid}.0")
        if title is not None and first is not None and look.title_mode == "above":
            look.after_title = round(look.after_title - (first - title), 2)
        steps = []
        for n in range(1, len(section.items)):
            a, b = dy(f"{sid}.{n - 1}"), dy(f"{sid}.{n}")
            if a is not None and b is not None:
                # L'écart entre deux entrées dépend aussi de la hauteur de la précédente :
                # on corrige d'après sa dernière ligne repérée.
                last = _last_line(sid, n - 1, want, got)
                steps.append(b - (last if last is not None else a))
        if steps:
            look.item_gap = round(look.item_gap - statistics.median(steps), 2)
        rows, firsts, spaces = [], [], []
        for n in range(len(section.items)):
            fields = [dy(f"{sid}.{n}.{name}") for name in ("title", "place", "dates", "tag")]
            fields = [f for f in fields if f is not None]
            if len(fields) >= 2:
                rows.append(max(fields) - min(fields))
            head = (
                dy(f"{sid}.{n}.title") if dy(f"{sid}.{n}.title") is not None else dy(f"{sid}.{n}")
            )
            bullets = [dy(f"{sid}.{n}.b{k}") for k in range(12)]
            bullets = [b for b in bullets if b is not None]
            if bullets:
                last_row = max([f for f in fields] or [head or 0.0])
                firsts.append(bullets[0] - last_row)
                spaces += [b - a for a, b in zip(bullets, bullets[1:], strict=False)]
        if rows and look.rows and len(look.rows) > 1:
            look.row_gap = round(look.row_gap - statistics.median(rows) / (len(look.rows) - 1), 2)
        if firsts:
            look.bullet_gap = round(look.bullet_gap - statistics.median(firsts), 2)
        if spaces:
            look.bullet_space = round(look.bullet_space - statistics.median(spaces), 2)


def _last_line(sid: str, n: int, want: dict[str, Anchor], got: dict[str, Anchor]) -> float | None:
    names = [k for k in want if k.startswith(f"{sid}.{n}.") and k in got]
    if not names:
        return None
    last = max(names, key=lambda k: want[k][0])
    return got[last][0] - want[last][0]


def clone_into(folder: Path, pdf: Path, content: CVContent, online: bool = True) -> CompileResult:
    """Écrit le clone dans ``folder`` (main.tex, cv.pdf, clone.json) et le compile, calé."""
    original = pages.read(pdf)
    layout = inference.infer(original, content, online)
    want = anchors(original, content)
    best: tuple[int, CloneLayout, CompileResult] | None = None
    for _ in range(ROUNDS + 1):
        result = compile_tex(write(folder, layout, content))
        if not result.ok:
            break
        score = likeness.measure(pdf, folder / PDF).score
        if best is None or score > best[0]:
            best = (score, layout.model_copy(deep=True), result)
        got = anchors(pages.read(folder / PDF), content)
        calibrate(layout, content, want, got)
    if best is None:
        return result
    _, layout, _ = best
    (folder / "clone.json").write_text(layout.model_dump_json(indent=1), encoding="utf-8")
    return compile_tex(write(folder, layout, content))
