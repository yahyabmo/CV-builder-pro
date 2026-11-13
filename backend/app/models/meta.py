"""Les métadonnées d'un CV (meta.json) : nom, origine, dates, mode, suivi de la candidature."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.application import Application


def now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class CVMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: Literal["base", "cv"] = "cv"
    # « manual » : le .tex a été modifié à la main et devient la source.
    mode: Literal["visual", "manual"] = "visual"
    # Un CV cloné (clone.json gardé à côté) : « clone » prend la forme du PDF d'origine,
    # « app » la mise en page de l'appli et son style ; on passe de l'une à l'autre.
    shape: Literal["clone", "app"] = "clone"
    source: str | None = None
    # Renseignés pour un CV ciblé (phase 5) : l'offre visée.
    company: str | None = None
    position: str | None = None
    offer_url: str | None = None
    # 1 à 3 mots qui résument l'offre, pour le nom du fichier téléchargé.
    label: str | None = None
    # Couverture des mots-clés de l'offre (sur 100), mesurée sur le PDF.
    score: int | None = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
    pages: int | None = None
    # Version classique encore fictive : l'accueil propose d'importer ou de saisir son CV.
    welcome: bool = False
    # Pour un CV ciblé : où en est la candidature.
    application: Application = Field(default_factory=Application)
