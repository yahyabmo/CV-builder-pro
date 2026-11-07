import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app import settings
from app.ai import llm, quota, targeting, usage_log
from app.ai.schemas import OfferAnalysis
from app.ai.targeting import TargetOptions
from app.latex.compile import overflow_columns
from app.models.content import CVContent, ExperienceSection, ProjectsSection, SkillsSection
from app.models.library import Library, LibraryExperience, LibraryProject, LibrarySkill
from app.offer.fetch import Offer
from app.services import cuts
from app.storage import cv_store, library_store
from tests.conftest import needs_latex

OFFER = Offer(
    text="Stage de fin d'études : ingénieur IA backend. Python, FastAPI, Kubernetes, Docker. "
    "Autonomie et rigueur attendues. Équipe data à Bordeaux.",
    url=None,
    title=None,
)
RESERVE = "Agent IA avec appel d'outils : requêtes SQL générées et vérifiées sur PostgreSQL."


def analysis(language: str = "fr", job: bool = True) -> dict[str, Any]:
    return {
        "is_job_offer": job,
        "job_title": "Stage Ingénieur IA Backend",
        "company": "Acme",
        "location": "Bordeaux",
        "contract": "Stage",
        "offer_language": language,
        "required_languages": ["français"],
        "technologies": ["Python", "FastAPI", "Kubernetes", "Docker"],
        "tools": [],
        "methods": [],
        "skills": [],
        "soft_skills": ["autonomie"],
        "keywords": [
            {"term": "Python", "importance": 3, "category": "techno"},
            {"term": "FastAPI", "importance": 2, "category": "techno"},
            {"term": "Kubernetes", "importance": 2, "category": "outil"},
            {"term": "Docker", "importance": 1, "category": "outil"},
            {"term": "autonomie", "importance": 1, "category": "soft skill"},
        ],
        "summary": "Développer des services d'IA.",
    }


def s(text: str, source: str | None = None) -> dict[str, str]:
    return {"text": text, "source": text if source is None else source}


PLAN = {
    "headline": "Élève Ingénieur en Informatique | IA & Backend",
    "summary": "Élève-ingénieur, je déploie des services Python sur Kubernetes.",
    "skill_groups": [
        {
            "label": "Programmation",
            "items": [s("Python"), s("SQL"), s("Kubernetes", ""), s("Python")],
        },
        {"label": "Outils", "items": [s("Docker"), s("Git"), s("Conteneurs", "Linux")]},
        {"label": "Backend", "items": [s("FastAPI"), s("REST API", "API REST")]},
    ],
    "missing": [
        {"term": "Python", "note": "faux manque : le CV le montre"},
        {"term": "finance de marché", "note": "rien d'approchant"},
    ],
    "projects": [
        {"id": "cv-1", "reason": "RAG en Python"},
        {"id": "projet-inexistant", "reason": "?"},
        {"id": "cv-0", "reason": "Python"},
    ],
}


def refs(user: str) -> list[tuple[str, str]]:
    return [
        (ref, text.removesuffix(" (réserve)"))
        for ref, text in re.findall(r"^(T\d+|E[\d.]+|P\d+) : (.*)$", user, re.M)
    ]


