"""Ce que lit un logiciel de tri (ATS) : le texte extrait du PDF, vérifié.

Un ATS ne voit pas la mise en page, seulement le texte que donne le PDF. On
l'extrait comme lui (``pdftotext``, ordre de lecture) et on vérifie :

- qu'il y a bien du texte, et une seule page ;
- que les polices sont intégrées avec leur table Unicode (sinon les lettres
  extraites peuvent être n'importe quoi) ;
- qu'il n'y a ni ligatures (« ﬁ » en un caractère), ni caractères illisibles ;
- que chaque mot du CV se retrouve dans le texte extrait ;
- que le contenu de chaque rubrique suit bien son titre dans l'ordre de lecture
  (deux colonnes peuvent se lire entremêlées) ;
- que l'adresse électronique et le téléphone se lisent tels quels.
"""

import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.models.content import CVContent

Status = Literal["ok", "warn", "fail"]
LIGATURES = "ﬀﬁﬂﬃﬄﬅﬆ"
# Tirets et espaces exotiques, remplacement, zone privée : un ATS peut les rater.
_ODD = re.compile(r"[‐‑­�-]|\(cid:\d+\)")


class Check(BaseModel):
    id: str
    label: str
    status: Status
    detail: str


class Words(BaseModel):
    total: int
    found: int
    missing: list[str]


class AtsReport(BaseModel):
    checks: list[Check]
    words: Words
    text: str


def pdf_text(pdf: Path) -> str:
    """Le texte du PDF dans l'ordre de lecture, comme un ATS le reçoit."""
    try:
        run = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", str(pdf), "-"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    # Un mot coupé en fin de ligne (« Ma-\nchine ») est recollé.
    return re.sub(r"(\w)-\n(\w)", r"\1\2", run.stdout)


def _fonts(pdf: Path) -> list[dict[str, str]]:
    try:
        run = subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return []
    fonts = []
    for line in run.stdout.splitlines()[2:]:
        parts = line.split()
        if len(parts) >= 7:
            # Les deux dernières colonnes sont le numéro d'objet ; avant : emb, sub, uni.
            fonts.append({"name": parts[0], "emb": parts[-5], "uni": parts[-3]})
    return fonts


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("’", "'").replace("‘", "'")
    return re.sub(r"\*\*|__", "", text).lower()


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"\w+", _plain(text)) if len(t) > 1]


def content_texts(content: CVContent) -> list[str]:
    """Tout le texte visible du CV, tel qu'écrit dans content.json."""
    out = [content.header.name, content.header.headline, content.header.summary]
    for line in content.header.contact_lines:
        for item in line:
            out += [item.label or "", item.text]
    for section in content.sections:
        if not section.visible:
            continue
        out.append(section.title)
        for item in section.items:
            if isinstance(item, str):
                out.append(item)
            else:
                out += [
                    str(v)
                    for k, v in item.model_dump().items()
                    if k not in ("link", "library_id", "wide") and isinstance(v, str)
                ]
                out += getattr(item, "bullets", [])
    return [t for t in out if t]


def _first_words(section: object) -> str:
    items = getattr(section, "items", [])
    if not items:
        return ""
    first = items[0]
    text = (
        first
        if isinstance(first, str)
        else (
            getattr(first, "title", "")
            or getattr(first, "label", "")
            or getattr(first, "name", "")
            or getattr(first, "text", "")
        )
    )
    return " ".join(_tokens(text)[:3])


def _line_index(lines: list[str], needle: str, start: int = 0) -> int | None:
    for i in range(start, len(lines)):
        if needle and needle in lines[i]:
            return i
    return None


def reading_order(content: CVContent, text: str) -> tuple[list[str], list[str]]:
    """(rubriques bien lues, rubriques dont le contenu suit le titre d'une autre)."""
    lines = [" ".join(_tokens(line)) for line in text.splitlines()]
    sections = [s for s in content.sections if s.visible and s.items]
    titles = {s.id: " ".join(_tokens(s.title)) for s in sections}
    where = {sid: _line_index(lines, t) for sid, t in titles.items()}
    good, mixed = [], []
    for section in sections:
        start = where[section.id]
        probe = _first_words(section)
        found = _line_index(lines, probe, (start or 0) + 1) if start is not None else None
        if start is None or found is None:
            mixed.append(section.title)
            continue
        between = [
            sid
            for sid, i in where.items()
            if sid != section.id and i is not None and start < i < found
        ]
        (mixed if between else good).append(section.title)
    return good, mixed


