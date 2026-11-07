"""Les dossiers de l'appli.

Tout ce qui est personnel vit dans ``data/``, hors du dépôt : la version classique
du CV, les CV ciblés, la bibliothèque, les thèmes et la corbeille. ``demo/`` contient
un CV fictif, recopié dans ``data/base`` au premier lancement. ``local/`` garde
les réglages de cette machine et le journal des appels à l'IA.

``CVB_DATA`` et ``CVB_LOCAL`` remplacent ces deux dossiers : les essais de
l'interface tournent ainsi sur une copie jetable, jamais sur tes données.
"""

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("CVB_DATA") or ROOT / "data")
LOCAL_DIR = Path(os.environ.get("CVB_LOCAL") or ROOT / "local")
BASE_DIR = DATA_DIR / "base"
CVS_DIR = DATA_DIR / "cvs"
LIBRARY_DIR = DATA_DIR / "library"
THEMES_DIR = DATA_DIR / "themes"
TRASH_DIR = DATA_DIR / "corbeille"
# Propositions de ciblage en cours de relecture.
DRAFTS_DIR = DATA_DIR / "drafts"
DEMO_DIR = ROOT / "demo"
FONTS_DIR = ROOT / "fonts"
PROMPTS_DIR = ROOT / "prompts"
# L'interface construite (npm run build), servie par le serveur avec « make start ».
WEB_DIR = Path(os.environ.get("CVB_WEB") or ROOT / "frontend" / "dist")

BASE_FILES = ("content.json", "style.json", "meta.json", "imgcv.jpg")


def ensure_base(base: Path = BASE_DIR, demo: Path = DEMO_DIR) -> bool:
    """Recopie le CV fictif si aucune version classique n'existe encore."""
    if (base / "content.json").exists():
        return False
    base.mkdir(parents=True, exist_ok=True)
    for name in BASE_FILES:
        shutil.copy(demo / name, base / name)
    return True