def fake(language: str = "fr", job: bool = True) -> llm.FakeProvider:
    def answer(title: str, user: str, _: dict[str, Any]) -> Any:
        if title == "OfferAnalysis":
            return analysis(language, job)
        if title == "TargetPlan":
            return PLAN
        if title == "Rewrite":
            if language == "en":
                found = [(r, t) for r, t in refs(user) if r.startswith("E")]
                by_exp: dict[str, list[dict[str, str]]] = {}
                for ref, text in found:
                    by_exp.setdefault(ref.split(".")[0], []).append(
                        {"ref": ref, "text": f"EN {text}"}
                    )
                return {
                    "experiences": [{"exp": e, "bullets": b} for e, b in by_exp.items()],
                    "texts": [
                        {"ref": r, "text": f"EN {t}"} for r, t in refs(user) if r.startswith("P")
                    ],
                }
            return {
                "experiences": [
                    {
                        "exp": "E1",
                        "bullets": [
                            {"ref": "E1.5", "text": RESERVE},
                            {"ref": "E1.1", "text": "Puce adaptée, avec **Python**."},
                            {"ref": "E1.2", "text": "Recherche sémantique, sans changement."},
                            {"ref": "E1.9", "text": "Référence inconnue : ignorée."},
                        ],
                    },
                    # Une seule puce rendue sur deux : la seconde est complétée.
                    {"exp": "E2", "bullets": [{"ref": "E2.2", "text": "Gestion d'un rayon."}]},
                ],
                "texts": [{"ref": "P1", "text": "Projet adapté."}],
            }
        if title == "Translation":
            return {"texts": [{"ref": ref, "text": f"EN {text}"} for ref, text in refs(user)]}
        raise AssertionError(title)

    return llm.FakeProvider(answer)


LIBRARY = Library(
    skills=[
        LibrarySkill(id="k", name="Streamlit", category="IA", level="pratique", evidence="projet")
    ],
    experiences=[
        LibraryExperience(
            id="x",
            title="Stage Data Scientist",
            place="",
            bullets=[RESERVE, "Puce du CV en double."],
        )
    ],
)


async def _quiet(_: dict[str, Any]) -> None:
    return None


def run(content: CVContent, provider: llm.FakeProvider, **options: Any) -> targeting.Draft:
    return asyncio.run(
        targeting.run("base", content, LIBRARY, OFFER, TargetOptions(**options), provider, _quiet)
    )


@pytest.fixture(autouse=True)
def drafts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(targeting, "DRAFTS_DIR", tmp_path / "drafts")
    monkeypatch.setattr(usage_log, "USAGE_FILE", tmp_path / "usage.json")
    monkeypatch.setattr(llm, "BACKOFF", (0, 0, 0))
    monkeypatch.setattr(quota, "QUOTA_FILE", tmp_path / "quota.json")


def test_flatten_and_coverage(base_content: CVContent) -> None:
    know = targeting.build_knowledge(base_content, Library())
    found = targeting.coverage(
        OfferAnalysis.model_validate(analysis()), "Python et **FastAPI**. Docker.", know
    )
    assert found.present == ["Python", "FastAPI", "Docker"]
    assert found.absent == ["Kubernetes", "autonomie"]
    assert found.score == round(100 * 6 / 9)
    assert " node.js " in targeting.flatten("React, Node.js.")
    assert " c++ " in targeting.flatten("C/C++")
    a = OfferAnalysis.model_validate(
        {
            **analysis(),
            "keywords": [{"term": "revue de code", "importance": 2, "category": "méthode"}],
        }
    )
    assert targeting.new_terms("revues de code", "la revue de code", a, know) == []
    assert targeting.new_terms("Git", "Git et revue de code", a, know) == ["revue de code"]
    assert know.knows("LLMs") and know.knows("Python, SQL") and not know.knows("Kubernetes")
    assert targeting.plain_marks("texte", "un **mot** et __un autre__") == "un mot et un autre"
    assert targeting.lost_terms(
        "Backend Python/FastAPI sous Docker.", "Développement backend Python.", a, know
    ) == ["Docker", "FastAPI"]


