"""Le contenu d'un CV (content.json) : ce qui est écrit, sans la mise en forme.

Le texte peut porter deux marques en ligne, converties au rendu :
``**gras**`` et ``__italique__``. Tout le reste est du texte brut, échappé pour
LaTeX au rendu (voir ``app.latex.escape``).

Une section a un ``kind`` qui décide de sa structure et de son rendu. L'ordre
des sections dans la liste est leur ordre dans la colonne.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    # Une faute de frappe dans un fichier JSON doit se voir, pas disparaître.
    model_config = ConfigDict(extra="forbid")


class ContactItem(_Model):
    """Un élément d'une ligne de coordonnées.

    Avec ``label`` : « **Téléphone :** 06 00… ». Sans ``label`` et avec
    ``bold`` : le texte entier en gras (« **Bordeaux, France** »).
    """

    text: str
    label: str | None = None
    url: str | None = None
    bold: bool = False


class Header(_Model):
    name: str
    headline: str
    summary: str
    photo: str | None = "photo.jpg"
    contact_lines: list[list[ContactItem]] = Field(default_factory=list)


class _SectionBase(_Model):
    id: str
    title: str
    column: Literal["left", "right"]
    visible: bool = True


class EducationItem(_Model):
    title: str
    place: str
    dates: str
    description: str = ""


class EducationSection(_SectionBase):
    kind: Literal["education"] = "education"
    items: list[EducationItem] = Field(default_factory=list)


class SkillGroup(_Model):
    label: str
    text: str


class SkillsSection(_SectionBase):
    kind: Literal["skills"] = "skills"
    items: list[SkillGroup] = Field(default_factory=list)


class GridItem(_Model):
    """Une case de grille ; ``wide`` occupe toute la ligne."""

    text: str
    wide: bool = False


class GridSection(_SectionBase):
    kind: Literal["grid"] = "grid"
    items: list[GridItem] = Field(default_factory=list)


class Language(_Model):
    name: str
    level: str


class LanguagesSection(_SectionBase):
    kind: Literal["languages"] = "languages"
    items: list[Language] = Field(default_factory=list)


class BulletsSection(_SectionBase):
    kind: Literal["bullets"] = "bullets"
    items: list[str] = Field(default_factory=list)


class ExperienceItem(_Model):
    title: str
    tag: str = ""
    place: str
    dates: str
    bullets: list[str] = Field(default_factory=list)


class ExperienceSection(_SectionBase):
    """Expériences, ou activités du même type.

    ``detailed`` : intitulé et lieu dans la taille des expériences, sur deux
    paragraphes. ``compact`` : intitulé en gras à la taille du texte, lieu et
    date sur la ligne suivante (le travail associatif).
    """

    kind: Literal["experience"] = "experience"
    layout: Literal["detailed", "compact"] = "detailed"
    items: list[ExperienceItem] = Field(default_factory=list)


class ProjectItem(_Model):
    title: str
    tag: str = ""
    date: str
    description: str
    # Des puces sous la description (un CV importé qui détaille ses projets ainsi).
    bullets: list[str] = Field(default_factory=list)
    link: str | None = None
    library_id: str | None = None


class ProjectsSection(_SectionBase):
    kind: Literal["projects"] = "projects"
    items: list[ProjectItem] = Field(default_factory=list)


Section = Annotated[
    EducationSection
    | SkillsSection
    | GridSection
    | LanguagesSection
    | BulletsSection
    | ExperienceSection
    | ProjectsSection,
    Field(discriminator="kind"),
]


class CVContent(_Model):
    schema_version: int = 1
    language: Literal["fr", "en"] = "fr"
    header: Header
    sections: list[Section] = Field(default_factory=list)

    def column(self, side: Literal["left", "right"]) -> list[Section]:
        """Les sections visibles d'une colonne, dans leur ordre."""
        return [s for s in self.sections if s.column == side and s.visible]
