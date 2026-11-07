"""Garde-fous du dépôt public : aucune donnée personnelle dans les fichiers suivis.

Les données de l'utilisateur vivent dans ``data/`` (ignoré) ; le dépôt ne contient
que le CV fictif de ``demo/``.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.paths import BASE_FILES, ROOT, ensure_base

# Un numéro français ; seul celui du CV fictif est permis.
PHONE = re.compile(r"(?<!\d)(?:\+33\s?|0)[1-9](?:[ .-]?\d{2}){4}(?!\d)")
ALLOWED_PHONE = re.compile(r"(?:\+33\s?|0)[1-9](?:[ .-]?00){4}")
EMAIL = re.compile(r"[\w.+-]+@([\w-]+\.)+[a-z]{2,}", re.IGNORECASE)
ALLOWED_EMAIL_DOMAINS = ("example.com", "example.org", "users.noreply.github.com")
# Termes interdits propres à cette machine (noms, coordonnées…), un par ligne.
# Le fichier est hors du dépôt : ce test ne tourne que là où il existe.
PRIVATE_TERMS = ROOT / "local" / "termes-interdits.txt"
IMAGES = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def tracked() -> list[Path]:
    """Les fichiers suivis, et ceux qui le seraient au prochain commit."""
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("pas de dépôt Git")
    command = ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    out = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / name for name in out.split("\0") if name]


def texts() -> list[tuple[Path, str]]:
    found = []
    for path in tracked():
        if path.suffix.lower() in IMAGES or "fonts" in path.relative_to(ROOT).parts:
            continue
        try:
            found.append((path, path.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, FileNotFoundError):
            continue
    return found


def test_no_personal_data_dir_is_tracked() -> None:
    for path in tracked():
        assert path.relative_to(ROOT).parts[0] not in ("data", "local", ".env"), path


def test_no_real_phone_number() -> None:
    for path, text in texts():
        for match in PHONE.finditer(text):
            assert ALLOWED_PHONE.fullmatch(match.group()), f"{path}: {match.group()}"


def test_no_real_email() -> None:
    for path, text in texts():
        for match in EMAIL.finditer(text):
            domain = match.group().split("@", 1)[1].lower()
            assert domain.endswith(ALLOWED_EMAIL_DOMAINS), f"{path}: {match.group()}"


def test_no_private_term() -> None:
    if not PRIVATE_TERMS.exists():
        pytest.skip("pas de liste locale de termes interdits")
    terms = [
        line.strip().lower()
        for line in PRIVATE_TERMS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    for path, text in texts():
        lower = text.lower()
        assert not [term for term in terms if term in lower], path


def test_only_the_demo_photo_is_tracked() -> None:
    photos = [
        path.relative_to(ROOT).as_posix()
        for path in tracked()
        if path.suffix.lower() in IMAGES and "fonts" not in path.relative_to(ROOT).parts
    ]
    # assets/ : l'icône de l'appli (raccourci du bureau), jamais une photo.
    allowed = ("demo/", "frontend/public/", "docs/", "assets/")
    assert [p for p in photos if not p.startswith(allowed)] == []


def test_first_launch_copies_the_demo(tmp_path: Path) -> None:
    base = tmp_path / "base"
    assert ensure_base(base) is True
    assert sorted(p.name for p in base.iterdir()) == sorted(BASE_FILES)
    # Une version classique existante n'est jamais écrasée.
    (base / "content.json").write_text("{}", encoding="utf-8")
    assert ensure_base(base) is False
    assert (base / "content.json").read_text(encoding="utf-8") == "{}"
