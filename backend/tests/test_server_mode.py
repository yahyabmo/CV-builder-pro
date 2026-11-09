"""Le mode serveur : connexion par Cloudflare Access et un dossier par personne."""

import time
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import access, paths, settings
from app.main import app

TEAM = "cv-essai.cloudflareaccess.com"
ISSUER = f"https://{TEAM}"
AUD = "audience-essai"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(email: str, *, key: Any = KEY, aud: str = AUD, exp: float | None = None) -> str:
    now = int(time.time())
    claims = {
        "email": email,
        "aud": [aud],
        "iss": ISSUER,
        "iat": now,
        "exp": int(exp if exp is not None else now + 600),
        "sub": "id-" + email,
    }
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data = tmp_path / "data"
    monkeypatch.setattr(paths, "DATA_DIR", data)
    monkeypatch.setenv("CVB_MODE", "serveur")
    monkeypatch.setenv("CF_ACCESS_TEAM", TEAM)
    monkeypatch.setenv("CF_ACCESS_AUD", AUD)
    monkeypatch.setattr(access, "signing_key", lambda _token, _issuer: KEY.public_key())
    monkeypatch.setattr(settings, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(settings, "SETUP_FILE", tmp_path / "local" / "setup.json")
    for name in settings.KEYS.values():
        monkeypatch.delenv(name, raising=False)
    return data


def as_(email: str) -> dict[str, str]:
    return {"Cf-Access-Jwt-Assertion": token(email)}


def test_health_stays_open(server: Path) -> None:
    assert TestClient(app).get("/api/health").json()["app"] == "cv-builder-pro"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Cf-Access-Jwt-Assertion": "pas-un-jeton"},
        {"Cf-Access-Jwt-Assertion": token("a@example.com", key=OTHER_KEY)},
        {"Cf-Access-Jwt-Assertion": token("a@example.com", aud="autre-appli")},
        {"Cf-Access-Jwt-Assertion": token("a@example.com", exp=time.time() - 60)},
        {"Cf-Access-Jwt-Assertion": token("../../etc@example.com")},
        {"Cf-Access-Jwt-Assertion": token("")},
    ],
    ids=["sans", "illisible", "autre-cle", "autre-audience", "expire", "chemin", "vide"],
)
def test_refused_without_valid_token(server: Path, headers: dict[str, str]) -> None:
    client = TestClient(app)
    for url in ("/api/cvs", "/api/me", "/api/inconnue"):
        assert client.get(url, headers=headers).status_code == 401
    # Rien n'a été créé pour une connexion refusée.
    assert not (server / "users").exists()


def test_each_person_has_own_data(server: Path) -> None:
    client = TestClient(app)
    alice, bob = as_("Alice@Example.com"), as_("bob@example.com")

    assert client.get("/api/me", headers=alice).json() == {
        "mode": "serveur",
        "email": "alice@example.com",
    }
    # Première visite : le CV fictif, dans le dossier de la personne.
    assert [cv["slug"] for cv in client.get("/api/cvs", headers=alice).json()] == ["base"]
    assert (server / "users" / "alice@example.com" / "base" / "content.json").exists()

    put = client.put("/api/rules/lettre", headers=alice, json={"rules": ["Jamais de « je »"]})
    assert put.status_code == 200
    assert client.get("/api/rules/lettre", headers=alice).json()["rules"] == ["Jamais de « je »"]
    assert client.get("/api/rules/lettre", headers=bob).json()["rules"] != ["Jamais de « je »"]

    assert sorted(p.name for p in (server / "users").iterdir()) == [
        "alice@example.com",
        "bob@example.com",
    ]
    # Rien d'écrit directement dans data/ : tout est sous users/.
    assert sorted(p.name for p in server.iterdir()) == ["users"]


def test_cookie_works_too(server: Path) -> None:
    client = TestClient(app)
    client.cookies.set(access.COOKIE, token("carla@example.com"))
    assert client.get("/api/me").json()["email"] == "carla@example.com"


def test_server_refuses_to_start_without_access(
    server: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CF_ACCESS_AUD")
    with pytest.raises(access.AccessError), TestClient(app):
        pass


def test_local_mode_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CVB_MODE", raising=False)
    assert TestClient(app).get("/api/me").json() == {"mode": "local", "email": None}
    assert paths.user_root() == paths.DATA_DIR
