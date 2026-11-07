"""Petites fonctions de texte."""

import re
import unicodedata


def slugify(text: str, fallback: str = "sans-nom") -> str:
    """« Thème Bleu élégant » → « theme-bleu-elegant » (lettres, chiffres, tirets)."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:60].strip("-") or fallback
