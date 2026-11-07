import pytest

from app.latex.escape import escape, escape_url, rich


@pytest.mark.parametrize(
    ("raw", "latex"),
    [
        ("R&D", r"R\&D"),
        ("100%", r"100\%"),
        ("$5", r"\$5"),
        ("C#", r"C\#"),
        ("snake_case", r"snake\_case"),
        ("{a}", r"\{a\}"),
        ("~/bin", r"\textasciitilde{}/bin"),
        ("x^2", r"x\textasciicircum{}2"),
        ("a\\b", r"a\textbackslash{}b"),
        ("A*, Minimax", "A*, Minimax"),
        ("Élève — l'École", "Élève — l'École"),
    ],
)
def test_escape(raw: str, latex: str) -> None:
    assert escape(raw) == latex


def test_escape_does_not_double_escape() -> None:
    # Le « \ » ajouté pour « & » ne doit pas être ré-échappé.
    assert escape("\\&") == r"\textbackslash{}\&"


def test_rich_marks() -> None:
    assert rich("5e année, **IA & Data**.") == r"5e année, \textbf{IA \& Data}."
    assert rich("__en cours__") == r"\textit{en cours}"
    assert rich("A* et B*") == "A* et B*"
    assert rich("un_nom et __vraiment__") == r"un\_nom et \textit{vraiment}"


def test_escape_url() -> None:
    assert escape_url("https://x.org/a_b~c#top?q=100%") == r"https://x.org/a_b~c\#top?q=100\%"
    assert escape_url("https://x.org/{id}") == r"https://x.org/\%7Bid\%7D"
