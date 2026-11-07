"""Journal local des appels au modèle : jetons consommés et coût estimé.

Écrit dans ``local/usage.json`` (hors dépôt). Gemini gratuit et Ollama ne
coûtent rien ; pour Mistral, le prix public par million de jetons.
"""

import json
from datetime import UTC, datetime
from typing import Any

from app.ai.llm import Usage
from app.paths import LOCAL_DIR

USAGE_FILE = LOCAL_DIR / "usage.json"
KEEP = 2000
# Dollars par million de jetons (entrée, sortie), par début de nom de modèle.
PRICES = {"mistral-large": (0.5, 1.5)}


def cost(provider: str, model: str, usage: Usage) -> float | None:
    # Gemini et le relais de Yahya : offre gratuite ou crédit offert, rien à payer ici.
    if provider in ("relais", "gemini", "ollama", "demo", "fake"):
        return 0.0
    for prefix, (per_in, per_out) in PRICES.items():
        if model.startswith(prefix):
            return (usage.input_tokens * per_in + usage.output_tokens * per_out) / 1_000_000
    return None


def _entries() -> list[dict[str, Any]]:
    try:
        return json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def record(provider: str, model: str, usage: Usage, label: str) -> None:
    if provider in ("demo", "fake"):
        return
    entries = _entries()
    entries.append(
        {
            "at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "provider": provider,
            "model": model,
            "step": label,
            "input": usage.input_tokens,
            "output": usage.output_tokens,
            "thinking": usage.thinking_tokens,
            "cost": cost(provider, model, usage),
        }
    )
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = USAGE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries[-KEEP:], ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(USAGE_FILE)


def summary() -> dict[str, Any]:
    """Le mois en cours : appels, jetons, coût (None si un prix est inconnu)."""
    month = datetime.now(UTC).strftime("%Y-%m")
    entries = [e for e in _entries() if e["at"].startswith(month)]
    costs = [e["cost"] for e in entries]
    return {
        "month": month,
        "calls": len(entries),
        "input": sum(e["input"] for e in entries),
        "output": sum(e["output"] for e in entries),
        "cost": None if None in costs else round(sum(costs), 4),
        "last": entries[-1]["at"] if entries else None,
    }
