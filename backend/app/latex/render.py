"""Du contenu et du style au .tex.

Le template (``templates/cv.tex.j2``) utilise des délimiteurs Jinja2 adaptés
au LaTeX, pour ne pas entrer en conflit avec les accolades :

- ``\\VAR{expression}`` : une valeur ;
- ``\\BLOCK{instruction}`` : ``if``, ``for``, ``macro``… ;
- ``\\#{commentaire}``.

Le texte du contenu n'entre jamais brut : il passe par ``e`` (échappé) ou
``rich`` (échappé, avec **gras** et __italique__).
"""

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app import fonts
from app.latex.escape import escape, escape_url, rich
from app.models.content import CVContent, GridItem
from app.models.style import CVStyle, Palette, TextStyle, palette_color

_TEMPLATES = Path(__file__).parent / "templates"


def pt(value: float) -> str:
    """Un nombre pour LaTeX : « 12 » plutôt que « 12.0 », « 1.5 » sinon."""
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def mark(*parts: object) -> str:
    """Un repère du .tex, sur sa propre ligne : « %@ item experience 0 ».

    Un clic sur l'aperçu donne une ligne du .tex (SyncTeX) ; le repère qui la
    précède dit à quelle rubrique et à quel élément elle appartient.
    """
    return "%@ " + " ".join(re.sub(r"[^\w-]", "", str(part)) for part in parts)


class _Helpers:
    """Les fonctions données au template, liées au style du CV."""

    def __init__(self, style: CVStyle) -> None:
        self.style = style

    def color(self, value: str | None) -> str:
        name = self.style.color_name(value)
        if name is None:
            raise ValueError("couleur manquante")
        return name

    def size(self, block: TextStyle) -> str:
        """``\\fontsize{…}{…}\\selectfont`` si le bloc a une taille, sinon rien."""
        if block.size is None:
            return ""
        leading = block.leading if block.leading is not None else block.size * 1.2
        return rf"\fontsize{{{pt(block.size)}}}{{{pt(leading)}}}\selectfont "

    def fmt(self, block: TextStyle, latex: str) -> str:
        """Le texte (déjà en LaTeX) avec graisse, italique, couleur, casse."""
        inner = latex
        if block.uppercase:
            inner = rf"\MakeUppercase{{{inner}}}"
        if block.color is not None:
            colored = rf"\color{{{self.color(block.color)}}}{inner}"
            inner = colored if (block.bold or block.italic) else "{" + colored + "}"
        if block.italic:
            inner = rf"\textit{{{inner}}}"
        if block.bold:
            inner = rf"\textbf{{{inner}}}"
        features = []
        if block.font and block.font != self.style.fonts.main:
            features.append(font_command(fonts.get(block.font).id))
        if block.letter_spacing:
            features.append(rf"\addfontfeatures{{LetterSpace={pt(block.letter_spacing)}}}")
        if features:
            inner = "{" + "".join(features) + inner + "}"
        return inner

    def fmt_in(self, block: TextStyle, latex: str, color: str) -> str:
        """Comme ``fmt``, avec une autre couleur (texte d'un bandeau)."""
        return self.fmt(block.model_copy(update={"color": color}), latex)

    def glue(self, base: float, stretch: float) -> str:
        """Un espace extensible quand les colonnes remplissent la page."""
        if self.style.columns.fill_page and stretch:
            return f"{pt(base)}pt plus {pt(stretch)}fil"
        return f"{pt(base)}pt"

    def bullet(self) -> str:
        """Le symbole des puces, coloré si demandé."""
        lists = self.style.lists
        symbol = _BULLETS[lists.bullet]
        if lists.bullet_color:
            return rf"\textcolor{{{self.color(lists.bullet_color)}}}{{{symbol}}}"
        return symbol

    def stretch(self, base: float, stretch_pt: float) -> str:
        return f"{pt(base)}pt plus {pt(stretch_pt)}pt" if stretch_pt else f"{pt(base)}pt"

    def photo(self, filename: str) -> str:
        """La photo dans sa boîte (de largeur ``\\linewidth``) : forme, bordure, décalage.

        Carrée sans bordure, c'est un simple ``\\includegraphics`` (le CV de
        base). Sinon, l'image est centrée et découpée par TikZ.
        """
        p = self.style.photo
        lines = []
        if p.offset_y_pt:
            lines.append(rf"\vspace{{{pt(p.offset_y_pt)}pt}}")
        shift = rf"\hspace*{{{pt(p.offset_x_pt)}pt}}" if p.offset_x_pt else ""
        image = rf"\includegraphics[width=\linewidth]{{{filename}}}"
        if p.shape == "square" and not p.border_pt:
            return "\n    ".join([*lines, shift + image])
        if p.shape == "circle":
            options, path = "", r"(0.5\linewidth,0.5\linewidth) circle [radius=0.5\linewidth]"
        else:
            radius = p.corner_radius_pt if p.shape == "rounded" else 0
            options = f"[rounded corners={pt(radius)}pt]" if radius else ""
            path = r"(0,0) rectangle (\linewidth,\linewidth)"
        picture = (
            r"\begin{tikzpicture}\begin{scope}"
            rf"\clip{options} {path};"
            r"\node[anchor=center,inner sep=0pt] at (0.5\linewidth,0.5\linewidth) "
            rf"{{{image}}};\end{{scope}}"
        )
        if p.border_pt:
            picture += (
                rf"\draw[line width={pt(p.border_pt)}pt,{self.color(p.border_color)}]"
                rf"{options} {path};"
            )
        picture += r"\end{tikzpicture}"
        return "\n    ".join([*lines, shift + picture])


