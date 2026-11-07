"""Le texte d'une offre : collé, lu dans un fichier .txt, ou tiré d'une page web.

Une page web ne donne pas toujours l'offre : beaucoup de sites d'emploi
demandent une connexion, bloquent les robots ou chargent l'offre en
JavaScript. Dans ces cas, ``OfferUnavailable`` dit clairement pourquoi et
invite à coller le texte de l'offre.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
import trafilatura

MAX_CHARS = 20_000
MIN_CHARS = 300
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}
# Indices d'une page qui n'est pas l'offre : connexion, robot, JavaScript requis.
_WALLS = re.compile(
    r"(sign in to|connectez-vous|se connecter pour|enable javascript|activez javascript|"
    r"captcha|are you a robot|access denied|accès refusé|authwall)",
    re.I,
)


class OfferUnavailable(Exception):
    pass


@dataclass
class Offer:
    text: str
    url: str | None = None
    title: str | None = None


def clean(text: str) -> str:
    """Espaces et lignes vides réduits, longueur bornée."""
    text = text.replace("\r\n", "\n").replace(" ", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:MAX_CHARS]


def from_text(text: str) -> Offer:
    cleaned = clean(text)
    if len(cleaned) < 80:
        raise OfferUnavailable("Le texte de l'offre est trop court : colle l'offre entière.")
    return Offer(text=cleaned)


async def from_url(url: str) -> Offer:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise OfferUnavailable("Adresse invalide : elle doit commencer par https://")
    site = parsed.netloc.removeprefix("www.")
    paste = " Copie le texte de l'offre sur la page et colle-le ici."
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20, connect=10), follow_redirects=True, headers=HEADERS
        ) as client:
            response = await client.get(url.strip())
    except httpx.TimeoutException:
        raise OfferUnavailable(f"{site} ne répond pas." + paste) from None
    except httpx.HTTPError:
        raise OfferUnavailable(f"Impossible de joindre {site}." + paste) from None
    if response.status_code in (401, 403, 429, 999):
        raise OfferUnavailable(
            f"{site} bloque la lecture automatique ({response.status_code})." + paste
        )
    if response.status_code >= 400:
        raise OfferUnavailable(
            f"{site} répond « {response.status_code} » : l'offre n'existe peut-être plus." + paste
        )
    if "html" not in response.headers.get("content-type", ""):
        raise OfferUnavailable(f"{site} n'a pas renvoyé une page web." + paste)
    html = response.text
    text = (
        trafilatura.extract(html, include_comments=False, include_tables=True, favor_recall=True)
        or ""
    )
    title = None
    metadata = trafilatura.extract_metadata(html)
    if metadata is not None:
        title = metadata.title
    text = clean(text)
    if len(text) < MIN_CHARS:
        reason = (
            "demande une connexion ou bloque les robots"
            if _WALLS.search(html[:50_000])
            else "charge sans doute l'offre en JavaScript"
        )
        raise OfferUnavailable(
            f"La page de {site} ne contient pas le texte de l'offre (le site {reason})." + paste
        )
    if _WALLS.search(text[:600]) and len(text) < 1500:
        raise OfferUnavailable(
            f"{site} affiche une page de connexion à la place de l'offre." + paste
        )
    return Offer(text=text, url=url.strip(), title=title)
