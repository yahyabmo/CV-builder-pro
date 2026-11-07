import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.storage import cv_store
from tests.conftest import needs_latex


def test_list_has_the_base(client: TestClient) -> None:
    [first] = client.get("/api/cvs").json()
    assert first["slug"] == "base"
    assert first["meta"]["kind"] == "base"


def test_get_and_put_content(client: TestClient) -> None:
    detail = client.get("/api/cvs/base").json()
    content = detail["content"]
    content["header"]["summary"] = "Nouvelle accroche & test"
    answer = client.put("/api/cvs/base/content", json=content)
    assert answer.status_code == 200
    assert client.get("/api/cvs/base").json()["content"]["header"]["summary"] == (
        "Nouvelle accroche & test"
    )


def test_invalid_content_is_refused(client: TestClient) -> None:
    content = client.get("/api/cvs/base").json()["content"]
    content["sections"][0]["kind"] = "inconnu"
    assert client.put("/api/cvs/base/content", json=content).status_code == 422


@pytest.mark.parametrize("slug", ["inconnu", "..", "a/b", "Base"])
def test_unknown_or_unsafe_slug(client: TestClient, slug: str) -> None:
    assert client.get(f"/api/cvs/{slug}").status_code == 404


def test_photo(client: TestClient) -> None:
    answer = client.get("/api/cvs/base/photo")
    assert answer.status_code == 200
    assert answer.headers["content-type"] == "image/jpeg"


@needs_latex
def test_compile_and_pdf(client: TestClient) -> None:
    result = client.post("/api/cvs/base/compile").json()
    assert result["ok"] and result["pages"] == 1 and result["overflow_pt"] == 0
    pdf = client.get("/api/cvs/base/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


@needs_latex
def test_too_long_content_is_reported(client: TestClient) -> None:
    content = client.get("/api/cvs/base").json()["content"]
    experience = next(s for s in content["sections"] if s["id"] == "experience")
    experience["items"][0]["bullets"] *= 6
    client.put("/api/cvs/base/content", json=content)
    result = client.post("/api/cvs/base/compile").json()
    assert result["ok"]
    assert result["overflow_pt"] > 0


@needs_latex
def test_latex_error_is_readable(client: TestClient) -> None:
    content = client.get("/api/cvs/base").json()["content"]
    # Un nom de photo absent fait échouer \includegraphics.
    content["header"]["photo"] = "absente.jpg"
    client.put("/api/cvs/base/content", json=content)
    result = client.post("/api/cvs/base/compile").json()
    assert not result["ok"]
    assert result["errors"] and result["errors"][0]["message"]


def test_put_style(client: TestClient) -> None:
    style = client.get("/api/cvs/base").json()["style"]
    style["blocks"]["section_title"]["font"] = "FiraSans"
    style["palette"]["primary"] = "8b1e3f"
    assert client.put("/api/cvs/base/style", json=style).status_code == 200
    saved = client.get("/api/cvs/base").json()["style"]
    assert saved["blocks"]["section_title"]["font"] == "FiraSans"
    assert saved["palette"]["primary"] == "8B1E3F"


@pytest.mark.parametrize(
    ("path", "value"),
    [(("blocks", "name", "font"), "Comic"), (("blocks", "name", "color"), "violet")],
)
def test_bad_style_is_refused(client: TestClient, path: tuple[str, ...], value: str) -> None:
    style = client.get("/api/cvs/base").json()["style"]
    target = style
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    answer = client.put("/api/cvs/base/style", json=style)
    assert answer.status_code == 422
    assert value in answer.json()["detail"]


def test_photo_upload_is_squared(client: TestClient) -> None:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (1200, 800), "red").save(buffer, "PNG")
    answer = client.post(
        "/api/cvs/base/photo", files={"file": ("p.png", buffer.getvalue(), "image/png")}
    )
    assert answer.status_code == 200
    assert client.get("/api/cvs/base").json()["content"]["header"]["photo"] == "photo.jpg"
    photo = Image.open(io.BytesIO(client.get("/api/cvs/base/photo").content))
    assert photo.size == (800, 800)


def test_photo_upload_rejects_non_images(client: TestClient) -> None:
    answer = client.post(
        "/api/cvs/base/photo", files={"file": ("x.txt", b"pas une image", "text/plain")}
    )
    assert answer.status_code == 422


def test_fonts(client: TestClient) -> None:
    listed = {font["id"]: font for font in client.get("/api/fonts").json()}
    assert listed["Lato"]["name"] == "Lato"
    assert client.get("/api/fonts/FiraSans/bold").status_code == 200
    assert client.get("/api/fonts/FiraSans/gras").status_code == 404
    assert client.get("/api/fonts/Comic/regular").status_code == 404