_BULLETS = {
    "bullet": r"\textbullet",
    "dash": r"\textendash",
    "square": r"\raisebox{0.18ex}{\rule{0.32em}{0.32em}}",
    "chevron": "›",
}


def lines(*parts: str) -> str:
    """Les lignes non vides, séparées par ``\\\\``.

    Un champ vide (établissement d'une formation non renseigné, par exemple) ne laisse
    pas de ``\\\\`` seul sur sa ligne : LaTeX refuserait de compiler (« There's no line
    here to end »).
    """
    return "\\\\\n".join(part for part in parts if part.strip())


def grid_rows(items: list[GridItem]) -> list[tuple[str, ...]]:
    """Les lignes d'une grille à deux cases ; une case large prend la ligne."""
    rows: list[tuple[str, ...]] = []
    pending: list[str] = []
    for item in items:
        if item.wide:
            if pending:
                rows.append(("single", pending.pop()))
            rows.append(("wide", item.text))
        else:
            pending.append(item.text)
            if len(pending) == 2:
                rows.append(("pair", pending[0], pending[1]))
                pending = []
    if pending:
        rows.append(("single", pending[0]))
    return rows


def font_command(font_id: str) -> str:
    """La commande LaTeX d'une famille secondaire (identifiant en lettres seules)."""
    return rf"\cvfont{font_id}"


def font_specs(style: CVStyle) -> tuple[dict[str, str], list[dict[str, str]]]:
    """La police principale, puis les autres familles utilisées par des blocs."""

    def spec(font_id: str) -> dict[str, str]:
        family = fonts.get(font_id)
        return {
            "id": family.id,
            "prefix": family.prefix,
            "path": family.folder.as_posix() + "/",
            "command": font_command(family.id),
        }

    main = spec(style.fonts.main)
    used = {
        getattr(style.blocks, name).font
        for name in type(style.blocks).model_fields
        if getattr(style.blocks, name).font
    }
    used.discard(style.fonts.main)
    return main, [spec(font_id) for font_id in sorted(used)]


def environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATES),
        block_start_string=r"\BLOCK{",
        block_end_string="}",
        variable_start_string=r"\VAR{",
        variable_end_string="}",
        comment_start_string=r"\#{",
        comment_end_string="}",
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )
    env.globals.update(
        e=escape, rich=rich, url=escape_url, pt=pt, grid_rows=grid_rows, mark=mark, lines=lines
    )
    return env


def render(content: CVContent, style: CVStyle) -> str:
    """Le .tex complet du CV."""
    helpers = _Helpers(style)
    main_font, extra_fonts = font_specs(style)
    template = environment().get_template("cv.tex.j2")
    palette = [(palette_color(name), getattr(style.palette, name)) for name in Palette.model_fields]
    tex = template.render(
        c=content,
        s=style,
        b=style.blocks,
        sp=style.spacing,
        h=helpers,
        palette=palette,
        extra_colors=style.extra_colors(),
        font=main_font,
        extra_fonts=extra_fonts,
        left=content.column("left"),
        right=content.column("right"),
        single=[s for s in content.sections if s.visible],
    )
    # Une couleur libre n'est déclarée que si le document s'en sert (le blanc
    # du texte des bandeaux, par exemple, n'existe pas sans bandeau).
    for hex_code in style.extra_colors():
        name = f"cvhex{hex_code}"
        if tex.count(name) == 1:
            tex = tex.replace(rf"\definecolor{{{name}}}{{HTML}}{{{hex_code}}}" + "\n", "")
    return tex
