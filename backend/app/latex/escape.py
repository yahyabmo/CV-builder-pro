"""Échappement du texte avant son entrée dans le .tex.

Tout texte venant du contenu passe par ici : un « & » ou un « % » laissé brut
casse la compilation ou fait disparaître la fin d'une ligne sans erreur.
"""

import re

# Remplacements faits caractère par caractère : un remplacement ne doit pas être
# ré-échappé par un autre (le « \ » de « \& » par exemple).
_SPECIAL = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

# Marques en ligne du contenu : **gras** et __italique__ (doubles, pour ne pas
# confondre avec « A* » ou un nom_de_variable).
_MARK = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")


def escape(text: str) -> str:
    """Le texte, littéral en LaTeX."""
    return "".join(_SPECIAL.get(char, char) for char in text)


def rich(text: str) -> str:
    """Le texte échappé, avec **gras** et __italique__ convertis."""
    parts: list[str] = []
    position = 0
    for match in _MARK.finditer(text):
        parts.append(escape(text[position : match.start()]))
        if match.group(1) is not None:
            parts.append(r"\textbf{" + escape(match.group(1)) + "}")
        else:
            parts.append(r"\textit{" + escape(match.group(2)) + "}")
        position = match.end()
    parts.append(escape(text[position:]))
    return "".join(parts)


def escape_url(url: str) -> str:
    """Une adresse pour le premier argument de ``\\href``.

    hyperref lit l'adresse presque telle quelle : « # » et « % » sont protégés,
    l'antislash et les accolades sont encodés comme dans une URL ; « _ » et
    « ~ » restent tels quels.
    """
    for char, code in (("\\", "%5C"), ("{", "%7B"), ("}", "%7D")):
        url = url.replace(char, code)
    return url.replace("%", r"\%").replace("#", r"\#")
