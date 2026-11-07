import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models.content import CVContent
from app.models.library import Library, LibraryProject, LibrarySkill
from app.services import library_import
from app.services.library_import import from_cv, known_project, split_skills
from app.services.skill_categories import guess
from app.storage import library_store


def test_split_skills() -> None:
    assert split_skills("IA générative (LLM, RAG), NumPy ; recherche (A*, Minimax).") == [
        "IA générative",
        "LLM",
        "RAG",
        "NumPy",
        "recherche",
        "A*",
        "Minimax",
    ]
    assert split_skills("Python, C/C++, HTML/CSS.") == ["Python", "C/C++", "HTML/CSS"]


def test_from_cv(base_content: CVContent) -> None:
    projects, skills, experiences = from_cv(base_content, Library())
    titles = [p.title for p in projects]
    assert "Planificateur de tournées" in titles
    tours = next(p for p in projects if p.title.startswith("Planificateur"))
    # Ce qui vient du CV est déjà vrai : validé d'office.
    assert tours.team == "binôme" and tours.link and tours.status == "validé"
    names = {s.name for s in skills}
    assert {"Python", "FastAPI", "PyTorch", "LaTeX"} <= names
    assert all(s.status == "validé" for s in skills)
    stage = next(e for e in experiences if e.title == "Stage Data Scientist")
    assert len(stage.bullets) == 4 and stage.source == "cv"
    assert [e.title for e in from_cv(base_content, Library(experiences=experiences))[2]] == []


def test_from_cv_skips_what_is_already_there(base_content: CVContent) -> None:
    library = Library(
        projects=[LibraryProject(id="p1", title="Eirbone", link=None)],
        skills=[
            LibrarySkill(id="s1", name="python"),
            LibrarySkill(id="s2", name="Docker", aliases=["git"]),
        ],
    )
    projects, skills, _ = from_cv(base_content, library)
    assert not any(p.title.startswith("Eirbone") for p in projects)
    names = {s.name.lower() for s in skills}
    assert "python" not in names and "git" not in names and "docker" not in names


def test_normalize_keeps_plus_and_sharp() -> None:
    from app.services.library_import import normalize

    assert len({normalize("C"), normalize("C++"), normalize("C#")}) == 3
    assert normalize("Node.js") == normalize("NodeJS")


def test_known_project() -> None:
    library = Library(
        projects=[LibraryProject(id="p", title="Acting Shooting Star – Moteur de jeu")]
    )
    assert known_project(library, "Acting shooting star", None)
    assert not known_project(library, "Coursidor", None)
    linked = Library(projects=[LibraryProject(id="p", title="X", link="https://github.com/a/b/")])
    assert known_project(linked, "Autre nom", "https://github.com/a/b")


