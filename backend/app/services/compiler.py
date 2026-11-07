"""Compilation à la demande, une à la fois par CV, la plus récente gagne.

Pendant la frappe, l'interface demande une compilation après chaque pause.
Si une nouvelle demande arrive pendant qu'une autre attend son tour, celle
qui attend est abandonnée : seule la dernière version du contenu compte.
"""

import asyncio
from collections import defaultdict

from app.latex.compile import CompileResult, compile_tex
from app.storage import cv_store


class Compiler:
    def __init__(self) -> None:
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._latest: dict[str, int] = {}

    async def compile(self, slug: str) -> CompileResult | None:
        """Le résultat, ou None si une demande plus récente l'a remplacée."""
        ticket = self._latest.get(slug, 0) + 1
        self._latest[slug] = ticket
        async with self._locks[slug]:
            if self._latest[slug] != ticket:
                return None
            path = cv_store.folder(slug)
            meta = cv_store.load_meta(path)
            tex = path / cv_store.TEX if meta.mode == "manual" else cv_store.write_tex(path)
            result = await asyncio.to_thread(compile_tex, tex)
            if result.ok:
                cv_store.touch(path, pages=result.pages)
            return result

    async def compile_letter(self, slug: str) -> CompileResult | None:
        """La lettre de motivation du CV (son propre tour : elle n'attend pas le CV)."""
        from app.storage import letter_store

        key = f"{slug}#lettre"
        ticket = self._latest.get(key, 0) + 1
        self._latest[key] = ticket
        async with self._locks[key]:
            if self._latest[key] != ticket:
                return None
            path = cv_store.folder(slug)
            letter = letter_store.load(path)
            if letter is None:
                return None
            tex = (
                path / letter_store.TEX if letter.mode == "manual" else letter_store.write_tex(path)
            )
            return await asyncio.to_thread(compile_tex, tex, pdf_name=letter_store.PDF)


compiler = Compiler()