def test_pipeline_maximizes_but_asks(base_content: CVContent) -> None:
    provider = fake()
    draft = run(base_content, provider, projects_count=2)
    assert [call[0] for call in provider.calls] == ["OfferAnalysis", "TargetPlan", "Rewrite"]
    by_id = {c.id: c for c in draft.changes}

    # Une compétence absente du profil est proposée, à confirmer, hors du texte par défaut.
    programming = by_id["skills-0"]
    states = {c.text: c.state for c in programming.chips}
    assert states["Python"] == states["SQL"] == "kept" and states["Kubernetes"] == "pending"
    assert states["Java"] == "removed" and list(states).count("Python") == 1
    assert programming.after == "Python, SQL." and programming.pending == ["Kubernetes"]
    assert "Linux → Conteneurs" in by_id["skills-1"].notes[-1]
    assert by_id["skills-2"].after == "FastAPI, REST API."
    assert by_id["skills-remove-1"].kind == "remove"

    # Une phrase qui introduit un terme absent du profil part décochée.
    assert by_id["summary"].pending == ["Kubernetes"]
    assert "summary" not in targeting.default_accepted(draft)

    # Puces : la réserve est utilisée, le gras ajouté retiré, une référence inconnue ignorée,
    # et il y a toujours autant de puces que sur le CV.
    stage = by_id["exp-experience-0"]
    assert [line.reserve for line in stage.lines] == [True, False, False, False]
    assert stage.lines[0].text == RESERVE and stage.lines[1].text == "Puce adaptée, avec Python."
    assert len(stage.after.split("\n")) == 4
    job = by_id["exp-experience-1"]
    assert job.after.split("\n")[0] == "Gestion d'un rayon." and len(job.lines) == 2

    # Projets : inconnu ignoré, nombre demandé respecté.
    assert [p.id for p in draft.plan.projects] == ["cv-1", "cv-0"]
    assert by_id["project-cv-1"].after == "Projet adapté."
    assert {"project-remove-cv-2", "project-remove-cv-3"} <= set(by_id)
    # « Python » est dans le CV : pas « manquant ».
    assert [m.term for m in draft.plan.missing] == ["finance de marché"]

    everything = targeting.apply(base_content, draft, targeting.default_accepted(draft))
    skills = next(x for x in everything.sections if isinstance(x, SkillsSection))
    assert [g.label for g in skills.items] == ["Programmation", "Outils", "Backend"]
    assert "Kubernetes" not in json.dumps(everything.model_dump(), ensure_ascii=False)
    experience = next(x for x in everything.sections if isinstance(x, ExperienceSection))
    assert experience.items[0].bullets[0] == RESERVE
    projects = next(x for x in everything.sections if isinstance(x, ProjectsSection))
    assert [p.title.split(" –")[0] for p in projects.items] == [
        "Assistant de questions sur des documents",
        "TrafficLens",
    ]

    # Rien d'inconfirmé ne passe : la compétence acceptée doit être confirmée.
    choice = {"skills-0": "Python, SQL, Kubernetes.", "summary": by_id["summary"].after}
    assert targeting.unconfirmed(draft, choice, []) == ["Kubernetes"]
    assert targeting.unconfirmed(draft, choice, ["kubernetes"]) == []

    # Un groupe gardé ne répète pas ce qu'un nouveau groupe montre déjà.
    mixed = targeting.apply(base_content, draft, {"skills-2": "Python, FastAPI."})
    skills = next(x for x in mixed.sections if isinstance(x, SkillsSection))
    assert skills.items[0].text == "C/C++, Java, TypeScript, SQL."
    assert targeting.load_draft(draft.id).id == draft.id


def test_private_repo_link_stays_out(base_content: CVContent) -> None:
    library = Library(
        projects=[
            LibraryProject(
                id="t",
                title="Outil interne",
                link="https://github.com/y/outil-interne",
                private=True,
            ),
            LibraryProject(id="r", title="Autre", link="https://github.com/y/Autre"),
        ]
    )
    know = targeting.build_knowledge(base_content, library)
    assert know.projects["t"]["link"] is None and know.projects["r"]["link"]


def test_rerun_keeps_the_analysis(base_content: CVContent) -> None:
    first = run(base_content, fake())
    provider = fake()
    again = asyncio.run(
        targeting.run(
            "base",
            base_content,
            LIBRARY,
            OFFER,
            TargetOptions(**first.options),
            provider,
            _quiet,
            analysis=first.analysis,
            parent=first.id,
        )
    )
    assert [call[0] for call in provider.calls] == ["TargetPlan", "Rewrite"]
    assert again.parent == first.id and again.id != first.id