def test_from_github_with_a_fake_api(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = {
        "user/repos?per_page=100&affiliation=owner": [
            {
                "name": "nachOS",
                "full_name": "y/nachOS",
                "html_url": "https://github.com/y/nachOS",
                "description": "Système",
                "private": False,
                "created_at": "2025-09-01",
                "pushed_at": "2026-01-30",
            },
            {
                "name": "Eirbone",
                "full_name": "y/Eirbone",
                "html_url": "https://github.com/y/Eirbone",
                "description": "",
                "private": False,
                "created_at": "2026-03-01",
                "pushed_at": "2026-05-06",
            },
        ],
        "repos/y/nachOS/languages": {"C++": 900, "C": 80, "Makefile": 20},
        "repos/y/nachOS/readme": {"content": ""},
    }
    monkeypatch.setattr(library_import, "_gh", lambda path: answers[path])
    answers["repos/y/Eirbone/languages"] = {"C": 700, "Java": 300}
    answers["repos/y/Eirbone/readme"] = {
        "content": base64.b64encode(b"# Eirbone\nTracker en C.").decode()
    }
    library = Library(projects=[LibraryProject(id="p", title="Eirbone – P2P")])
    projects, skills = library_import.from_github(library)
    # Le projet déjà connu n'est pas dupliqué : il récupère le lien, le README et les langages.
    [eirbone] = library.projects
    assert eirbone.link == "https://github.com/y/Eirbone" and eirbone.techs == ["C", "Java"]
    assert "Tracker en C" in eirbone.notes
    [nachos] = projects
    # Le cadre n'est jamais deviné depuis GitHub : on le précise en validant.
    assert nachos.title == "NachOS" and nachos.team is None and nachos.date == "2025 – 2026"
    assert nachos.techs == ["C++", "C"]
    assert [s.name for s in skills] == ["C++", "C"]


@pytest.fixture
def library_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> TestClient:
    monkeypatch.setattr(library_store, "LIBRARY_DIR", tmp_path / "library")
    return client


def test_skill_categories() -> None:
    mine = ["Programmation", "Intelligence artificielle & Data", "Développement logiciel & web"]
    assert guess("Rust", mine) == "Programmation"
    assert guess("Streamlit", mine) == "Intelligence artificielle & Data"
    assert guess("React", mine) == "Développement logiciel & web"
    assert guess("Kubernetes", mine) == "Cloud & DevOps"
    assert guess("APIs", ["Outils"]) == "Autres" and guess("LLMs", []) == "IA & Data"
    assert guess("Docker", ["Outils & Systèmes"]) == "Outils & Systèmes"


def test_library_api(library_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    client = library_client

    def offline(_: str) -> object:
        raise library_import.GitHubUnavailable("GitHub n'est pas connecté")

    monkeypatch.setattr(library_import, "_gh", offline)
    assert client.get("/api/library").json() == {"projects": [], "skills": [], "experiences": []}
    filled = client.post("/api/library/fill").json()
    assert filled["added"]["projects"] == 4 and filled["added"]["skills"] > 20
    assert filled["added"]["experiences"] == 3
    # GitHub hors ligne n'empêche pas le reste, et le dit.
    assert filled["github_error"] == "GitHub n'est pas connecté"
    # Un second remplissage ne duplique rien.
    again = client.post("/api/library/fill").json()
    assert again["added"] == {"projects": 0, "skills": 0, "experiences": 0}

    bulk = client.post(
        "/api/library/skills/bulk",
        json={"text": "Kubernetes, streamlit ; python\nMCP", "level": "notions"},
    ).json()
    assert bulk["added"] == ["Kubernetes", "streamlit", "MCP"] and bulk["known"] == ["python"]
    kube = next(x for x in bulk["library"]["skills"] if x["name"] == "Kubernetes")
    assert kube["category"] == "Cloud & DevOps" and kube["level"] == "notions"

    experiences = bulk["library"]["experiences"]
    experiences[0]["bullets"].append("Une puce de réserve.")
    saved = client.put("/api/library/experiences", json=experiences).json()
    assert saved["experiences"][0]["bullets"][-1] == "Une puce de réserve."

    projects = filled["library"]["projects"]
    projects[0]["status"] = "validé"
    projects[0]["techs"] = ["Python", "JavaScript"]
    saved = client.put("/api/library/projects", json=projects).json()
    assert saved["projects"][0]["status"] == "validé"
    duplicate = [projects[0], projects[0]]
    assert client.put("/api/library/projects", json=duplicate).status_code == 422


def test_project_draft(library_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ai import llm

    # Le faux modèle n'écrit rien dans le journal de consommation.
    draft = {
        "description": "Partage P2P en C et Java.",
        "bullets": ["Tracker en C."],
        "techs": ["C", "Java"],
    }
    provider = llm.FakeProvider(lambda *_: draft)
    monkeypatch.setattr(llm, "provider_from_settings", lambda: provider)
    library_store.save_projects(
        [
            LibraryProject(
                id="p", title="Eirbone", notes="README : tracker multithreadé en C, pairs en Java."
            )
        ]
    )
    answer = library_client.post("/api/library/projects/p/draft")
    assert answer.status_code == 200 and answer.json()["techs"] == ["C", "Java"]
    assert "tracker multithreadé" in provider.calls[0][1]
    assert library_client.post("/api/library/projects/inconnu/draft").status_code == 404


def test_fill_without_github_never_calls_gh(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """« github=false » : la bibliothèque se remplit du CV seul, sans lire le compte GitHub."""

    def no_github(_: str) -> object:
        raise AssertionError("GitHub ne doit pas être lu")

    monkeypatch.setattr(library_store, "LIBRARY_DIR", tmp_path / "library")
    monkeypatch.setattr(library_import, "_gh", no_github)
    answer = client.post("/api/library/fill?github=false").json()
    assert answer["added"]["skills"] > 10 and answer["github_error"] is None
