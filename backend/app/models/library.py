"""La bibliothèque : tous les projets, compétences et expériences de la personne.

Un CV n'en montre qu'une partie ; le ciblage d'une offre choisit dans la
bibliothèque ce qu'il faut mettre en avant. C'est aussi la liste de ce qui est
vrai : l'IA n'utilise sans confirmation que ce qui y est validé. Une entrée
« proposée » (tirée de GitHub) attend une validation ; une entrée de source
« offre » a été confirmée pendant un ciblage.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["validé", "proposé"]
Source = Literal["cv", "github", "manuel", "offre"]
Level = Literal["notions", "pratique", "maîtrise"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LibraryProject(_Model):
    id: str
    title: str
    # Telle qu'affichée dans le CV : « 2026 », « Mars – Mai 2026 ».
    date: str = ""
    context: Literal["école", "stage", "perso", "autre"] | None = None
    team: Literal["seul", "binôme", "équipe"] | None = None
    techs: list[str] = Field(default_factory=list)
    # La phrase du CV.
    description: str = ""
    # Points détaillés, pour l'IA ou une présentation en puces.
    bullets: list[str] = Field(default_factory=list)
    link: str | None = None
    private: bool = False
    # Informations brutes (extrait du README…) que l'IA peut exploiter.
    notes: str = ""
    source: Source = "manuel"
    status: Status = "validé"


class LibrarySkill(_Model):
    id: str
    name: str
    category: str = "Autres"
    # Autres écritures reconnues dans une offre (« JS » pour JavaScript).
    aliases: list[str] = Field(default_factory=list)
    level: Level | None = None
    # Où elle a servi : « stage chez Logistica », « projet TrafficLens », « cours »…
    evidence: str = ""
    source: Source = "manuel"
    status: Status = "validé"


class LibraryExperience(_Model):
    """Une expérience et sa réserve de puces : toutes les puces vraies, pas
    seulement celles du CV. Le ciblage choisit les plus utiles à chaque offre."""

    id: str
    title: str
    place: str = ""
    dates: str = ""
    bullets: list[str] = Field(default_factory=list)
    source: Source = "manuel"
    status: Status = "validé"


class Library(_Model):
    projects: list[LibraryProject] = Field(default_factory=list)
    skills: list[LibrarySkill] = Field(default_factory=list)
    experiences: list[LibraryExperience] = Field(default_factory=list)
