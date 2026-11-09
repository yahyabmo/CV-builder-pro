"""Réglages de l'IA.

Trois sources, de la plus faible à la plus forte :

1. les valeurs par défaut ci-dessous ;
2. le fichier ``.env`` à la racine (et les variables d'environnement) ;
3. ``local/settings.json`` (hors dépôt), écrit par la page Réglages.

Les clés d'API ne viennent QUE de ``.env`` (ou d'une variable d'environnement) :
l'écran de démarrage et Réglages les y écrivent, lisible par toi seul ; elles ne
sont jamais écrites ailleurs, jamais renvoyées par l'API, jamais journalisées.
``CVB_ENV`` remplace le chemin de ``.env`` (essais de l'interface, image Docker).
"""

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.paths import LOCAL_DIR, ROOT, server_mode

ENV_FILE = Path(os.environ.get("CVB_ENV") or ROOT / ".env")
SETTINGS_FILE = LOCAL_DIR / "settings.json"
# Présent une fois l'écran de démarrage (modèle d'IA et machine) passé.
SETUP_FILE = LOCAL_DIR / "setup.json"

# « relais » : Gemini par le relais de Yahya (dossier relais/), avec un code d'accès qu'il
# donne, sans clé. « demo » rejoue des réponses enregistrées pour l'offre d'exemple.
Provider = Literal["relais", "gemini", "mistral", "ollama", "demo", "fake"]
KEYS = {"relais": "RELAIS_CODE", "gemini": "GEMINI_API_KEY", "mistral": "MISTRAL_API_KEY"}
# L'adresse du relais de Yahya, en ligne depuis le 07/11/2026 (README de relais/) ;
# RELAIS_URL la remplace (essais, autre relais).
DEFAULT_RELAIS_URL = "https://cvb-relais.cv-pro.workers.dev"
# Une clé d'API collée d'un bloc : lettres, chiffres, « . », « _ » et « - ».
KEY_PATTERN = re.compile(r"[A-Za-z0-9._-]{10,200}")


class AISettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: Provider = "gemini"
    # Mesures du 18/10/2026 en offre gratuite (20 requêtes par jour et par
    # modèle) : 3.5 Flash cible une offre en 30 à 40 s et rédige le mieux ;
    # 3.8 Flash est bon mais lent (plus de 2 min) ; 3.5 Flash-Lite répond en
    # 8 s, plus prudent, et perd parfois un détail.
    gemini_model: str = "gemini-3.5-flash"
    # Modèles suivants, dans l'ordre, quand le premier est surchargé ou épuisé.
    gemini_fallbacks: list[str] = ["gemini-3.8-flash", "gemini-3.5-flash-lite"]
    mistral_model: str = "mistral-large-latest"
    relais_url: str = DEFAULT_RELAIS_URL
    # Le modèle que sert le relais (il l'impose, quoi que l'appli demande).
    relais_model: str = "gemini-3.5-flash-lite"
    ollama_model: str = "ministral-3:8b"
    ollama_url: str = "http://127.0.0.1:11434"
    temperature: float = 0.2

    def model_for(self, provider: Provider | None = None) -> str:
        p = provider or self.provider
        return {
            "relais": self.relais_model,
            "gemini": self.gemini_model,
            "mistral": self.mistral_model,
            "ollama": self.ollama_model,
            "demo": "réponses enregistrées",
            "fake": "faux-modele",
        }[p]


def read_env() -> dict[str, str]:
    """Les variables de .env (sans guillemets autour), puis celles de l'environnement."""
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip().strip('"').strip("'")
    wanted = set(values) | set(KEYS.values()) | {"RELAIS_URL"}
    values.update({k: v for k, v in os.environ.items() if k in wanted or k.startswith("LLM_")})
    return values


def load() -> AISettings:
    env = read_env()
    data: dict[str, object] = {}
    mapping = {
        "LLM_PROVIDER": "provider",
        "GEMINI_MODEL": "gemini_model",
        "MISTRAL_MODEL": "mistral_model",
        "OLLAMA_MODEL": "ollama_model",
        "OLLAMA_URL": "ollama_url",
        "RELAIS_URL": "relais_url",
    }
    for env_name, field in mapping.items():
        if env.get(env_name):
            data[field] = env[env_name]
    if env.get("GEMINI_FALLBACK_MODELS"):
        data["gemini_fallbacks"] = [m.strip() for m in env["GEMINI_FALLBACK_MODELS"].split(",")]
    if SETTINGS_FILE.exists():
        data.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    if server_mode():
        data["provider"] = "relais"
    return AISettings.model_validate(data)


def save(settings: AISettings) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(settings.model_dump(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def secret(provider: Provider) -> str | None:
    """La clé d'un fournisseur, lue dans .env au moment de l'appel."""
    name = KEYS.get(provider)
    return read_env().get(name) if name else None


def has_key(provider: Provider) -> bool:
    return provider in ("ollama", "demo", "fake") or bool(secret(provider))


def key_from_environment(provider: Provider) -> bool:
    """La clé vient d'une variable d'environnement (image Docker) : .env n'y peut rien."""
    name = KEYS.get(provider)
    return bool(name and os.environ.get(name))


def _env_lines(without: str) -> list[str]:
    """Les lignes de .env, sans celles qui définissent ``without``."""
    if not ENV_FILE.exists():
        return []
    return [
        line
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines()
        if line.lstrip().startswith("#") or line.split("=", 1)[0].strip() != without
    ]


def _write_env(lines: list[str]) -> None:
    """Réécrit .env d'un coup, lisible et modifiable par toi seul (600)."""
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = ENV_FILE.with_name(ENV_FILE.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n" if lines else "")
    os.chmod(tmp, 0o600)
    os.replace(tmp, ENV_FILE)


def write_key(provider: Provider, key: str) -> None:
    """Enregistre la clé d'un fournisseur dans .env, à la place de l'ancienne."""
    name = KEYS[provider]
    _write_env([*_env_lines(name), f"{name}={key}"])


def delete_key(provider: Provider) -> None:
    _write_env(_env_lines(KEYS[provider]))


def setup_done() -> bool:
    return SETUP_FILE.exists()


def mark_setup_done() -> None:
    SETUP_FILE.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).replace(microsecond=0).isoformat()
    SETUP_FILE.write_text(json.dumps({"done": stamp}) + "\n", encoding="utf-8")
