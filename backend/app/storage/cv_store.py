"""Lecture et écriture des dossiers de CV.

La version classique vit dans ``base/`` (identifiant ``base``), chaque CV
ciblé dans ``cvs/<identifiant>/``. Un dossier contient content.json,
style.json et meta.json ; main.tex et cv.pdf en sont tirés à chaque
compilation.
"""

import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path
from typing import Literal

from app.latex.render import render
from app.models.content import CVContent
from app.models.meta import CVMeta, now
from app.models.style import CVStyle
from app.paths import BASE_DIR, CVS_DIR, TRASH_DIR
from app.text import slugify

CONTENT = "content.json"
STYLE = "style.json"
META = "meta.json"
TEX = "main.tex"
PDF = "cv.pdf"
THUMB = "miniature.png"
# Ce que laissaient les CV clonés (le clone est retiré) : effacé au premier passage.
_OLD_CLONE = ("clone.json", "clone-images", "main.pos")
BASE_SLUG = "base"

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")


class UnknownCV(LookupError):
    pass


def folder(slug: str) -> Path:
    """Le dossier d'un CV. L'identifiant est vérifié : jamais de chemin libre."""
    if slug == BASE_SLUG:
        return Path(BASE_DIR)
    if not _SLUG.match(slug):
        raise UnknownCV(slug)
    path = CVS_DIR / slug
    if not (path / CONTENT).exists():
        raise UnknownCV(slug)
    return path


def load(path: Path) -> tuple[CVContent, CVStyle]:
    content = CVContent.model_validate_json((path / CONTENT).read_text(encoding="utf-8"))
    style = CVStyle.model_validate_json((path / STYLE).read_text(encoding="utf-8"))
    return content, style


def load_meta(path: Path) -> CVMeta:
    file = path / META
    if file.exists():
        return CVMeta.model_validate_json(file.read_text(encoding="utf-8"))
    return CVMeta(name=path.name, kind="base" if path == BASE_DIR else "cv")


def _write_json(path: Path, data: dict) -> None:
    # Écriture atomique : un fichier à moitié écrit ne doit jamais remplacer le bon.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def save(path: Path, content: CVContent, style: CVStyle) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _write_json(path / CONTENT, content.model_dump(mode="json", exclude_none=True))
    _write_json(path / STYLE, style.model_dump(mode="json"))


def save_content(path: Path, content: CVContent) -> None:
    _write_json(path / CONTENT, content.model_dump(mode="json", exclude_none=True))
    touch(path)


def save_style(path: Path, style: CVStyle) -> None:
    _write_json(path / STYLE, style.model_dump(mode="json"))
    touch(path)


def save_meta(path: Path, meta: CVMeta) -> None:
    _write_json(path / META, meta.model_dump(mode="json"))


def touch(path: Path, **changes: object) -> CVMeta:
    """Met à jour la date de modification (et d'autres champs) du CV."""
    meta = load_meta(path).model_copy(update={"updated_at": now(), **changes})
    save_meta(path, meta)
    return meta


def forget_clone(path: Path) -> None:
    """Retire ce qu'un ancien clone a laissé dans le dossier du CV."""
    for name in _OLD_CLONE:
        target = path / name
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        else:
            target.unlink(missing_ok=True)


def generated(path: Path) -> str:
    """Le .tex tiré du contenu et du style."""
    content, style = load(path)
    return render(content, style)


def write_tex(path: Path) -> Path:
    """Régénère main.tex depuis content.json et style.json."""
    tex = path / TEX
    tex.write_text(generated(path), encoding="utf-8")
    return tex


def list_all() -> list[tuple[str, CVMeta]]:
    """La version classique puis les CV ciblés, du plus récent au plus ancien."""
    found = [(BASE_SLUG, load_meta(BASE_DIR))]
    if CVS_DIR.is_dir():
        others = [
            (child.name, load_meta(child))
            for child in CVS_DIR.iterdir()
            if child.is_dir() and _SLUG.match(child.name) and (child / CONTENT).exists()
        ]
        found += sorted(others, key=lambda item: item[1].updated_at, reverse=True)
    return found


def bases() -> list[str]:
    """Les CV classiques : la première version (``base``), puis les autres, par nom."""
    others = [(slug, meta.name) for slug, meta in list_all()[1:] if meta.kind == "base"]
    return [BASE_SLUG] + [slug for slug, _ in sorted(others, key=lambda item: item[1].lower())]


def new_folder(name: str) -> tuple[str, Path]:
    """Un dossier vide pour un nouveau CV, à un identifiant libre tiré de son nom."""
    CVS_DIR.mkdir(parents=True, exist_ok=True)
    base = slugify(name, "cv")
    slug, n = base, 2
    while slug == BASE_SLUG or (CVS_DIR / slug).exists():
        slug, n = f"{base}-{n}", n + 1
    target = CVS_DIR / slug
    target.mkdir()
    return slug, target


def create(name: str, source: str, kind: Literal["base", "cv"] = "cv") -> str:
    """Un nouveau CV, copie de ``source`` (contenu, style, photo) ; rend son identifiant.

    ``kind="base"`` : un CV classique de plus, toujours en mode visuel.
    """
    origin = folder(source)
    content, style = load(origin)
    slug, target = new_folder(name)
    save(target, content, style)
    photo = content.header.photo
    if photo and (origin / photo).is_file():
        shutil.copy2(origin / photo, target / photo)
    # Une copie d'un CV en mode manuel garde son code LaTeX, et son mode (sauf un CV classique).
    manual = load_meta(origin).mode == "manual" and kind == "cv"
    if manual:
        shutil.copy2(origin / TEX, target / TEX)
    save_meta(
        target,
        CVMeta(
            name=name.strip(),
            kind=kind,
            source=source,
            mode="manual" if manual else "visual",
        ),
    )
    return slug


