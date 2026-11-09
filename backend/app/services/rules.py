"""Les listes de règles modifiables dans Réglages, une règle par ligne « - … ».

- ``lettre`` : les règles de la lettre de motivation ;
- ``tournures`` : les tournures qui sonnent « écrit par une IA », signalées dans la lettre.

Les listes par défaut sont dans ``prompts/`` ; celles modifiées dans Réglages sont
écrites dans ``data/rules/``, hors du dépôt, et prennent le pas sur les premières.
"""

from pathlib import Path

from app.paths import PROMPTS_DIR, RULES_DIR

FILES: dict[str, str] = {
    "lettre": "lettre-regles.md",
    "tournures": "lettre-tournures.md",
}


class UnknownRules(LookupError):
    pass


def _name(kind: str) -> str:
    if kind not in FILES:
        raise UnknownRules(kind)
    return FILES[kind]


def _file(kind: str) -> Path:
    """La liste modifiée si elle existe, sinon celle par défaut."""
    edited = RULES_DIR / _name(kind)
    return edited if edited.exists() else PROMPTS_DIR / _name(kind)


def read(kind: str) -> list[str]:
    """Les règles : une ligne « - » ouvre une règle, les lignes suivantes la prolongent."""
    file = _file(kind)
    if not file.exists():
        return []
    rules: list[str] = []
    for line in file.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith("- ") or text == "-" or not rules:
            rules.append(text.removeprefix("-").strip())
        else:
            rules[-1] = f"{rules[-1]} {text}"
    return [rule for rule in rules if rule]


def write(kind: str, rules: list[str]) -> list[str]:
    clean = [" ".join(rule.split()) for rule in rules]
    clean = [rule for rule in clean if rule]
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    (RULES_DIR / _name(kind)).write_text("".join(f"- {rule}\n" for rule in clean), encoding="utf-8")
    return clean


def as_text(kind: str) -> str:
    """Les règles en liste Markdown, pour un prompt."""
    return "\n".join(f"- {rule}" for rule in read(kind))