def test_english_offer_translates_the_rest(base_content: CVContent) -> None:
    provider = fake("en")
    draft = run(base_content, provider)
    assert draft.language == "en"
    assert [call[0] for call in provider.calls][-1] == "Translation"
    # Ni téléphone ni adresse électronique ne partent au modèle.
    for _, user in provider.calls:
        assert "@" not in user
        for line in base_content.header.contact_lines:
            for item in line:
                if re.search(r"\d", item.text):
                    assert item.text not in user

    # Les compétences proposées passent aussi par la traduction.
    skill_changes = [c for c in draft.changes if c.id.startswith("skills-") and c.kind != "remove"]
    assert all(c.after.startswith("EN ") for c in skill_changes)
    assert draft.changes[0].pending == [] and not any(
        p.startswith("chip/") for p in draft.translation
    )

    accepted = {c.id: c.after for c in draft.changes if c.id != "headline"}
    out = targeting.apply(base_content, draft, accepted)
    assert out.language == "en"
    assert out.header.headline == "EN " + base_content.header.headline
    assert all(x.title.startswith("EN ") for x in out.sections)
    experience = next(x for x in out.sections if x.id == "experience")
    assert experience.items[0].bullets[0].startswith("EN ")

    # Une traduction retouchée à la main.
    path = "section/experience/title"
    assert draft.translation_source[path] == next(
        x.title for x in base_content.sections if x.id == "experience"
    )
    edited = targeting.apply(base_content, draft, {"translation": ""}, {path: "EXPERIENCE"})
    assert next(x for x in edited.sections if x.id == "experience").title == "EXPERIENCE"

    kept = targeting.apply(base_content, draft, {})
    assert kept.language == "fr" and kept.header.headline == base_content.header.headline


def test_not_a_job_offer(base_content: CVContent) -> None:
    with pytest.raises(llm.LLMError, match="offre d'emploi"):
        run(base_content, fake(job=False))


def test_generate_retries() -> None:
    answers = iter(["{pas du json", {"ok": True, "langue": "fr"}])

    class Ping(BaseModel):
        ok: bool
        langue: str

    notes: list[str] = []

    async def notify(message: str) -> None:
        notes.append(message)

    provider = llm.FakeProvider(lambda *_: next(answers))
    result = asyncio.run(llm.generate(provider, "s", "u", Ping, notify))
    assert result.attempts == 2 and result.data.ok
    assert "nouvel essai" in notes[0]

    class Busy(llm.FakeProvider):
        failures = 1

        async def complete(
            self, system: str, user: str, schema: dict[str, Any], notify: Any = None
        ) -> llm.Completion:
            if self.failures:
                self.failures -= 1
                raise llm.LLMError("503", retryable=True)
            return await super().complete(system, user, schema)

    notes.clear()
    result = asyncio.run(
        llm.generate(Busy(lambda *_: {"ok": True, "langue": "fr"}), "s", "u", Ping, notify)
    )
    assert result.data.ok and "surchargé" in notes[0]


def test_gemini_daily_quota() -> None:
    body = {
        "error": {
            "code": 429,
            "message": "You exceeded your current quota. Please retry in 12h16m32.2s.",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                    "violations": [
                        {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}
                    ],
                },
                {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "44131s"},
            ],
        }
    }
    error = llm._http_error("Gemini", httpx.Response(429, json=body), "gemini-a")
    assert error.quota_until and not error.retryable
    assert "quota gratuit du jour épuisé pour gemini-a" in error.message
    minute = llm._http_error(
        "Gemini", httpx.Response(429, json={"error": {"message": "Slow down"}})
    )
    assert minute.retryable and minute.quota_until is None


