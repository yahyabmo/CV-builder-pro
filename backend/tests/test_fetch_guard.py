"""La lecture d'une offre par son adresse : jamais le serveur lui-même ni un réseau privé."""

import asyncio

import httpx
import pytest

from app.offer import fetch


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/api/me",
        "http://localhost/",
        "http://169.254.169.254/hetzner/v1/metadata",
        "http://10.0.0.2/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "file:///etc/passwd",
    ],
)
def test_private_addresses_are_refused(url: str) -> None:
    with pytest.raises(fetch.OfferUnavailable):
        asyncio.run(fetch.from_url(url))


def test_redirect_to_a_private_address_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    async def public(url: str) -> None:
        if "127.0.0.1" in url:
            raise fetch.OfferUnavailable("Cette adresse n'est pas une page publique.")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1:8000/api/me"})

    real = httpx.AsyncClient
    monkeypatch.setattr(fetch, "_public", public)
    monkeypatch.setattr(
        fetch.httpx,
        "AsyncClient",
        lambda *a, **k: real(*a, transport=httpx.MockTransport(handler), **k),
    )
    with pytest.raises(fetch.OfferUnavailable, match="publique"):
        asyncio.run(fetch.from_url("https://emplois.example.com/offre"))


def test_public_page_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    paragraphs = "".join(
        f"<p>Mission {n} : analyser des données de santé avec l'équipe {n}, puis présenter "
        f"les résultats au comité numéro {n} chaque mois.</p>"
        for n in range(1, 13)
    )
    page = f"<html><body><article>{paragraphs}</article></body></html>"

    async def public(url: str) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ancienne":
            return httpx.Response(301, headers={"location": "/offre"})
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=page)

    real = httpx.AsyncClient
    monkeypatch.setattr(fetch, "_public", public)
    monkeypatch.setattr(
        fetch.httpx,
        "AsyncClient",
        lambda *a, **k: real(*a, transport=httpx.MockTransport(handler), **k),
    )
    offer = asyncio.run(fetch.from_url("https://emplois.example.com/ancienne"))
    assert "données de santé" in offer.text
