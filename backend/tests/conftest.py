import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import settings
from app.main import app
from app.models.content import CVContent
from app.models.style import CVStyle
from app.paths import BASE_FILES, DEMO_DIR
from app.storage import cv_store

needs_latex = pytest.mark.skipif(
    shutil.which("xelatex") is None or shutil.which("latexmk") is None,
    reason="xelatex ou latexmk absent (sudo apt install texlive-xetex latexmk)",
)


@pytest.fixture
def base_content() -> CVContent:
    return CVContent.model_validate_json((DEMO_DIR / "content.json").read_text(encoding="utf-8"))


@pytest.fixture
def base_style() -> CVStyle:
    return CVStyle.model_validate_json((DEMO_DIR / "style.json").read_text(encoding="utf-8"))


@pytest.fixture
def cv_folder(tmp_path: Path, base_content: CVContent, base_style: CVStyle) -> Path:
    """Un dossier de CV jetable, copie du CV fictif."""
    from app.storage.cv_store import save

    folder = tmp_path / "cv"
    save(folder, base_content, base_style)
    shutil.copy(DEMO_DIR / "imgcv.jpg", folder / "imgcv.jpg")
    return folder


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """L'API sur une copie du CV fictif : les tests ne touchent jamais à data/."""
    base = tmp_path / "base"
    base.mkdir()
    for name in BASE_FILES:
        shutil.copy(DEMO_DIR / name, base / name)
    monkeypatch.setattr(cv_store, "BASE_DIR", base)
    monkeypatch.setattr(cv_store, "CVS_DIR", tmp_path / "cvs")
    # Jamais le vrai .env ni l'état de cette machine.
    monkeypatch.setattr(settings, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(settings, "SETUP_FILE", tmp_path / "local" / "setup.json")
    for name in settings.KEYS.values():
        monkeypatch.delenv(name, raising=False)
    return TestClient(app)
