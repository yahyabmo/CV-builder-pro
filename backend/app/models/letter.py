"""La lettre de motivation d'un CV ciblé (letter.json, à côté de content.json).

Le haut de la lettre (nom, coordonnées, couleur) vient du CV : il le suit
quand le CV change. Le reste est écrit ici, modifiable champ par champ.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LetterContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    # Le bloc destinataire, une ligne par élément (entreprise, équipe, ville).
    recipient: list[str] = Field(default_factory=list)
    place_date: str = ""
    subject: str = ""
    salutation: str = "Madame, Monsieur,"
    paragraphs: list[str] = Field(default_factory=list)
    closing: str = "Je vous prie d'agréer, Madame, Monsieur, mes salutations distinguées."
    signature: str = ""
    # L'image de signature de la personne (s'il y en a une) en bas de cette lettre.
    signature_image: bool = True
    # Les réponses de la personne avant la génération, gardées pour regénérer.
    why: str = ""
    detail: str = ""
    # « manual » : lettre.tex a été modifié à la main et devient la source.
    mode: Literal["visual", "manual"] = "visual"