def rename(slug: str, name: str, label: str | None = None, set_label: bool = False) -> CVMeta:
    changes: dict[str, object] = {"name": name.strip()}
    if set_label:
        changes["label"] = short_label(label or "") or None
    return touch(folder(slug), **changes)


# ─── Nom du fichier téléchargé : prenom_nom-de-famille_offre ─────────────────

# Mots qui ne disent rien du poste : ils ne vont pas dans le nom du fichier.
_STOP = set(
    "stage stages stagiaire internship intern ingenieur ingenieure engineer h f hf fh m w x "
    "de du des la le les l d et en pour par a au aux un une avec sur dans the of for and in to "
    "with pfe fin etudes cdi cdd alternance alternant apprenti master m2 junior senior".split()
)


def _words(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]+", plain)


def short_label(text: str, limit: int = 3) -> str:
    """1 à 3 mots tirés d'un texte : « Agent IA analyste de la… » → « agent-ia-analyste »."""
    return "-".join([w for w in _words(text) if w not in _STOP and not w.isdigit()][:limit])


def unique_label(label: str, company: str, taken: set[str]) -> str:
    """Des mots d'offre qu'aucun autre CV n'utilise : l'entreprise en plus, sinon un numéro."""
    if label not in taken:
        return label
    with_company = "-".join(filter(None, [short_label(company, 1), label]))
    if with_company not in taken:
        return with_company
    n = 2
    while f"{label}-{n}" in taken:
        n += 1
    return f"{label}-{n}"


def labels_in_use() -> set[str]:
    """Les mots d'offre des CV existants (pour qu'un nouveau CV ait un nom de fichier à lui)."""
    used = set()
    for slug, meta in list_all():
        label = offer_label(folder(slug), meta)
        if label:
            used.add(label)
    return used


def person_stem(name: str) -> str:
    """« CAMILLE LAURENT DUPONT » → « camille_laurent-dupont » (prénom, puis nom de famille)."""
    words = _words(name)
    if not words:
        return "cv"
    return words[0] + ("_" + "-".join(words[1:]) if len(words) > 1 else "")


def offer_label(path: Path, meta: CVMeta) -> str:
    """Les mots de l'offre : choisis à la main, sinon ceux de l'analyse, sinon l'intitulé."""
    if meta.label:
        return short_label(meta.label)
    file = path / "analysis.json"
    if not file.exists():
        return ""
    try:
        analysis = json.loads(file.read_text(encoding="utf-8")).get("analysis", {})
    except ValueError:
        return ""
    return short_label(analysis.get("short_name") or "") or short_label(
        analysis.get("job_title") or ""
    )


def offer_facts(path: Path) -> dict[str, str]:
    """Le lieu et le contrat de l'offre visée, tirés de son analyse."""
    file = path / "analysis.json"
    if not file.exists():
        return {}
    try:
        analysis = json.loads(file.read_text(encoding="utf-8")).get("analysis", {})
    except ValueError:
        return {}
    return {key: str(analysis.get(key) or "").strip() for key in ("location", "contract")}


def letter_file_stem(path: Path) -> str:
    """Le nom du fichier de la lettre : « camille_laurent_lettre_agent-ia-analyste »."""
    content, _ = load(path)
    label = offer_label(path, load_meta(path))
    return person_stem(content.header.name) + "_lettre" + (f"_{label}" if label else "")


def file_stem(path: Path) -> str:
    """Le nom du fichier téléchargé, sans extension : « camille_laurent_agent-ia »."""
    content, _ = load(path)
    label = offer_label(path, load_meta(path))
    return person_stem(content.header.name) + (f"_{label}" if label else "")


def delete(slug: str) -> Path:
    """Met le CV à la corbeille (corbeille/, hors du dépôt) ; rend son nouvel emplacement.

    Le dernier CV classique ne se supprime pas. Supprimer la première version (``base``)
    met à sa place le CV classique modifié le plus récemment : ``base`` existe toujours.
    """
    path = folder(slug)
    others = [s for s in bases() if s != slug]
    if load_meta(path).kind == "base" and not others:
        raise ValueError("C'est ton seul CV classique : il ne se supprime pas.")
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now().strftime("%Y%m%d-%H%M%S")
    target = TRASH_DIR / f"{slug}-{stamp}"
    if slug != BASE_SLUG:
        shutil.move(str(path), target)
        return target
    heir = max(others, key=lambda s: load_meta(folder(s)).updated_at)
    heir_path = folder(heir)
    shutil.move(str(path), target)
    shutil.move(str(heir_path), str(Path(BASE_DIR)))
    # Les CV ciblés faits à partir de lui suivent son nouvel identifiant.
    for other, meta in list_all()[1:]:
        if meta.source == heir:
            save_meta(folder(other), meta.model_copy(update={"source": BASE_SLUG}))
    return target


def thumbnail(slug: str) -> Path | None:
    """La miniature PNG du PDF, refaite quand le PDF a changé."""
    path = folder(slug)
    pdf, thumb = path / PDF, path / THUMB
    if not pdf.exists():
        return None
    if not thumb.exists() or thumb.stat().st_mtime < pdf.stat().st_mtime:
        subprocess.run(
            [
                "pdftoppm",
                "-png",
                "-r",
                "40",
                "-f",
                "1",
                "-l",
                "1",
                "-singlefile",
                str(pdf),
                str(thumb.with_suffix("")),
            ],
            check=True,
            timeout=30,
        )
    return thumb