def test_themes(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.storage import themes

    monkeypatch.setattr(themes, "THEMES_DIR", tmp_path / "themes")
    style = client.get("/api/cvs/base").json()["style"]
    created = client.post("/api/themes", json={"name": "Bleu élégant", "style": style}).json()
    assert created["slug"] == "bleu-elegant"
    again = client.post("/api/themes", json={"name": "Bleu élégant", "style": style}).json()
    assert again["slug"] == "bleu-elegant-2"
    assert [t["slug"] for t in client.get("/api/themes").json()] == [
        "bleu-elegant-2",
        "bleu-elegant",
    ]
    assert client.delete("/api/themes/bleu-elegant").status_code == 200
    assert client.delete("/api/themes/bleu-elegant").status_code == 404
    assert client.delete("/api/themes/..").status_code == 404


@needs_latex
def test_create_duplicate_rename_delete(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cv_store, "TRASH_DIR", tmp_path / "corbeille")
    created = client.post(
        "/api/cvs", json={"name": "Thales — Ingénieur IA", "source": "base"}
    ).json()
    assert created["slug"] == "thales-ingenieur-ia"
    assert created["meta"]["source"] == "base" and created["pdf_version"]
    assert client.get("/api/cvs/thales-ingenieur-ia/photo").status_code == 200

    copy = client.post(
        "/api/cvs", json={"name": "Thales — Ingénieur IA", "source": "thales-ingenieur-ia"}
    ).json()
    assert copy["slug"] == "thales-ingenieur-ia-2"

    renamed = client.patch("/api/cvs/thales-ingenieur-ia-2", json={"name": "Thales (bis)"}).json()
    assert renamed["meta"]["name"] == "Thales (bis)"
    assert [c["slug"] for c in client.get("/api/cvs").json()][0] == "base"

    thumb = client.get("/api/cvs/thales-ingenieur-ia/thumbnail")
    assert thumb.status_code == 200 and thumb.content.startswith(b"\x89PNG")
    assert client.get("/api/cvs/thales-ingenieur-ia/tex").text.startswith("% Généré par CV Builder")

    assert (
        client.delete("/api/cvs/thales-ingenieur-ia-2")
        .json()["trash"]
        .startswith("thales-ingenieur-ia-2-")
    )
    assert client.get("/api/cvs/thales-ingenieur-ia-2").status_code == 404
    assert (tmp_path / "corbeille").is_dir()


def test_base_cannot_be_deleted(client: TestClient) -> None:
    assert client.delete("/api/cvs/base").status_code == 409


def test_create_from_unknown_source(client: TestClient) -> None:
    assert client.post("/api/cvs", json={"name": "X", "source": "inconnu"}).status_code == 404


def test_download_file_name(client: TestClient) -> None:
    from app.storage import cv_store

    assert client.get("/api/cvs/base").json()["file_stem"] == "camille_laurent"
    slug = client.post("/api/cvs", json={"name": "Ciblé"}).json()["slug"]
    folder = cv_store.folder(slug)
    # Un CV ciblé : les mots de l'analyse, sinon ceux de l'intitulé du poste.
    analysis = {
        "analysis": {"job_title": "Stage – Agent IA analyste de la documentation technique (H/F)"}
    }
    (folder / "analysis.json").write_text(json.dumps(analysis))
    assert client.get(f"/api/cvs/{slug}").json()["file_stem"] == "camille_laurent_agent-ia-analyste"
    analysis["analysis"]["short_name"] = "Agent SRE"
    (folder / "analysis.json").write_text(json.dumps(analysis))
    assert client.get(f"/api/cvs/{slug}").json()["file_stem"] == "camille_laurent_agent-sre"
    # Choisis à la main : 3 mots au plus ; vide = retour à ceux de l'analyse.
    renamed = client.patch(
        f"/api/cvs/{slug}",
        json={"name": "Ciblé", "label": "Ouicare assistant agentique production"},
    )
    assert renamed.json()["file_stem"] == "camille_laurent_ouicare-assistant-agentique"
    assert (
        client.patch(f"/api/cvs/{slug}", json={"name": "Ciblé"}).json()["meta"]["label"]
        == "ouicare-assistant-agentique"
    )
    back = client.patch(f"/api/cvs/{slug}", json={"name": "Ciblé", "label": ""}).json()
    assert back["file_stem"] == "camille_laurent_agent-sre"
    assert cv_store.short_label("Stage Ingénieur IA Backend H/F") == "ia-backend"
    # Deux CV n'ont jamais le même nom de fichier : l'entreprise, puis un numéro.
    assert cv_store.unique_label("agents-ia", "Nordia", set()) == "agents-ia"
    assert cv_store.unique_label("agents-ia", "Nordia", {"agents-ia"}) == "nordia-agents-ia"
    taken = {"agents-ia", "nordia-agents-ia"}
    assert cv_store.unique_label("agents-ia", "Nordia", taken) == "agents-ia-2"
    assert "agent-sre" in cv_store.labels_in_use()


def test_unknown_api_address_is_a_404(client: TestClient) -> None:
    """Une adresse /api inconnue répond 404 en JSON, même quand l'interface est servie."""
    for method in ("get", "post", "delete"):
        answer = getattr(client, method)("/api/nexiste-pas")
        assert answer.status_code == 404
        assert answer.headers["content-type"].startswith("application/json")