def test_gemini_model_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def call(self: Any, model: str, *_: Any) -> llm.Completion:
        calls.append(model)
        if model == "gemini-a":
            raise llm.LLMError("épuisé", status=429, quota_until=time.time() + 3600)
        if model == "gemini-b":
            raise llm.LLMError("503", retryable=True, status=503)
        return llm.Completion(text="{}", usage=llm.Usage(), model=model)

    monkeypatch.setattr(llm.GeminiProvider, "_call", call)
    provider = llm.GeminiProvider("clé", ["gemini-a", "gemini-b", "gemini-c"], 0.2)
    notes: list[str] = []

    async def notify(message: str) -> None:
        notes.append(message)

    done = asyncio.run(provider.complete("s", "u", {}, notify))
    assert done.model == "gemini-c" and calls == ["gemini-a", "gemini-b", "gemini-c"]
    assert notes[0] == "gemini-a : quota du jour épuisé, je passe à gemini-b…"
    # Le modèle épuisé n'est plus essayé.
    calls.clear()
    asyncio.run(provider.complete("s", "u", {}))
    assert calls == ["gemini-b", "gemini-c"]
    quota.block("gemini-b", time.time() + 60)
    quota.block("gemini-c", time.time() + 60)
    with pytest.raises(llm.LLMError, match="tous les modèles Gemini"):
        asyncio.run(provider.complete("s", "u", {}))


def test_overflow_columns() -> None:
    tex = "\n".join(
        ["x"] * 9 + [r"\begin{minipage}[t]{1cm}"] + ["x"] * 9 + [r"\begin{minipage}[t]{2cm}"]
    )
    log = (
        "Overfull \\vbox (12.5pt too high) detected at line 15\n"
        "Overfull \\vbox (3.0pt too high) detected at line 25\n"
        "Overfull \\vbox (9.0pt too high) detected at line 4\n"
    )
    assert overflow_columns(log, tex) == {"left": 12.5, "right": 3.0}


def test_cuts(base_content: CVContent) -> None:
    proposed = cuts.suggest(base_content, {"right": 20.0, "left": 0.2})
    ids = [c.id for c in proposed]
    assert ids == ["bullet:experience:0:3", "item:projets:3"]
    assert all(c.column == "right" for c in proposed)
    shorter = cuts.apply_cut(base_content, "item:projets:3")
    projects = next(s for s in shorter.sections if isinstance(s, ProjectsSection))
    assert len(projects.items) == 3
    with pytest.raises(cuts.UnknownCut):
        cuts.apply_cut(base_content, "item:projets:9")
    with pytest.raises(cuts.UnknownCut):
        cuts.apply_cut(base_content, "bullet:projets:0:0")


# ─── API ─────────────────────────────────────────────────────────────────────


def test_settings_never_expose_keys(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    env.write_text("LLM_PROVIDER=gemini\nGEMINI_API_KEY=cle-tres-secrete\n")
    monkeypatch.setattr(settings, "ENV_FILE", env)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "local" / "settings.json")
    response = client.get("/api/settings")
    assert response.status_code == 200
    assert "cle-tres-secrete" not in response.text
    data = response.json()
    assert data["keys"] == {
        "relais": False,
        "gemini": True,
        "mistral": False,
        "ollama": True,
        "demo": True,
    }
    assert data["ai"]["provider"] == "gemini" and data["blocked"] == {}

    changed = {**data["ai"], "provider": "mistral"}
    assert client.put("/api/settings", json=changed).json()["ai"]["provider"] == "mistral"
    assert "cle" not in (tmp_path / "local" / "settings.json").read_text()
    assert client.put("/api/settings", json={**changed, "provider": "fake"}).status_code == 422


def events(response: Any) -> list[dict[str, Any]]:
    return [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]


