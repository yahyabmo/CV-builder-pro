"""Les formes des réponses de l'API."""

from typing import Literal

from pydantic import BaseModel

from app.models.content import CVContent
from app.models.meta import CVMeta
from app.models.style import CVStyle
from app.services.cuts import Cut


class CVSummary(BaseModel):
    slug: str
    meta: CVMeta
    pdf_version: int | None
    # Nom du fichier téléchargé, sans extension : « camille_laurent_agent-ia ».
    file_stem: str
    # Les mots de l'offre dans ce nom (« agent-ia »), vide s'il n'y en a pas.
    file_label: str = ""
    # L'offre visée : lieu et contrat, tirés de son analyse.
    location: str = ""
    contract: str = ""
    # Une relance à faire aujourd'hui.
    due: bool = False


class CVDetail(CVSummary):
    content: CVContent
    style: CVStyle
    # Le CV a une forme clonée de son PDF d'origine (clone.json) ; ``shape`` dit laquelle des
    # deux formes il prend (l'onglet Style ne s'applique qu'à « app »).
    cloned: bool = False
    shape: Literal["clone", "app"] = "clone"


class ShapeIn(BaseModel):
    shape: Literal["clone", "app"]


class LatexErrorOut(BaseModel):
    message: str
    line: int | None
    context: str


class CompileOut(BaseModel):
    ok: bool
    superseded: bool = False
    pages: int | None = None
    seconds: float = 0
    overflow_pt: float = 0
    pdf_version: int | None = None
    errors: list[LatexErrorOut] = []
    # Coupes proposées quand une colonne déborde.
    cuts: list[Cut] = []
