"""La mise en page ancrée d'un CV cloné (version 2) : ce que ``render`` écrit en LaTeX.

La page est découpée en « unités » : un champ du contenu (ou quelques champs qui
partagent une ligne, comme « Lyon | 06… | mail »), avec ses lignes exactes d'origine,
mot par mot. Au rendu, une unité dont le texte n'a pas changé est posée telle quelle, à
sa place ; une unité modifiée coule dans sa largeur et décale ce qui la suit dans sa
colonne. Les formes et images qui l'accompagnent (puce dessinée, filet de titre, icône)
la suivent.

Tout est en points, depuis le coin haut gauche de chaque page.
"""

from typing import Literal

from pydantic import BaseModel, Field

Box = tuple[float, float, float, float]


class Ink(BaseModel):
    """Un style de texte : police (identifiant de l'appli), taille, couleur."""

    font: str
    size: float
    color: str = "000000"
    bold: bool = False
    italic: bool = False
    # Blanc ajouté entre deux lettres, en points.
    tracking: float = 0.0
    # Le texte d'origine est en capitales mais pas le contenu : l'écrire en capitales.
    upper: bool = False


class Glyph(BaseModel):
    """Un mot posé : son texte, son bord gauche et sa largeur d'origine, son style."""

    t: str
    x: float
    w: float
    i: int
    # Décalage de sa ligne de base (exposant, indice).
    dy: float = 0.0
    u: str | None = None


class Row(BaseModel):
    """Une ligne exacte d'une unité : sa ligne de base (depuis celle de l'unité) et ses mots."""

    y: float
    words: list[Glyph] = Field(default_factory=list)


class Part(BaseModel):
    """Un morceau d'unité : un champ du contenu (``path``) ou un texte fixe (séparateur)."""

    path: str | None = None
    text: str = ""
    ink: int = 0
    # Le lien d'origine (coordonnées) : le champ l'a dans le contenu, sinon il reste ici.
    url: str | None = None


class Unit(BaseModel):
    id: int
    page: int
    # Première ligne de base, et décalage de la dernière.
    y: float
    end: float = 0.0
    # La boîte où le texte coule quand il change : bord gauche, bord droit.
    x0: float
    x1: float
    # Retrait de la première ligne (une puce tenue dans la marge, un titre décalé).
    indent: float = 0.0
    align: Literal["left", "right", "center"] = "left"
    leading: float = 12.0
    ascent: float = 10.0
    rows: list[Row] = Field(default_factory=list)
    parts: list[Part] = Field(default_factory=list)
    # Le signe de puce, à sa place d'origine (ligne de base de la première ligne).
    marker: Glyph | None = None
    # Le texte de chaque champ au moment du clonage : inchangé → posé tel quel.
    original: dict[str, str] = Field(default_factory=dict)
    lanes: list[int] = Field(default_factory=list)
    # Écart depuis la dernière ligne de base de l'unité précédente de sa colonne.
    gap: float = 0.0
    # « title », « field », « bullet », « list », « header », « contact », « label ».
    role: str = "field"
    section: str | None = None
    item: int | None = None
    bullet: int | None = None
    # Une liste écrite à la suite (« Python, Java, SQL ») : ses éléments et leur séparateur.
    items: list[int] = Field(default_factory=list)
    joiner: str = ", "
    # Le repère du clic sur l'aperçu (``%@ …``).
    mark: str = "none"


class Paint(BaseModel):
    """Une forme : fond, bandeau, filet, pastille, icône dessinée."""

    page: int
    kind: Literal["rect", "ellipse", "line", "path"]
    box: Box
    fill: str | None = None
    stroke: str | None = None
    width: float = 0.0
    radius: float = 0.0
    path: str = ""
    even_odd: bool = False
    # Un dégradé : son sens (« h », « v »), puis ses couleurs du début à la fin.
    shade: list[str] | None = None
    # L'unité qu'elle suit (et qui l'emporte si elle disparaît) ; ``exact`` : seulement
    # quand l'unité est inchangée (un fond derrière un mot précis).
    unit: int | None = None
    exact: bool = False


class Picture(BaseModel):
    page: int
    box: Box
    file: str
    shape: Literal["circle", "rounded", "square"] = "square"
    unit: int | None = None
    exact: bool = False


class Link(BaseModel):
    """Un lien posé sur la page sans texte dessous (une icône) : il reste à sa place."""

    page: int
    box: Box
    url: str
    unit: int | None = None


class Photo(BaseModel):
    page: int = 1
    box: Box
    shape: Literal["circle", "rounded", "square"] = "square"


class ItemPlan(BaseModel):
    units: list[int] = Field(default_factory=list)
    bullets: list[int] = Field(default_factory=list)


class SectionPlan(BaseModel):
    title: int | None = None
    items: list[ItemPlan] = Field(default_factory=list)


class PageSize(BaseModel):
    width: float
    height: float


class AnchoredLayout(BaseModel):
    version: Literal[2] = 2
    pages: list[PageSize]
    inks: list[Ink] = Field(default_factory=list)
    units: list[Unit] = Field(default_factory=list)
    paints: list[Paint] = Field(default_factory=list)
    pictures: list[Picture] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    photo: Photo | None = None
    lanes: list[list[tuple[float, float]]] = Field(default_factory=list)
    sections: dict[str, SectionPlan] = Field(default_factory=dict)
    # L'ordre des champs d'en-tête et de coordonnées : leurs unités.
    header: dict[str, int] = Field(default_factory=dict)
    # Polices reprises : famille du PDF → (identifiant, « identique », « mêmes largeurs »
    # ou « proche »).
    fonts: dict[str, tuple[str, str]] = Field(default_factory=dict)
    # Le style de base pour ce qui n'existait pas sur la page (une rubrique ajoutée).
    body: int = 0
    title_ink: int | None = None

    def unit(self, unit_id: int) -> Unit:
        return self.units[unit_id]
