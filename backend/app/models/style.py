"""La forme d'un CV (style.json) : polices, tailles, couleurs, espaces, photo.

Les valeurs par défaut sont celles du CV de base : un ``CVStyle()`` vide le
reproduit. Les tailles sont en points (pt), les largeurs de colonne en part de
la largeur du texte.

Une couleur s'écrit soit avec le nom d'une couleur de la palette
(``"primary"``), soit en hexadécimal sur six chiffres (``"001F82"``).
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_HEX = re.compile(r"^[0-9A-Fa-f]{6}$")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextStyle(_Model):
    """La mise en forme d'un type de bloc.

    ``size`` vide : la taille du texte courant. ``leading`` vide : 1,2 fois la
    taille. ``color`` vide : la couleur du texte.
    """

    size: float | None = Field(default=None, gt=0, le=72)
    leading: float | None = Field(default=None, gt=0, le=90)
    bold: bool = False
    italic: bool = False
    color: str | None = None
    uppercase: bool = False
    # Espace ajouté entre les lettres, en % de la taille de la police.
    letter_spacing: float = Field(default=0, ge=-10, le=50)
    # Identifiant d'une famille de fonts/ ; vide = la police principale.
    font: str | None = None


def _bold(**kw: object) -> TextStyle:
    return TextStyle(bold=True, **kw)  # type: ignore[arg-type]


class Blocks(_Model):
    """Un réglage par type de bloc du CV."""

    name: TextStyle = Field(default_factory=lambda: _bold(size=24.88, leading=30, color="primary"))
    headline: TextStyle = Field(default_factory=lambda: _bold(size=12, leading=14, color="primary"))
    summary: TextStyle = Field(default_factory=TextStyle)
    contact_label: TextStyle = Field(default_factory=_bold)
    contact_strong: TextStyle = Field(default_factory=_bold)
    contact_value: TextStyle = Field(default_factory=TextStyle)
    section_title: TextStyle = Field(
        default_factory=lambda: _bold(size=13, leading=15.5, color="primary")
    )
    entry_title: TextStyle = Field(default_factory=_bold)
    skill_label: TextStyle = Field(default_factory=_bold)
    language_name: TextStyle = Field(default_factory=_bold)
    experience_title: TextStyle = Field(default_factory=lambda: _bold(size=11, leading=13.5))
    experience_tag: TextStyle = Field(
        default_factory=lambda: TextStyle(size=10, leading=12, italic=True)
    )
    experience_place: TextStyle = Field(default_factory=lambda: TextStyle(size=11, leading=13.5))
    project_title: TextStyle = Field(default_factory=_bold)
    project_tag: TextStyle = Field(
        default_factory=lambda: TextStyle(size=9, leading=11, italic=True)
    )
    date: TextStyle = Field(default_factory=lambda: _bold(italic=True))
    date_in_place: TextStyle = Field(
        default_factory=lambda: _bold(size=10, leading=12, italic=True)
    )
    body: TextStyle = Field(default_factory=TextStyle)


class Palette(_Model):
    """Les rôles de couleur du CV ; chaque élément en prend un (ou une couleur libre)."""

    primary: str = "001F82"
    secondary: str = "4F6B8A"
    text: str = "000000"
    accent: str = "2E7D32"
    band: str = "ECF3FB"
    # Texte discret : dates, lieux, mentions.
    muted: str = "5B6472"
    # Le fond des titres de rubrique présentés en bandeau.
    title_band: str = "E3EAF6"
    link: str = "1F4FA3"

    @field_validator("*")
    @classmethod
    def _hex(cls, value: str) -> str:
        if not _HEX.match(value):
            raise ValueError(f"couleur hexadécimale attendue sur six chiffres, reçu {value!r}")
        return value.upper()


class Fonts(_Model):
    # Identifiant d'une famille de fonts/ (nom du dossier).
    main: str = "Lato"
    # Les ligatures (« ﬁ » en un seul signe) gênent la lecture des ATS.
    ligatures: bool = False
    # Chiffres proportionnels (« 16 » plus étroit que « 35 »), comme le CV
    # d'origine ; « tabular » les aligne en colonnes.
    figures: Literal["proportional", "tabular"] = "proportional"


class Page(_Model):
    margin_cm: float = Field(default=1.0, gt=0, le=4)
    base_size: Literal[10, 11, 12] = 10
    parskip_pt: float = 3
    line_spread: float = Field(default=1.0, gt=0.5, le=2)


class Photo(_Model):
    visible: bool = True
    shape: Literal["square", "rounded", "circle"] = "square"
    position: Literal["right", "left"] = "right"
    # « match_text » : côté du carré = hauteur du bloc de texte à côté.
    size_mode: Literal["match_text", "fixed"] = "match_text"
    size_cm: float = Field(default=3.0, gt=0, le=10)
    offset_x_pt: float = 0
    offset_y_pt: float = 0
    border_pt: float = Field(default=0, ge=0, le=10)
    border_color: str = "primary"
    corner_radius_pt: float = Field(default=6, ge=0, le=50)


class HeaderLayout(_Model):
    # « center » : nom, titre, accroche et coordonnées centrés.
    align: Literal["left", "center"] = "left"
    # Où vont la photo et les coordonnées : en haut sur toute la largeur (« top »), ou en
    # tête d'une colonne (« left », « right ») avec le nom en tête de l'autre (un CV fait
    # sous Canva). Deux colonnes seulement.
    placement: Literal["top", "left", "right"] = "top"
    # L'accroche dans la colonne de la photo, sous ce titre (sinon sous le nom).
    summary_side: bool = False
    summary_title: str = Field(default="PROFIL", max_length=60)
    # Un fond coloré derrière tout l'en-tête, du haut de la page (CV faits sous Canva) ;
    # None : pas de fond. Le texte posé dessus prend ``fill_text_color``.
    fill_color: str | None = None
    fill_text_color: str = "FFFFFF"
    fill_padding_pt: float = Field(default=14, ge=0, le=60)
    text_width: float = Field(default=0.78, gt=0.2, le=1)
    name_gap_pt: float = 12
    headline_gap_pt: float = 7
    rule_visible: bool = True
    rule_before_pt: float = 6
    rule_after_pt: float = 2
    rule_thickness_pt: float = 0.4
    rule_color: str = "primary"
    contact_separator: str = "|"
    after_contact_pt: float = 10


class Columns(_Model):
    # « one » : les rubriques l'une sous l'autre, sur toute la largeur, dans
    # l'ordre du contenu (la colonne de chaque rubrique est alors ignorée).
    layout: Literal["two", "one"] = "two"
    left_width: float = Field(default=0.41, gt=0.1, lt=0.9)
    right_width: float = Field(default=0.55, gt=0.1, lt=0.9)
    # Les deux colonnes prennent toute la hauteur restante : l'espace libre se
    # répartit entre les rubriques et les entrées.
    fill_page: bool = True
    bottom_safety_pt: float = 4


class Band(_Model):
    """Le fond coloré d'une colonne, du haut de la colonne au bas de la page."""

    visible: bool = True
    color: str = "band"
    column: Literal["left", "right"] = "left"
    top_offset_pt: float = 14
    # Le texte et les titres posés sur le fond (du blanc sur un fond sombre) ; None : comme
    # ailleurs.
    text_color: str | None = None
    title_color: str | None = None


