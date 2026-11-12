"""Le contrôle du clone, mot à mot : ce qui manque, ce qui a bougé, ce qui a changé de style.

Les deux PDF sont lus de la même façon (``reading``) ; chaque mot de l'original cherche
son jumeau dans le clone (même texte, le plus proche). Une ligne est « à sa place » quand
tous ses mots sont à moins de ``TOLERANCE`` points de leur place d'origine.
"""

import math
from dataclasses import dataclass, field
from pathlib import Path

from app.services.clone.reading import Page, read
from app.services.clone.structure import key

TOLERANCE = 1.0


@dataclass
class Differences:
    words: int = 0
    found: int = 0
    lines: int = 0
    lines_in_place: int = 0
    max_shift: float = 0.0
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    moved: list[tuple[str, float]] = field(default_factory=list)
    restyled: list[tuple[str, str]] = field(default_factory=list)
    overlaps: list[tuple[str, str]] = field(default_factory=list)
    overflow: list[str] = field(default_factory=list)

    @property
    def in_place(self) -> float:
        return self.lines_in_place / self.lines if self.lines else 1.0


def _close(a: str, b: str) -> bool:
    """Deux couleurs presque égales (à 24 près sur chaque composante)."""
    try:
        return all(abs(int(a[i : i + 2], 16) - int(b[i : i + 2], 16)) <= 24 for i in (0, 2, 4))
    except ValueError:
        return a == b


def compare(original: list[Page], clone_pdf: Path, tolerance: float = TOLERANCE) -> Differences:
    clone = read(clone_pdf)
    out = Differences()
    for number, page in enumerate(original, 1):
        theirs = clone[number - 1] if number - 1 < len(clone) else None
        pool: dict[str, list] = {}
        if theirs is not None:
            for line in theirs.lines:
                for w in line.words:
                    if key(w.text):
                        pool.setdefault(key(w.text), []).append(w)
        for line in page.lines:
            words = [w for w in line.words if key(w.text)]
            if not words:
                continue
            out.lines += 1
            line_ok = True
            for w in words:
                out.words += 1
                candidates = pool.get(key(w.text), [])
                if not candidates:
                    out.missing.append(w.text)
                    line_ok = False
                    continue
                best = min(
                    candidates, key=lambda c: math.dist((c.x0, c.baseline), (w.x0, w.baseline))
                )
                candidates.remove(best)
                out.found += 1
                shift = math.dist((best.x0, best.baseline), (w.x0, w.baseline))
                out.max_shift = max(out.max_shift, shift)
                if shift > tolerance:
                    out.moved.append((w.text, round(shift, 1)))
                    line_ok = False
                changes = []
                if best.bold != w.bold:
                    changes.append("gras" if w.bold else "plus en gras")
                if best.italic != w.italic:
                    changes.append("italique" if w.italic else "plus en italique")
                if not _close(best.color, w.color):
                    changes.append("couleur")
                if abs(best.size - w.size) > 0.35:
                    changes.append("taille")
                if changes:
                    out.restyled.append((w.text, ", ".join(changes)))
            if line_ok:
                out.lines_in_place += 1
        out.extra += [w.text for words in pool.values() for w in words]
        if theirs is not None:
            out.overlaps += _overlaps(theirs)
            out.overflow += [
                w.text
                for line in theirs.lines
                for w in line.words
                if w.x1 > theirs.width + 0.5 or w.bottom > theirs.height + 0.5 or w.x0 < -0.5
            ]
    return out


def _overlaps(page: Page) -> list[tuple[str, str]]:
    """Deux mots de lignes différentes qui se recouvrent (du texte sur du texte)."""
    words = [(n, w) for n, line in enumerate(page.lines) for w in line.words if key(w.text)]
    found = []
    words.sort(key=lambda item: item[1].top)
    for i, (n, a) in enumerate(words):
        for m, b in words[i + 1 :]:
            if b.top >= a.bottom:
                break
            if m == n:
                continue
            dx = min(a.x1, b.x1) - max(a.x0, b.x0)
            # La hauteur des lettres seulement (la boîte d'une police déborde un peu).
            top_a, top_b = a.baseline - 0.7 * a.size, b.baseline - 0.7 * b.size
            dy = min(a.baseline, b.baseline) - max(top_a, top_b)
            if dx > 0.5 and dy > 0.5:
                found.append((a.text, b.text))
    return found


def phrases(d: Differences, scanned: bool = False) -> list[str]:
    """Ce qui n'est pas identique, en phrases courtes (vide : rien à signaler)."""
    out = []
    if d.missing:
        sample = ", ".join(f"« {w} »" for w in d.missing[:4])
        out.append(f"{len(d.missing)} mot(s) de ton PDF absent(s) du clone : {sample}")
    if d.moved and not scanned:
        out.append(
            f"{len(d.moved)} mot(s) décalé(s) de plus de {TOLERANCE:g} pt "
            f"(au plus {d.max_shift:.1f} pt)"
        )
    if d.restyled:
        kinds = sorted({k for _, change in d.restyled for k in change.split(", ")})
        out.append(f"{len(d.restyled)} mot(s) au style différent ({', '.join(kinds)})")
    if d.overlaps:
        out.append(f"{len(d.overlaps)} chevauchement(s) de texte")
    if d.overflow:
        out.append(f"{len(d.overflow)} mot(s) hors de la page")
    return out
