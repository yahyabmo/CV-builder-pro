"""Les idées de projet d'un CV ciblé, gardées avec lui, et leur cahier des charges.

Une idée coûte une requête (``api/project_ideas.py``) ; elle est enregistrée
dans le dossier du CV pour ne pas la payer deux fois. Le cahier des charges est
écrit sans IA, à partir de l'idée et de l'offre.
"""

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from app.ai.schemas import OfferAnalysis, ProjectIdea
from app.models.meta import now

FILE = "project-ideas.json"


class SavedIdeas(BaseModel):
    ideas: list[ProjectIdea] = []
    created_at: datetime | None = None


def load(folder: Path) -> SavedIdeas:
    file = folder / FILE
    if not file.exists():
        return SavedIdeas()
    try:
        return SavedIdeas.model_validate_json(file.read_text(encoding="utf-8"))
    except ValueError:
        return SavedIdeas()


def save(folder: Path, ideas: list[ProjectIdea]) -> SavedIdeas:
    saved = SavedIdeas(ideas=ideas, created_at=now())
    (folder / FILE).write_text(
        json.dumps(saved.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return saved


def file_name(idea: ProjectIdea) -> str:
    """« Assistant de maintenance » → « cahier-des-charges-assistant-de-maintenance.md »."""
    ascii_name = unicodedata.normalize("NFKD", idea.name).encode("ascii", "ignore").decode()
    stem = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:50] or "projet"
    return f"cahier-des-charges-{stem}.md"


def brief(idea: ProjectIdea, analysis: OfferAnalysis) -> str:
    """Le cahier des charges de l'idée, en Markdown, à suivre soi-même."""
    where = " · ".join(part for part in (analysis.company, analysis.location) if part)
    lines = [
        f"# {idea.name}",
        "",
        f"Cahier des charges · {idea.effort} · {', '.join(idea.stack)}",
        "",
        "## L'offre visée",
        "",
        f"{analysis.job_title}{f' ({where})' if where else ''}. {analysis.summary}".strip(),
        "",
        "## Ce que fait le projet",
        "",
        idea.pitch,
        "",
        f"Pour cette offre, {idea.why}",
        "",
        "## Mots-clés de l'offre qu'il rend vrais",
        "",
        ", ".join(idea.keywords) + ".",
        "",
        "## Les composants",
        "",
        *[f"- {module}" for module in idea.modules],
        "",
        "## Les données",
        "",
        idea.data,
        "",
        "## Étapes",
        "",
        *[f"{n}. {step}" for n, step in enumerate(idea.steps, 1)],
        "",
        "## À livrer",
        "",
        "- Un dépôt public, avec un README : ce que fait le projet, captures, chiffres mesurés.",
        "- Des tests, et un lancement en une commande.",
        "- Rien de payant ni de privé : les données et les services utilisés sont gratuits.",
        "",
        "## Sur ton CV, une fois fait",
        "",
        f"**{idea.name}** · Projet personnel",
        "",
        idea.cv_line,
        "",
        "Ajoute-le depuis la Bibliothèque (« Remplir depuis GitHub ») une fois le dépôt publié.",
        "",
        "## En entretien",
        "",
        *[f"- {question}" for question in idea.questions],
        "",
        "Prépare une réponse courte à chacune, avec un chiffre du projet.",
        "",
    ]
    return "\n".join(lines)
