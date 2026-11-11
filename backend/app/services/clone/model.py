"""La mise en page d'un CV cloné : ce que le gabarit ``clone.tex.j2`` dessine.

Tout est en points, depuis le coin haut gauche de la page. Le contenu reste celui de
l'appli (``content.json``) : la mise en page dit seulement où et comment l'écrire.
"""

from typing import Literal

from pydantic import BaseModel, Field

Align = Literal["left", "center", "right"]


class Ink(BaseModel):
    """Un style de texte : police (identifiant de l'appli), taille, interligne, couleur."""

    font: str
    size: float
    leading: float
    color: str = "000000"
    bold: bool = False
    italic: bool = False
    upper: bool = False
    # Espacement des lettres, en % de la taille (LetterSpace de fontspec).
    tracking: float = 0.0
    # Petites capitales imitées : taille des petites lettres (0 : non).
    small: float = 0.0


class Paint(BaseModel):
    """Une forme fixe de la page : fond, bandeau, filet, pastille."""

    kind: Literal["rect", "ellipse", "line"]
    x0: float
    y0: float
    x1: float
    y1: float
    fill: str | None = None
    stroke: str | None = None
    width: float = 0.0
    radius: float = 0.0


class Photo(BaseModel):
    x: float
    y: float
    w: float
    h: float
    shape: Literal["circle", "rounded", "square"] = "square"


class Deco(BaseModel):
    """Ce qui accompagne un titre de rubrique."""

    kind: Literal["none", "rule", "band"] = "none"
    color: str = "000000"
    thickness: float = 0.5
    # Filet : écart entre le bas du texte et le filet. Bandeau : marge intérieure.
    gap: float = 2.0
    pad_y: float = 1.0
    # Largeur du filet ou du bandeau ; None : toute la largeur du cadre.
    width: float | None = None
    radius: float = 0.0
    align: Align = "left"
    # Bandeau : sa hauteur, la hauteur au-dessus de la ligne de base du titre, et son bord
    # gauche depuis le bord du cadre.
    height: float = 0.0
    above: float = 0.0
    offset: float = 0.0


class Row(BaseModel):
    """Une ligne d'une entrée (expérience, formation, projet) : champs à gauche et à droite."""

    left: list[str] = Field(default_factory=list)
    right: list[str] = Field(default_factory=list)
    sep: str = ", "


class Bullet(BaseModel):
    # « dot » : pastille dessinée ; « char » : un caractère (•, –, ▪) ; « none » : rien.
    kind: Literal["dot", "char", "none"] = "none"
    char: str = "•"
    size: float = 3.0
    color: str = "000000"
    # Retrait du texte depuis le bord du cadre, et place du signe avant le texte.
    indent: float = 0.0
    offset: float = 6.0
    # Hauteur du centre de la pastille au-dessus de la ligne de base, en points.
    raise_: float = 2.5


class Chip(BaseModel):
    fill: str | None = None
    stroke: str | None = None
    width: float = 0.6
    radius: float = 3.0
    pad_x: float = 4.0
    pad_y: float = 1.5
    gap: float = 3.0


class Look(BaseModel):
    """Comment une rubrique s'écrit : son titre, ses entrées, ses écarts."""

    id: str
    title: Ink | None = None
    title_align: Align = "left"
    # « gutter » : le titre dans la marge à gauche du contenu (Europass).
    title_mode: Literal["above", "gutter", "hidden"] = "above"
    gutter: float = 0.0
    # Décalage du titre depuis le bord du cadre (négatif : il dépasse à gauche).
    title_indent: float = 0.0
    deco: Deco = Field(default_factory=Deco)
    after_title: float = 4.0
    item_gap: float = 4.0
    # Les lignes d'une entrée, et l'écart avant les puces.
    rows: list[Row] = Field(default_factory=list)
    row_gap: float = 0.0
    # Avant la première puce, et entre deux puces (en plus de l'interligne).
    bullet_gap: float = 1.0
    bullet_space: float = 0.0
    inks: dict[str, Ink] = Field(default_factory=dict)
    bullet: Bullet = Field(default_factory=Bullet)
    # Compétences et langues : sur une ligne (« inline »), l'un sous l'autre (« stacked »),
    # libellé seul (« label »), pastilles (« tags »), liste à virgules (« list »), ou tous à
    # la suite dans un même paragraphe (« flow », aussi pour les listes et la grille).
    mode: Literal["inline", "stacked", "label", "tags", "list", "flow"] = "inline"
    sep: str = " : "
    # « flow » : après le texte d'un élément, et entre deux éléments.
    suffix: str = ""
    joiner: str = ", "
    chip: Chip | None = None
    columns: int = 1


class Block(BaseModel):
    """Un élément d'un cadre, dans l'ordre vertical : en-tête, rubrique ou libellé fixe."""

    kind: Literal["name", "headline", "summary", "contacts", "section", "label"]
    ref: str = ""
    # Espace au-dessus, en points (calé par mesure).
    gap: float = 0.0
    align: Align = "left"
    ink: Ink | None = None
    text: str = ""
    # Coordonnées : groupes d'indices par ligne, et séparateur.
    lines: list[list[int]] = Field(default_factory=list)
    sep: str = " · "
    # Le titre du CV ouvre la première ligne des coordonnées.
    with_headline: bool = False
    # Libellé dans la marge (Europass) : sa largeur et son style.
    gutter_text: str = ""
    gutter_ink: Ink | None = None
    gutter: float = 0.0


class Frame(BaseModel):
    x: float
    y: float
    w: float
    blocks: list[Block] = Field(default_factory=list)


class CloneLayout(BaseModel):
    width: float = 595.28
    height: float = 841.89
    paints: list[Paint] = Field(default_factory=list)
    photo: Photo | None = None
    frames: list[Frame] = Field(default_factory=list)
    looks: list[Look] = Field(default_factory=list)
    # Polices reprises : famille du PDF → (identifiant, et « identique », « mêmes largeurs »
    # ou « proche »).
    fonts: dict[str, tuple[str, str]] = Field(default_factory=dict)

    def look(self, section_id: str) -> Look | None:
        return next((look for look in self.looks if look.id == section_id), None)
