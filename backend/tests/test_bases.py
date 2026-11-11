"""Plusieurs CV classiques : en ajouter, en remplacer, en supprimer, sans perdre les autres."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai import usage_log
from app.models.content import CVContent
from app.storage import cv_store, library_store
from tests.conftest import needs_latex


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(library_store, "LIBRARY_DIR", tmp_path / "library")
    monkeypatch.setattr(cv_store, "TRASH_DIR", tmp_path / "corbeille")
    monkeypatch.setattr(usage_log, "USAGE_FILE", tmp_path / "usage.json")


def _kinds(client: TestClient) -> dict[str, str]:
    return {cv["slug"]: cv["meta"]["kind"] for cv in client.get("/api/cvs").json()}


def _name_of(client: TestClient, slug: str) -> str:
    return client.get(f"/api/cvs/{slug}").json()["content"]["header"]["name"]


@needs_latex
def test_a_new_base_cv_is_added_without_touching_the_first(
    client: TestClient, base_content: CVContent
) -> None:
    content = base_content.model_copy(deep=True)
    content.header.name = "CAMILLE DEUX"
    out = client.post(
        "/api/welcome/apply", json={"content": content.model_dump(), "new_name": "CV Data"}
    ).json()
    assert out["compile"]["ok"] and out["slug"] == "cv-data"
    assert _kinds(client)["cv-data"] == "base"
    assert _name_of(client, "cv-data") == "CAMILLE DEUX"
    assert _name_of(client, "base") == "CAMILLE LAURENT"
    assert client.get("/api/cvs/cv-data").json()["meta"]["name"] == "CV Data"
    # Le premier lancement est passé : l'accueil ne se rouvre plus.
    assert client.get("/api/welcome").json()["show"] is False
    assert not cv_store.TRASH_DIR.exists()

    # Remplacé : l'ancien part à la corbeille, les autres ne bougent pas.
    content.header.name = "CAMILLE TROIS"
    out = client.post(
        "/api/welcome/apply", json={"content": content.model_dump(), "target": "cv-data"}
    ).json()
    assert out["slug"] == "cv-data" and _name_of(client, "cv-data") == "CAMILLE TROIS"
    assert _name_of(client, "base") == "CAMILLE LAURENT"
    assert [p.name.startswith("cv-data-") for p in cv_store.TRASH_DIR.iterdir()] == [True]


def test_only_a_base_cv_can_be_replaced(client: TestClient, base_content: CVContent) -> None:
    slug = client.post("/api/cvs", json={"name": "Candidature"}).json()["slug"]
    body = {"content": base_content.model_dump(), "target": slug}
    assert client.post("/api/welcome/apply", json=body).status_code == 409
    body["target"] = "inconnu"
    assert client.post("/api/welcome/apply", json=body).status_code == 404


def test_copy_rename_and_keep_base_cvs_visual(client: TestClient) -> None:
    copy = client.post("/api/cvs", json={"name": "English CV", "kind": "base"}).json()
    assert copy["meta"]["kind"] == "base" and _kinds(client)[copy["slug"]] == "base"
    client.patch(f"/api/cvs/{copy['slug']}", json={"name": "CV anglais"})
    assert client.get(f"/api/cvs/{copy['slug']}").json()["meta"]["name"] == "CV anglais"
    # Un CV classique n'est pas une candidature et ne passe pas en mode manuel.
    patch = client.patch(f"/api/cvs/{copy['slug']}/application", json={"status": "sent"})
    assert patch.status_code == 409
    tex = client.get(f"/api/cvs/{copy['slug']}/source").json()["tex"] + "\n% retouche"
    assert client.put(f"/api/cvs/{copy['slug']}/source", json={"tex": tex}).status_code == 409


def test_deleting_base_cvs(client: TestClient) -> None:
    # Le seul CV classique ne se supprime pas.
    assert client.delete("/api/cvs/base").status_code == 409

    second = client.post("/api/cvs", json={"name": "CV Web", "kind": "base"}).json()["slug"]
    third = client.post("/api/cvs", json={"name": "CV Data", "kind": "base"}).json()["slug"]
    targeted = client.post("/api/cvs", json={"name": "Offre", "source": third}).json()["slug"]
    assert client.delete(f"/api/cvs/{second}").status_code == 200
    assert second not in _kinds(client)

    # Supprimer la première version : le CV classique le plus récent prend sa place.
    folder = cv_store.folder(third)
    (folder / "content.json").write_text(
        (folder / "content.json").read_text().replace("CAMILLE LAURENT", "CAMILLE DATA")
    )
    cv_store.touch(folder)
    assert client.delete("/api/cvs/base").status_code == 200
    kinds = _kinds(client)
    assert third not in kinds and kinds["base"] == "base"
    assert _name_of(client, "base") == "CAMILLE DATA"
    assert client.get("/api/cvs/base").json()["meta"]["name"] == "CV Data"
    assert client.get(f"/api/cvs/{targeted}").json()["meta"]["source"] == "base"
    assert client.delete("/api/cvs/base").status_code == 409


def test_library_is_filled_from_every_base_cv(client: TestClient) -> None:
    slug = client.post("/api/cvs", json={"name": "CV Web", "kind": "base"}).json()["slug"]
    folder = cv_store.folder(slug)
    content = json.loads((folder / "content.json").read_text())
    skills = next(s for s in content["sections"] if s["kind"] == "skills")
    skills["items"].append({"label": "Front", "text": "Svelte, Astro."})
    (folder / "content.json").write_text(json.dumps(content))
    library = client.post("/api/library/fill?github=false").json()["library"]
    names = {s["name"] for s in library["skills"]}
    assert {"Svelte", "Astro", "Python"} <= names
