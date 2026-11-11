"""L'image de signature : fond retiré, recadrée, en bas de chaque lettre (ou pas)."""

import io
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app import paths
from app.services import signature
from app.storage import letter_store
from tests.conftest import needs_latex
from tests.test_letter import cv  # noqa: F401


def _photo(background: tuple[int, int, int] = (238, 236, 230)) -> bytes:
    """Une « photo » de signature : papier gris clair, trait bleu foncé au milieu."""
    image = Image.new("RGB", (800, 500), background)
    draw = ImageDraw.Draw(image)
    draw.line([(250, 300), (350, 200), (450, 320), (560, 210)], fill=(20, 30, 90), width=9)
    out = io.BytesIO()
    image.save(out, "JPEG", quality=92)
    return out.getvalue()


@pytest.fixture(autouse=True)
def own_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Jamais le vrai dossier data/ : la signature vit à la racine des données.
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "donnees")


def test_paper_becomes_transparent_and_image_is_cropped() -> None:
    image = signature.process(_photo())
    assert image.mode == "RGBA"
    # Recadrée au trait : bien plus petite que la photo, et plus large que haute.
    assert image.width < 400 and image.height < 160 and image.width > image.height
    alpha = image.getchannel("A")
    assert alpha.getpixel((0, 0)) == 0
    assert alpha.getextrema()[1] == 255


def test_transparent_png_is_kept() -> None:
    image = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((100, 80, 200, 120), fill=(0, 0, 0, 255))
    out = io.BytesIO()
    image.save(out, "PNG")
    found = signature.process(out.getvalue())
    assert found.size[0] < 120 and found.getchannel("A").getpixel((0, 0)) == 0


def test_bad_images_are_refused() -> None:
    with pytest.raises(signature.BadImage):
        signature.process(b"pas une image")
    blank = io.BytesIO()
    Image.new("RGB", (200, 100), "white").save(blank, "PNG")
    with pytest.raises(signature.BadImage, match="Aucun trait"):
        signature.process(blank.getvalue())


def test_api(client: TestClient) -> None:
    assert client.get("/api/signature").json() == {
        "present": False,
        "size": "medium",
        "version": None,
    }
    assert client.get("/api/signature/image").status_code == 404
    out = client.put("/api/signature", files={"file": ("sig.jpg", _photo(), "image/jpeg")})
    assert out.status_code == 200 and out.json()["present"] is True
    image = client.get("/api/signature/image")
    assert image.headers["content-type"] == "image/png" and image.content[:4] == b"\x89PNG"
    assert client.patch("/api/signature", json={"size": "large"}).json()["size"] == "large"
    assert client.patch("/api/signature", json={"size": "huge"}).status_code == 422
    bad = client.put("/api/signature", files={"file": ("x.png", b"rien", "image/png")})
    assert bad.status_code == 422
    assert client.delete("/api/signature").json()["present"] is False


@needs_latex
def test_letter_shows_the_signature_under_the_name(
    client: TestClient,
    cv: dict[str, Any],  # noqa: F811
) -> None:
    slug, folder = cv["slug"], cv["folder"]
    client.post(f"/api/cvs/{slug}/letter/generate", json={})
    client.put("/api/signature", files={"file": ("sig.jpg", _photo(), "image/jpeg")})
    client.patch("/api/signature", json={"size": "small"})
    assert client.post(f"/api/cvs/{slug}/letter/compile").json()["ok"]
    tex = (folder / letter_store.TEX).read_text()
    assert r"\includegraphics[height=1.2cm]{signature.png}" in tex
    assert tex.index("Camille Laurent") < tex.index("includegraphics")
    assert (folder / "signature.png").is_file()
    images = subprocess.run(
        ["pdfimages", "-list", folder / letter_store.PDF], capture_output=True, text=True
    ).stdout
    assert "smask" in images  # l'image et sa transparence sont dans le PDF

    # Décochée pour cette lettre : plus d'image, et la copie disparaît.
    letter = client.get(f"/api/cvs/{slug}/letter").json()["letter"]
    letter["signature_image"] = False
    client.put(f"/api/cvs/{slug}/letter", json=letter)
    assert client.post(f"/api/cvs/{slug}/letter/compile").json()["ok"]
    assert "includegraphics" not in (folder / letter_store.TEX).read_text()
    assert not (folder / "signature.png").exists()