def analyze(pdf: Path, content: CVContent, pages: int | None) -> AtsReport:
    text = pdf_text(pdf)
    checks: list[Check] = []
    words_in_pdf = set(_tokens(text))
    count = len(_tokens(text))

    checks.append(
        Check(
            id="text", label="Texte lisible", status="ok", detail=f"{count} mots extraits du PDF."
        )
        if count >= 150
        else Check(
            id="text",
            label="Texte lisible",
            status="fail",
            detail="Le PDF ne donne presque pas de texte : un ATS n'y lira rien.",
        )
    )
    checks.append(
        Check(id="pages", label="Une page", status="ok", detail="Le CV tient sur une page.")
        if pages == 1
        else Check(id="pages", label="Une page", status="warn", detail=f"Le CV fait {pages} pages.")
    )

    fonts = _fonts(pdf)
    bad = [f["name"].split("+")[-1] for f in fonts if f["emb"] != "yes" or f["uni"] != "yes"]
    checks.append(
        Check(
            id="fonts",
            label="Polices intégrées, avec table Unicode",
            status="ok" if fonts and not bad else "fail",
            detail=(
                f"{len(fonts)} polices, toutes intégrées avec leur table Unicode."
                if fonts and not bad
                else "Sans table Unicode ou non intégrées : "
                f"{', '.join(bad) or 'aucune police lue'}."
            ),
        )
    )

    ligatures = sorted({c for c in text if c in LIGATURES})
    checks.append(
        Check(
            id="ligatures",
            label="Pas de ligatures",
            status="fail" if ligatures else "ok",
            detail=(
                f"Ligatures trouvées : {' '.join(ligatures)} "
                "(un ATS peut ne pas reconnaître « fichiers »)."
                if ligatures
                else "« fi », « fl »… sont extraits en lettres séparées."
            ),
        )
    )

    odd = sorted({m.group(0) for m in _ODD.finditer(text)})
    checks.append(
        Check(
            id="chars",
            label="Caractères standard",
            status="warn" if odd else "ok",
            detail=(
                f"Caractères inhabituels : {' '.join(repr(c) for c in odd)}."
                if odd
                else "Tirets, apostrophes et espaces extraits normalement."
            ),
        )
    )

    expected = list(dict.fromkeys(t for chunk in content_texts(content) for t in _tokens(chunk)))
    missing = [t for t in expected if t not in words_in_pdf]
    found = len(expected) - len(missing)
    share = found / len(expected) if expected else 1
    checks.append(
        Check(
            id="words",
            label="Tous tes mots se retrouvent",
            status="ok" if share >= 0.98 else "warn" if share >= 0.9 else "fail",
            detail=f"{found} mots sur {len(expected)} retrouvés dans le texte extrait.",
        )
    )

    good, mixed = reading_order(content, text)
    checks.append(
        Check(
            id="order",
            label="Ordre de lecture",
            status="warn" if mixed else "ok",
            detail=(
                "Lues entremêlées avec une autre rubrique (deux colonnes) : "
                f"{', '.join(mixed)}. Les ATS récents s'en sortent en général ; un ancien peut "
                "rattacher ce contenu à la mauvaise rubrique."
                if mixed
                else "Le contenu de chaque rubrique suit son titre."
            ),
        )
    )

    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    phone = re.search(r"(?:\+33\s?|0)\d(?:[ .]?\d{2}){4}", text)
    contact_ok = bool(email and phone)
    checks.append(
        Check(
            id="contact",
            label="Coordonnées lisibles",
            status="ok" if contact_ok else "warn",
            detail=(
                f"Adresse électronique et téléphone lus : {email.group(0)}, {phone.group(0)}."
                if email and phone
                else "L'adresse électronique ou le téléphone ne se lit pas tel quel."
            ),
        )
    )
    return AtsReport(
        checks=checks,
        words=Words(total=len(expected), found=found, missing=missing[:40]),
        text=text,
    )
