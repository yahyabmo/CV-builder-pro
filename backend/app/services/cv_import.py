"""Un CV en PDF devient la version classique, sans rien réécrire.

1. ``read_pdf`` : le texte, déjà rangé par rubrique d'après la page (``clone.structure`` :
   colonnes, titres repérés à leur style), et la photo la plus grande (pdfimages).
2. L'IA range ce texte dans ``ImportedCV`` (prompts/import.md).
3. ``to_content`` : les rubriques de l'appli, sur le modèle du CV fictif ; puis
   ``clone.fill.complete`` corrige d'après la page (lignes oubliées, puces coupées, gras,
   liens).
4. ``checks`` : les mots absents du PDF, et ce qui serait resté sans rubrique.

Chaque import vit dans ``data/imports/<id>/`` : le PDF, son texte, sa photo et le
résultat de la lecture, pour reprendre la relecture après un rechargement.
"""

import json
import re
import secrets
import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel

from app.ai.schemas import ImportedContact, ImportedCV
from app.latex.compile import page_count
from app.models.content import (
    BulletsSection,
    ContactItem,
    CVContent,
    EducationItem,
    EducationSection,
    ExperienceItem,
    ExperienceSection,
    GridItem,
    GridSection,
    Header,
    Language,
    LanguagesSection,
    ProjectItem,
    ProjectsSection,
    SkillGroup,
    SkillsSection,
)
from app.paths import DEMO_DIR, IMPORTS_DIR
from app.services import ocr, photo
from app.services.clone import reading as clone_reading
from app.services.clone import scan as clone_scan
from app.services.clone import structure as clone_structure
from app.services.library_import import split_skills
from app.text import slugify

MAX_BYTES = 10 * 1024 * 1024
# En dessous, le PDF n'a pas de texte à lire : c'est un scan.
MIN_WORDS = 30
SOURCE = "source.pdf"
TEXT = "text.txt"
RESULT = "result.json"
# Une photo de CV : assez grande, à peu près carrée ou en portrait.
MIN_PHOTO_SIDE = 80

TITLES_EN = {
    "FORMATION": "EDUCATION",
    "COMPÉTENCES": "SKILLS",
    "SOFT SKILLS": "SOFT SKILLS",
    "LANGUES": "LANGUAGES",
    "CENTRES D'INTÉRÊT": "INTERESTS",
    "EXPÉRIENCE PROFESSIONNELLE": "PROFESSIONAL EXPERIENCE",
    "PROJETS": "PROJECTS",
    "TRAVAIL ASSOCIATIF": "VOLUNTEERING",
}


class UnreadablePdf(ValueError):
    """Un PDF que l'appli ne peut pas lire ; le message s'affiche tel quel."""


class UnknownImport(LookupError):
    pass


@dataclass
class Reading:
    id: str
    words: int
    pages: int | None
    photo: bool
    # Un scan lu par Tesseract : le texte est à relire de près.
    scanned: bool = False


class Check(BaseModel):
    kind: Literal["absent", "unplaced"]
    where: str
    text: str


