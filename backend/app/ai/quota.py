"""Les modèles dont le quota gratuit du jour est épuisé, jusqu'à sa remise à zéro.

Gemini compte les requêtes gratuites par modèle et par jour. Un modèle épuisé
est noté ici (dans ``local/quota.json``, pour survivre aux redémarrages) et
sauté jusqu'à l'heure indiquée par Google : aucune requête n'est gaspillée.
"""

import json
import time
from pathlib import Path

from app import paths
from app.paths import LOCAL_DIR

QUOTA_FILE = LOCAL_DIR / "quota.json"


def _file() -> Path:
    """En ligne, chaque personne a ses propres quotas (sa propre clé Gemini)."""
    if paths.server_mode() and paths.current_user():
        return paths.user_root() / "quota.json"
    return QUOTA_FILE


def _read() -> dict[str, float]:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    now = time.time()
    return {model: until for model, until in data.items() if until > now}


def blocked() -> dict[str, float]:
    """Modèle → instant (epoch) où son quota revient."""
    return _read()


def is_blocked(model: str) -> bool:
    return model in _read()


def block(model: str, until: float) -> None:
    data = _read()
    data[model] = until
    _file().parent.mkdir(parents=True, exist_ok=True)
    _file().write_text(json.dumps(data, indent=1), encoding="utf-8")


def clear() -> None:
    _file().unlink(missing_ok=True)