class SectionTitles(_Model):
    """Présentation des titres de rubrique.

    ``rule`` : titre puis filet (réglages du filet dans ``spacing``) ;
    ``band`` : titre dans un bandeau coloré ; ``plain`` : titre seul.
    """

    variant: Literal["rule", "band", "plain"] = "rule"
    band_color: str = "primary"
    # Couleur du texte dans le bandeau (remplace celle du bloc section_title).
    band_text_color: str = "FFFFFF"
    band_radius_pt: float = Field(default=3, ge=0, le=20)
    band_padding_pt: float = Field(default=3, ge=0, le=20)


class SummaryFrame(_Model):
    """Cadre autour de l'accroche."""

    visible: bool = False
    border_pt: float = Field(default=0.6, ge=0, le=5)
    border_color: str = "primary"
    background_color: str | None = None
    radius_pt: float = Field(default=4, ge=0, le=30)
    padding_pt: float = Field(default=6, ge=0, le=30)


class Spacing(_Model):
    section_gap_pt: float = 12
    section_stretch: float = 2
    entry_gap_pt: float = 7
    entry_stretch: float = 1
    skill_gap_pt: float = 5
    skill_stretch: float = 0.5
    title_rule_gap_pt: float = 2
    title_rule_visible: bool = True
    title_rule_thickness_pt: float = 0.4
    title_rule_color: str = "primary"
    after_title_pt: float = 7
    place_gap_pt: float = 3