def folder(import_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{12}", import_id) or not (IMPORTS_DIR / import_id).is_dir():
        raise UnknownImport(import_id)
    return IMPORTS_DIR / import_id


def pdf_text(pdf: Path) -> str:
    """Le texte du PDF, ligatures dépliées et mots coupés en fin de ligne recollés."""
    run = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", str(pdf), "-"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if run.returncode != 0:
        raise UnreadablePdf("Ce PDF ne s'ouvre pas : il est peut-être protégé ou abîmé.")
    text = unicodedata.normalize("NFKC", run.stdout)
    return re.sub(r"(\w)-\n(\w)", r"\1\2", text)


def _photo(pdf: Path, target: Path) -> bool:
    """Garde la plus grande image à peu près carrée ou en portrait : la photo du CV."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["pdfimages", "-png", str(pdf), f"{tmp}/image"],
            capture_output=True,
            timeout=30,
            check=False,
        )
        best: tuple[int, Path] | None = None
        for image in Path(tmp).glob("*.png"):
            try:
                with Image.open(image) as opened:
                    width, height = opened.size
            except (UnidentifiedImageError, OSError):
                continue
            if min(width, height) < MIN_PHOTO_SIDE or not 0.6 <= width / height <= 1.7:
                continue
            if best is None or width * height > best[0]:
                best = (width * height, image)
        if best is None:
            return False
        try:
            photo.store(target, best[1].read_bytes())
        except photo.BadImage:
            return False
    return True


def read_pdf(data: bytes) -> Reading:
    if not data.startswith(b"%PDF"):
        raise UnreadablePdf("Ce fichier n'est pas un PDF.")
    if len(data) > MAX_BYTES:
        raise UnreadablePdf("Ce PDF dépasse 10 Mo.")
    import_id = secrets.token_hex(6)
    target = IMPORTS_DIR / import_id
    target.mkdir(parents=True)
    source = target / SOURCE
    source.write_bytes(data)
    try:
        text = pdf_text(source)
    except UnreadablePdf:
        shutil.rmtree(target)
        raise
    words = len(re.findall(r"\w+", text))
    scanned = False
    if words < MIN_WORDS:
        # Presque pas de texte : un scan. Tesseract le lit, s'il est là.
        if not ocr.available():
            shutil.rmtree(target)
            raise UnreadablePdf(
                "Ce PDF est un scan (une image) : pour le lire, l'appli a besoin de Tesseract. "
                f"Installe-le avec : {ocr.INSTALL}. Sinon, exporte ton CV en PDF depuis ton "
                "traitement de texte, ou remplis-le à la main."
            )
        try:
            text = ocr.text(ocr.read(source, target))
        except (ocr.OcrError, subprocess.SubprocessError, OSError):
            shutil.rmtree(target)
            raise UnreadablePdf("Ce scan ne se lit pas : il est peut-être trop flou.") from None
        words = len(re.findall(r"\w+", text))
        scanned = True
        if words < MIN_WORDS:
            shutil.rmtree(target)
            raise UnreadablePdf(
                "Même lu comme un scan, ce PDF n'a presque pas de texte : il est peut-être trop "
                "flou ou trop petit. Remplis ton CV à la main, ou exporte-le en PDF."
            )
    # Le texte pour l'IA : rangé par rubrique d'après la page (à défaut, celui de pdftotext).
    try:
        found = clone_structure.analyse(_pages(target, scanned))
        structured = clone_structure.text(found)
        if len(re.findall(r"\w+", structured)) >= 0.8 * words:
            text = structured
    except Exception:  # noqa: BLE001 — une page illisible : le texte brut suffit
        pass
    (target / TEXT).write_text(text, encoding="utf-8")
    # Un scan est une seule grande image : ce n'est pas la photo du CV.
    has_photo = False if scanned else _photo(source, target)
    return Reading(import_id, words, page_count(source), has_photo, scanned)


def is_scanned(import_id: str) -> bool:
    return (folder(import_id) / ocr.OCR_FILE).is_file()


def _pages(target: Path, scanned: bool) -> list[clone_reading.Page]:
    if scanned:
        return clone_scan.pages(ocr.load(target) or [], target)
    return clone_reading.read(target / SOURCE)


def pages_of(import_id: str) -> list[clone_reading.Page]:
    """Les pages du PDF importé, lues au point près (ou par Tesseract pour un scan)."""
    return _pages(folder(import_id), is_scanned(import_id))


def text_of(import_id: str) -> str:
    return (folder(import_id) / TEXT).read_text(encoding="utf-8")


def has_photo(import_id: str) -> bool:
    return (folder(import_id) / photo.PHOTO).exists()


def is_demo_pdf(data: bytes) -> bool:
    return data == (DEMO_DIR / "cv-exemple.pdf").read_bytes()


# ─── Des rubriques lues aux sections de l'appli ──────────────────────────────


def _contacts(contacts: list[ImportedContact]) -> list[list[ContactItem]]:
    items = []
    for contact in contacts:
        text = contact.text.strip()
        if not text:
            continue
        url = contact.url.strip() or None
        if url is None and re.fullmatch(r"[^@\s]+@[^@\s]+\.\w+", text):
            url = f"mailto:{text}"
        label = contact.label.strip() or None
        items.append(ContactItem(text=text, label=label, url=url, bold=label is None))
    half = (len(items) + 1) // 2
    return [line for line in (items[:half], items[half:]) if line]


def _sentence(items: list[str]) -> str:
    """Les compétences d'un groupe, à la suite, telles qu'écrites (sans point ajouté)."""
    return ", ".join(item.strip() for item in items if item.strip())


def _experiences(items: list) -> list[ExperienceItem]:
    return [
        ExperienceItem(
            title=e.title, tag=e.tag, place=e.place, dates=e.dates, bullets=[b for b in e.bullets]
        )
        for e in items
    ]


# Le genre et la mise en page d'une section du CV fictif → sa rubrique dans la lecture.
_RUBRICS = {
    ("education", None): "education",
    ("experience", "detailed"): "experience",
    ("experience", "compact"): "associative",
    ("projects", None): "projects",
    ("skills", None): "skills",
    ("grid", None): "soft_skills",
    ("languages", None): "languages",
    ("bullets", None): "interests",
}


def to_content(cv: ImportedCV, with_photo: bool, template: CVContent | None = None) -> CVContent:
    """Le CV lu, rangé dans les sections du CV fictif ; une section vide est masquée."""
    if template is None:
        raw = (DEMO_DIR / "content.json").read_text(encoding="utf-8")
        template = CVContent.model_validate_json(raw)
    sections = []
    for model in template.sections:
        section = model.model_copy(deep=True)
        if isinstance(section, EducationSection):
            section.items = [
                EducationItem(
                    title=e.title, place=e.place, dates=e.dates, description=e.description
                )
                for e in cv.education
            ]
        elif isinstance(section, SkillsSection):
            section.items = [
                SkillGroup(label=g.label, text=_sentence(g.items)) for g in cv.skills if g.items
            ]
        elif isinstance(section, GridSection):
            section.items = [GridItem(text=s, wide=len(s) > 22) for s in cv.soft_skills]
        elif isinstance(section, LanguagesSection):
            section.items = [Language(name=lang.name, level=lang.level) for lang in cv.languages]
        elif isinstance(section, BulletsSection):
            section.items = list(cv.interests)
        elif isinstance(section, ExperienceSection):
            source = cv.associative if section.layout == "compact" else cv.experience
            section.items = _experiences(source)
        elif isinstance(section, ProjectsSection):
            section.items = [
                ProjectItem(
                    title=p.title,
                    tag=p.tag,
                    date=p.date,
                    description=p.description,
                    bullets=[b for b in p.bullets if b.strip()],
                    link=p.link.strip() or None,
                )
                for p in cv.projects
            ]
        section.visible = bool(section.items)
        if cv.language == "en":
            section.title = TITLES_EN.get(section.title, section.title)
        # Le titre écrit dans le PDF, s'il a été lu : la rubrique garde son nom.
        rubric = _RUBRICS.get((section.kind, getattr(section, "layout", None)))
        written = next((t.title.strip() for t in cv.titles if t.rubric == rubric), "")
        if written:
            section.title = written
        sections.append(section)
    # Les rubriques que l'appli n'a pas (Certifications, Prix…) : une liste chacune.
    taken = {s.id for s in sections}
    for other in cv.others:
        lines = [line.strip() for line in other.lines if line.strip()]
        if not other.title.strip() or not lines:
            continue
        base = slugify(other.title, "rubrique")
        sid, n = base, 2
        while sid in taken:
            sid, n = f"{base}-{n}", n + 1
        taken.add(sid)
        sections.append(
            BulletsSection(id=sid, title=other.title.strip(), column="right", items=lines)
        )
    header = Header(
        name=cv.name,
        headline=cv.headline,
        summary=cv.summary,
        photo=photo.PHOTO if with_photo else "",
        contact_lines=_contacts(cv.contacts),
    )
    return CVContent(language=cv.language, header=header, sections=sections)


# ─── Ce qu'il faut relire ────────────────────────────────────────────────────


def _fold(word: str) -> str:
    plain = unicodedata.normalize("NFKD", word.lower())
    return "".join(c for c in plain if not unicodedata.combining(c))


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"\w+", text) if len(w) >= 3]


def _fields(cv: ImportedCV) -> list[tuple[str, str]]:
    found = [("Identité", cv.name), ("Titre", cv.headline), ("Accroche", cv.summary)]
    found += [("Coordonnées", c.text) for c in cv.contacts]
    for n, e in enumerate(cv.education, 1):
        found.append((f"Formation {n}", f"{e.title} {e.place} {e.dates} {e.description}"))
    for label, items in (("Expérience", cv.experience), ("Engagement", cv.associative)):
        for n, e in enumerate(items, 1):
            found.append((f"{label} {n}", f"{e.title} {e.tag} {e.place} {e.dates}"))
            found += [(f"{label} {n}, puce {b}", text) for b, text in enumerate(e.bullets, 1)]
    for n, p in enumerate(cv.projects, 1):
        found.append((f"Projet {n}", f"{p.title} {p.tag} {p.date} {p.description}"))
        found += [(f"Projet {n}, puce {b}", text) for b, text in enumerate(p.bullets, 1)]
    found += [(f"Compétences : {g.label}", f"{g.label} {' '.join(g.items)}") for g in cv.skills]
    found += [("Soft skills", s) for s in cv.soft_skills]
    found += [("Langues", f"{lang.name} {lang.level}") for lang in cv.languages]
    found += [("Centres d'intérêt", i) for i in cv.interests]
    for other in cv.others:
        found += [(other.title, line) for line in other.lines]
    return found


def checks(cv: ImportedCV, source: str, left: list[str] | None = None) -> list[Check]:
    """Chaque mot rangé doit venir du PDF ; ce qui reste sans rubrique est signalé.

    ``left`` : les mots de la page qu'aucun champ n'écrit, après la correction d'après la
    page ; donné, il remplace les lignes que l'IA n'avait pas su ranger.
    """
    known = {_fold(w) for w in _words(source)}
    out = []
    for where, value in _fields(cv):
        missing = list(dict.fromkeys(w for w in _words(value) if _fold(w) not in known))
        if missing:
            words = ", ".join(f"« {w} »" for w in missing[:4])
            out.append(
                Check(
                    kind="absent",
                    where=where,
                    text=f"{words} n'apparaît pas dans ton PDF. Garde-le seulement s'il est vrai.",
                )
            )
    if left is not None:
        if left:
            sample = " ".join(left[:12]) + (" …" if len(left) > 12 else "")
            out.append(
                Check(
                    kind="unplaced",
                    where="Sans rubrique",
                    text=f"« {sample} » n'a trouvé aucune rubrique : ajoute-le à la main "
                    "s'il compte.",
                )
            )
        return out
    for line in cv.unplaced:
        if line.strip():
            out.append(
                Check(
                    kind="unplaced",
                    where="Sans rubrique",
                    text=f"« {line.strip()} » n'a trouvé aucune rubrique : ajoute-le à la main "
                    "s'il compte.",
                )
            )
    return out


def counts(content: CVContent) -> dict[str, int]:
    """Ce que la bibliothèque recevra : compétences, expériences, projets."""
    skills = experiences = projects = 0
    for section in content.sections:
        if isinstance(section, SkillsSection):
            skills += sum(len(split_skills(group.text)) for group in section.items)
        elif isinstance(section, ExperienceSection):
            experiences += len(section.items)
        elif isinstance(section, ProjectsSection):
            projects += len(section.items)
    return {"skills": skills, "experiences": experiences, "projects": projects}


def save_result(import_id: str, data: dict) -> None:
    (folder(import_id) / RESULT).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_result(import_id: str) -> dict | None:
    file = folder(import_id) / RESULT
    return json.loads(file.read_text(encoding="utf-8")) if file.exists() else None
