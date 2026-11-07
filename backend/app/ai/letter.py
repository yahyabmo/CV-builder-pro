"""La lettre de motivation : écrite par l'IA à partir de l'offre, du CV et des réponses.

Les règles (``rules.read("lettre")``) et les tournures à bannir
(``rules.read("tournures")``) se modifient dans Réglages. Après génération comme
après chaque retouche, ``checks`` signale ce qui sonne « IA », ce qui n'est pas
dans le profil, et une longueur hors de 200 à 380 mots.
"""

import re
import unicodedata
from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.ai import llm, targeting, usage_log
from app.ai.schemas import LetterDraft, OfferAnalysis
from app.latex.letter import person_name
from app.models.content import CVContent
from app.models.letter import LetterContent
from app.models.library import Library
from app.services import rules

MONTHS = (
    "janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split()
)
WORDS = (200, 380)
_FIRST_PERSON = re.compile(r"(?i)\b(je|j['’]|me|m['’]|moi|mon|ma|mes|i|my|me)\b")


class LetterCheck(BaseModel):
    kind: Literal["tournure", "profil", "longueur"]
    text: str


def city(content: CVContent) -> str:
    """La ville du CV : la première coordonnée sans libellé ni chiffre (« Bordeaux, France »)."""
    for line in content.header.contact_lines:
        for item in line:
            if (
                not item.label
                and not item.url
                and not any(c.isdigit() or c == "@" for c in item.text)
            ):
                return item.text.split(",")[0].strip()
    return ""


def place_date(content: CVContent, today: date | None = None) -> str:
    today = today or date.today()
    where = city(content)
    if content.language == "en":
        when = today.strftime("%-d %B %Y")
        return f"{where}, {when}" if where else when
    when = f"{'1er' if today.day == 1 else today.day} {MONTHS[today.month - 1]} {today.year}"
    return f"{where}, le {when}" if where else f"Le {when}"


def facts(content: CVContent, library: Library) -> str:
    """Ce que la bibliothèque sait de vrai en plus du CV : puces de réserve, compétences."""
    know = targeting.build_knowledge(content, library)
    pools = targeting.experience_pools(content, library)
    reserve = [f"- {pool.title} : {bullet}" for pool in pools for bullet in pool.reserve]
    return "\n".join([*reserve, "Compétences :", targeting.skills_text(know)])


async def generate(
    content: CVContent,
    library: Library,
    offer: str,
    analysis: OfferAnalysis,
    why: str,
    detail: str,
    provider: llm.LLMProvider,
) -> LetterContent:
    system, message = targeting.load_prompt(
        "lettre",
        rules=rules.as_text("lettre"),
        banned=", ".join(f"« {t} »" for t in rules.read("tournures")),
        language_name=targeting.LANG_NAME[content.language],
        offer=offer[:8000],
        analysis=targeting.analysis_text(analysis),
        profile=targeting.profile_text(content),
        facts=facts(content, library),
        why=why.strip(),
        detail=detail.strip(),
    )
    result = await llm.generate(provider, system, message, LetterDraft)
    usage_log.record(provider.name, result.model, result.usage, "Lettre de motivation")
    draft = result.data
    recipient = [line.strip() for line in draft.recipient if line.strip()][:3]
    return LetterContent(
        recipient=recipient or [analysis.company, analysis.location],
        place_date=place_date(content),
        subject=targeting.plain_marks("", draft.subject),
        salutation=draft.salutation.strip() or "Madame, Monsieur,",
        paragraphs=[targeting.plain_marks("", p) for p in draft.paragraphs if p.strip()],
        closing=draft.closing.strip() or LetterContent.model_fields["closing"].default,
        signature=person_name(content),
        why=why.strip(),
        detail=detail.strip(),
    )


def _fold(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text.replace("’", "'")).encode("ascii", "ignore").decode()
    return " ".join(plain.lower().split())


def words(letter: LetterContent) -> int:
    return sum(len(p.split()) for p in letter.paragraphs)


def checks(
    letter: LetterContent, content: CVContent, library: Library, analysis: OfferAnalysis | None
) -> list[LetterCheck]:
    out: list[LetterCheck] = []
    body = "\n".join([letter.subject, letter.salutation, *letter.paragraphs, letter.closing])
    folded = _fold(body)
    for phrase in rules.read("tournures"):
        if phrase == "—":
            if "—" in body:
                out.append(
                    LetterCheck(
                        kind="tournure",
                        text="Tiret cadratin (—) : remplace-le par une virgule ou un point.",
                    )
                )
        elif _fold(phrase) and _fold(phrase) in folded:
            out.append(
                LetterCheck(kind="tournure", text=f"Tournure qui sonne « IA » : « {phrase} ».")
            )
    if analysis is not None:
        # Seules les phrases où la personne parle d'elle comptent : décrire l'offre n'affirme rien.
        mine = [
            s
            for p in letter.paragraphs
            for s in re.split(r"(?<=[.!?])\s+", p)
            if _FIRST_PERSON.search(s)
        ]
        know = targeting.build_knowledge(content, library)
        extra = targeting.profile_text(content) + "\n" + facts(content, library)
        for term in targeting.new_terms("", "\n".join(mine), analysis, know, extra):
            out.append(
                LetterCheck(
                    kind="profil",
                    text=f"« {term} » : tu en parles à la première personne, mais ce n'est "
                    "pas dans ton profil. Vérifie que la phrase reste vraie.",
                )
            )
    count = words(letter)
    if letter.paragraphs and not WORDS[0] <= count <= WORDS[1]:
        out.append(
            LetterCheck(
                kind="longueur",
                text=f"{count} mots : vise entre {WORDS[0]} et {WORDS[1]}, "
                "pour tenir sur une page sans paraître vide.",
            )
        )
    return out
