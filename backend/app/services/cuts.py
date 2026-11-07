"""Coupes proposées quand un CV ne tient plus sur une page.

Les colonnes ont une hauteur fixe : le texte en trop déborde en bas de la
colonne. Pour la colonne qui dépasse, on propose de retirer le dernier
élément des rubriques où c'est le moins coûteux : le dernier projet (le moins
pertinent, l'ordre venant du ciblage), la dernière puce de l'expérience la
plus longue, le dernier groupe de compétences, la dernière ligne d'une liste.
"""

from typing import Literal

from pydantic import BaseModel

from app.models.content import CVContent

Side = Literal["left", "right"]
# En dessous, le dépassement est invisible à l'œil (arrondis de LaTeX).
THRESHOLD_PT = 0.5


class Cut(BaseModel):
    id: str
    column: Side
    label: str
    detail: str


class UnknownCut(LookupError):
    pass


def overflowing(columns: dict[str, float]) -> list[Side]:
    return [side for side in ("right", "left") if columns.get(side, 0) > THRESHOLD_PT]  # type: ignore[misc]


def suggest(content: CVContent, columns: dict[str, float]) -> list[Cut]:
    sides = overflowing(columns)
    cuts: list[Cut] = []
    for section in content.sections:
        if not section.visible or section.column not in sides or not section.items:
            continue
        rubric = section.title.capitalize()
        last = len(section.items) - 1
        if section.kind == "projects" and len(section.items) >= 2:
            item = section.items[last]
            cuts.append(
                Cut(
                    id=f"item:{section.id}:{last}",
                    column=section.column,
                    label=f"Retirer le projet « {item.title} »",
                    detail=item.description,
                )
            )
        elif section.kind == "experience":
            longest = max(range(len(section.items)), key=lambda i: len(section.items[i].bullets))
            entry = section.items[longest]
            if len(entry.bullets) >= 3:
                j = len(entry.bullets) - 1
                cuts.append(
                    Cut(
                        id=f"bullet:{section.id}:{longest}:{j}",
                        column=section.column,
                        label=f"Retirer la dernière puce de « {entry.title} »",
                        detail=entry.bullets[j],
                    )
                )
        elif section.kind == "skills" and len(section.items) >= 3:
            group = section.items[last]
            cuts.append(
                Cut(
                    id=f"item:{section.id}:{last}",
                    column=section.column,
                    label=f"Retirer le groupe « {group.label} » ({rubric})",
                    detail=group.text,
                )
            )
        elif section.kind in ("bullets", "grid") and len(section.items) >= 3:
            item = section.items[last]
            text = item if isinstance(item, str) else item.text
            cuts.append(
                Cut(
                    id=f"item:{section.id}:{last}",
                    column=section.column,
                    label=f"Retirer la dernière ligne de {rubric}",
                    detail=text,
                )
            )
    return cuts


def apply_cut(content: CVContent, cut_id: str) -> CVContent:
    """Le CV sans l'élément visé.

    ``cut_id`` : ``item:<section>:<n>`` ou ``bullet:<section>:<n>:<m>``.
    """
    out = content.model_copy(deep=True)
    parts = cut_id.split(":")
    section = next((s for s in out.sections if len(parts) > 1 and s.id == parts[1]), None)
    try:
        if section is None:
            raise UnknownCut(cut_id)
        if parts[0] == "item" and len(parts) == 3:
            del section.items[int(parts[2])]
        elif parts[0] == "bullet" and len(parts) == 4 and section.kind == "experience":
            del section.items[int(parts[2])].bullets[int(parts[3])]
        else:
            raise UnknownCut(cut_id)
    except (IndexError, ValueError):
        raise UnknownCut(cut_id) from None
    return out