class ListSpacing(_Model):
    itemsep_pt: float = 1.5
    itemsep_stretch_pt: float = 0
    topsep_pt: float = 2
    topsep_stretch_pt: float = 0


class Lists(_Model):
    leftmargin_pt: float = 12
    labelsep_pt: float = 5
    # Symbole des puces (listes et grilles) et sa couleur (vide : celle du texte).
    bullet: Literal["bullet", "dash", "square", "chevron"] = "bullet"
    bullet_color: str | None = None
    left: ListSpacing = Field(default_factory=ListSpacing)
    right: ListSpacing = Field(
        default_factory=lambda: ListSpacing(
            itemsep_pt=4, itemsep_stretch_pt=1, topsep_pt=4, topsep_stretch_pt=1
        )
    )


class Grid(_Model):
    arraystretch: float = 1.15
    first_col: float = 0.46
    gap: float = 0.04
    second_col: float = 0.5


class Links(_Model):
    # Cadres de couleur autour des liens, visibles à l'écran seulement
    # (réglage par défaut de hyperref, gardé pour le CV de base).
    hide_boxes: bool = False
    # La couleur du texte des liens (vide : celle du texte qui l'entoure, avec les cadres).
    color: str | None = None


def palette_color(role: str) -> str:
    """Le nom LaTeX d'un rôle de palette : « title_band » → « cvtitleband » (pas de _)."""
    return "cv" + role.replace("_", "")


class CVStyle(_Model):
    schema_version: int = 1
    fonts: Fonts = Field(default_factory=Fonts)
    palette: Palette = Field(default_factory=Palette)
    page: Page = Field(default_factory=Page)
    blocks: Blocks = Field(default_factory=Blocks)
    photo: Photo = Field(default_factory=Photo)
    header: HeaderLayout = Field(default_factory=HeaderLayout)
    columns: Columns = Field(default_factory=Columns)
    band: Band = Field(default_factory=Band)
    section_titles: SectionTitles = Field(default_factory=SectionTitles)
    summary_frame: SummaryFrame = Field(default_factory=SummaryFrame)
    spacing: Spacing = Field(default_factory=Spacing)
    lists: Lists = Field(default_factory=Lists)
    grid: Grid = Field(default_factory=Grid)
    links: Links = Field(default_factory=Links)

    def color_name(self, value: str | None) -> str | None:
        """Le nom de couleur LaTeX pour une couleur de palette ou un hexadécimal."""
        if value is None:
            return None
        if value in Palette.model_fields:
            return palette_color(value)
        if _HEX.match(value):
            return f"cvhex{value.upper()}"
        raise ValueError(f"couleur inconnue : {value!r} (nom de palette ou hexadécimal)")

    def extra_colors(self) -> list[str]:
        """Les couleurs hexadécimales utilisées hors palette, à déclarer."""
        found: set[str] = set()

        def visit(node: object) -> None:
            if isinstance(node, BaseModel):
                for name in type(node).model_fields:
                    value = getattr(node, name)
                    if (name == "color" or name.endswith("_color")) and isinstance(value, str):
                        if _HEX.match(value) and value not in Palette.model_fields:
                            found.add(value.upper())
                    visit(value)

        visit(self)
        return sorted(found)
