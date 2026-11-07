"""Lecture et écriture de la bibliothèque (library/projects.json, skills.json)."""

import json
from pathlib import Path

from pydantic import TypeAdapter

from app.models.library import Library, LibraryExperience, LibraryProject, LibrarySkill
from app.paths import LIBRARY_DIR

_PROJECTS = TypeAdapter(list[LibraryProject])
_SKILLS = TypeAdapter(list[LibrarySkill])
_EXPERIENCES = TypeAdapter(list[LibraryExperience])


def _file(name: str) -> Path:
    return LIBRARY_DIR / name


def load() -> Library:
    projects = _file("projects.json")
    skills = _file("skills.json")
    experiences = _file("experiences.json")
    return Library(
        projects=_PROJECTS.validate_json(projects.read_bytes()) if projects.exists() else [],
        skills=_SKILLS.validate_json(skills.read_bytes()) if skills.exists() else [],
        experiences=(
            _EXPERIENCES.validate_json(experiences.read_bytes()) if experiences.exists() else []
        ),
    )


def _write(name: str, data: list) -> None:
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    path = _file(name)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def save_projects(projects: list[LibraryProject]) -> None:
    _write("projects.json", [p.model_dump(mode="json") for p in projects])


def save_skills(skills: list[LibrarySkill]) -> None:
    _write("skills.json", [s.model_dump(mode="json") for s in skills])


def save_experiences(experiences: list[LibraryExperience]) -> None:
    _write("experiences.json", [e.model_dump(mode="json") for e in experiences])
