"""Le .tex de la lettre de motivation : son contenu, plus le haut du CV."""

from app import fonts
from app.latex.escape import escape, escape_url
from app.latex.render import environment
from app.models.content import CVContent
from app.models.letter import LetterContent
from app.models.style import CVStyle

# La police de la lettre : Lato, comme le CV de base.
FONT = "Lato"


def _contacts(content: CVContent) -> str:
    """Les coordonnées utiles à une lettre, ligne par ligne comme sur le CV :
    ville, téléphone, liens.

    « Permis B » ou la mobilité restent sur le CV.
    """
    lines = []
    city = False
    for line in content.header.contact_lines:
        parts = []
        for item in line:
            text = escape(item.text)
            if item.url:
                parts.append(rf"\href{{{escape_url(item.url)}}}{{{text}}}")
            elif any(c.isdigit() for c in item.text):
                parts.append(text)
            elif not item.label and not city:
                # La ville seule : « Bordeaux, France » → « Bordeaux ».
                parts.append(escape(item.text.split(",")[0].strip()))
                city = True
        # Jamais de coupure au milieu d'une adresse : seulement entre deux éléments.
        if parts:
            lines.append(
                r"\hspace{0.4em}·\hspace{0.4em}".join(rf"\mbox{{{part}}}" for part in parts)
            )
    return "\\\\\n".join(lines)


def person_name(content: CVContent) -> str:
    """« CAMILLE LAURENT » → « Camille Laurent » (signature)."""
    name = content.header.name.strip()
    return name.title() if name.isupper() else name


# Selon le nombre de mots du corps : (au plus, taille du texte en pt, interligne).
# Une lettre courte grossit et s'aère ; une longue se resserre pour tenir sur la page.
_STEPS = ((150, 12, 1.15), (230, 11.5, 1.12), (300, 11, 1.08), (340, 11, 1.0))
_LONGEST = (10.5, 1.0)


def words(letter: LetterContent) -> int:
    """Les mots du corps : formule d'appel, paragraphes et formule de politesse."""
    return len(" ".join([letter.salutation, *letter.paragraphs, letter.closing]).split())


def layout(letter: LetterContent) -> dict[str, str]:
    """La taille du texte et l'interligne, selon la longueur de la lettre.

    Les écarts entre les blocs, eux, s'adaptent dans le gabarit : ils se
    partagent la hauteur libre de la page.
    """
    count = words(letter)
    size, leading = next(((s, lead) for limit, s, lead in _STEPS if count <= limit), _LONGEST)
    return {"size": f"{size:g}", "baseline": f"{size * 1.22:.1f}", "leading": f"{leading:g}"}


def render_letter(
    letter: LetterContent,
    content: CVContent,
    style: CVStyle,
    signature: dict[str, str] | None = None,
) -> str:
    """``signature`` : l'image sous le nom (``file`` à côté du .tex, ``height`` en cm)."""
    family = fonts.get(FONT)
    english = content.language == "en"
    template = environment().get_template("letter.tex.j2")
    return template.render(
        letter=letter,
        name=content.header.name,
        contacts=_contacts(content),
        primary=style.palette.primary,
        font={"prefix": family.prefix, "path": family.folder.as_posix() + "/"},
        english=english,
        subject_label="Subject" if english else "Objet",
        layout=layout(letter),
        signature=signature,
    )