@pytest.fixture
def target_client(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    monkeypatch.setattr(library_store, "LIBRARY_DIR", tmp_path / "library")
    monkeypatch.setattr(llm, "provider_from_settings", lambda: fake())
    return client


@needs_latex
def test_target_api(target_client: TestClient) -> None:
    client = target_client
    assert client.post("/api/target", json={"text": ""}).status_code == 422

    found = events(client.post("/api/target", json={"text": OFFER.text, "projects_count": 2}))
    labels = [e["label"] for e in found if e["type"] == "step"]
    assert labels == ["Analyse de l'offre", "Compétences et projets", "Formulations"]
    assert found[-1]["type"] == "done"
    draft = found[-1]["draft"]
    assert client.get(f"/api/target/drafts/{draft['id']}").json()["id"] == draft["id"]
    changes = {c["id"]: c for c in draft["changes"]}

    # Score en direct : confirmer Kubernetes le fait monter.
    base = {
        c["id"]: c["after"]
        for c in draft["changes"]
        if not c["pending"] or c["group"] == "Compétences"
    }
    before = client.post(f"/api/target/drafts/{draft['id']}/score", json={"accepted": base}).json()
    more = {**base, "skills-0": "Python, SQL, Kubernetes."}
    after = client.post(f"/api/target/drafts/{draft['id']}/score", json={"accepted": more}).json()
    assert "Kubernetes" in before["absent"] and "Kubernetes" in after["present"]
    assert after["score"] > before["score"]

    url = f"/api/target/drafts/{draft['id']}/apply"
    assert client.post(url, json={"name": "Acme", "accepted": {"x": "y"}}).status_code == 422
    refused = client.post(url, json={"name": "Acme", "accepted": more})
    assert refused.status_code == 422 and "Kubernetes" in refused.json()["detail"]

    accepted = {**more, "summary": changes["summary"]["after"]}
    applied = client.post(
        url, json={"name": "Acme IA", "accepted": accepted, "confirmed": ["Kubernetes"]}
    )
    assert applied.status_code == 200
    out = applied.json()
    assert out["compile"]["ok"] and out["compile"]["pages"] == 1
    assert out["library_added"] == ["Kubernetes"] and "Kubernetes" in out["score"]["present"]
    library = client.get("/api/library").json()
    added = next(x for x in library["skills"] if x["name"] == "Kubernetes")
    assert added["source"] == "offre" and added["category"] == "Cloud & DevOps"

    detail = client.get(f"/api/cvs/{out['slug']}").json()
    assert detail["meta"]["company"] == "Acme" and detail["meta"]["score"] == out["score"]["score"]
    info = client.get(f"/api/target/offer/{out['slug']}").json()
    assert info["score"]["score"] == out["score"]["score"] and info["text"] == OFFER.text
    assert [m["term"] for m in info["missing"]] == ["finance de marché"]
    assert client.get("/api/target/offer/base").status_code == 404

    # Relancer : sans réanalyser l'offre.
    again = events(client.post(f"/api/target/drafts/{draft['id']}/rerun"))
    assert [e["label"] for e in again if e["type"] == "step"] == [
        "Compétences et projets",
        "Formulations",
    ]
    assert again[-1]["draft"]["parent"] == draft["id"]


def test_target_api_errors(target_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    client = target_client
    monkeypatch.setattr(llm, "provider_from_settings", lambda: fake(job=False))
    found = events(client.post("/api/target", json={"text": OFFER.text}))
    assert found[-1]["type"] == "error" and "offre d'emploi" in found[-1]["message"]
    found = events(client.post("/api/target", json={"text": "trop court"}))
    assert found[-1]["type"] == "error"
    assert (
        client.post("/api/target", json={"source": "inconnu", "text": OFFER.text}).status_code
        == 404
    )
    assert client.post("/api/target/drafts/000000000000/rerun").status_code == 404


def test_unreadable_offer_analysis_is_a_clear_error(client: TestClient) -> None:
    """Une analyse d'offre incomplète : une erreur lisible, pas une erreur 500."""
    slug = cv_store.create("Analyse abîmée", cv_store.BASE_SLUG)
    (cv_store.folder(slug) / "analysis.json").write_text('{"analysis": {"contract": "Stage"}}')
    answer = client.get(f"/api/target/offer/{slug}")
    assert answer.status_code == 422
    assert "illisible" in answer.json()["detail"]


def test_unreadable_offer_analysis_means_no_letter(client: TestClient) -> None:
    slug = cv_store.create("Analyse abîmée", cv_store.BASE_SLUG)
    (cv_store.folder(slug) / "analysis.json").write_text('{"analysis": {"contract": "Stage"}}')
    assert client.get(f"/api/cvs/{slug}/letter").json()["available"] is False
