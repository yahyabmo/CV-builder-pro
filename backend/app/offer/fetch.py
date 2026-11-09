"""Le texte d'une offre : collé, lu dans un fichier .txt, ou tiré d'une page web.

Une page web ne donne pas toujours l'offre : beaucoup de sites d'emploi
demandent une connexion, bloquent les robots ou chargent l'offre en
JavaScript. Dans ces cas, ``OfferUnavailable`` dit clairement pourquoi et
invite à coller le texte de l'offre.
"""

import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

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


# Une page d'offre fait quelques centaines de Ko ; au-delà, ce n'est pas une offre.
MAX_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 5


async def _public(url: str) -> None:
    """Refuse une adresse qui mène au serveur lui-même ou à un réseau privé.

    En ligne, l'appli lit les pages depuis le serveur : sans cette garde, une « offre »
    à http://127.0.0.1:8000 ou http://169.254.169.254 lirait ce qui n'est pas public.
    Chaque redirection repasse par ici.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise OfferUnavailable("Adresse invalide : elle doit commencer par https://")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError:
        raise OfferUnavailable(f"Adresse introuvable : {parsed.hostname}.") from None
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        if not address.is_global or address.is_multicast:
            raise OfferUnavailable("Cette adresse n'est pas une page publique.")


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """La page, en suivant les redirections une à une (chacune vérifiée), taille limitée."""
    for _ in range(MAX_REDIRECTS + 1):
        await _public(url)
        async with client.stream("GET", url) as response:
            if response.is_redirect and "location" in response.headers:
                url = urljoin(url, response.headers["location"])
                continue
            body = b""
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > MAX_BYTES:
                    raise OfferUnavailable("La page est trop lourde pour être une offre.")
            # Corps déjà décompressé : sans ces en-têtes, httpx ne le décode pas une 2e fois.
            headers = {
                k: v
                for k, v in response.headers.items()
                if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")
            }
            return httpx.Response(
                response.status_code,
                headers=headers,
                content=body,
                request=response.request,
            )
    raise OfferUnavailable("Trop de redirections.")


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
            timeout=httpx.Timeout(20, connect=10), follow_redirects=False, headers=HEADERS
        ) as client:
            response = await _get(client, url.strip())
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
