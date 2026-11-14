"""Le mode serveur : connexion par Cloudflare Access et un dossier par personne."""

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import access, paths, people, settings, user_keys
from app.ai import llm
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
    monkeypatch.setenv("CVB_ADMIN", "yahya@example.com")
    monkeypatch.setenv("CVB_SECRET", "secret-du-serveur-d-essai-abcdefghijklmnop")
    monkeypatch.setattr(people, "_last_write", {})
    for name in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_ACCESS_GROUP_ID"):
        monkeypatch.delenv(name, raising=False)
    for email in ("alice@example.com", "bob@example.com", "carla@example.com"):
        people.invite(email)
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
        "admin": False,
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
    assert sorted(p.name for p in server.iterdir()) == ["acces.json", "users"]


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
    assert TestClient(app).get("/api/me").json() == {"mode": "local", "email": None, "admin": False}
    assert paths.user_root() == paths.DATA_DIR


# L'IA en ligne : toujours le relais, au nom de la personne connectée.

RELAY = "https://relais.example.com"
SERVER_CODE = "cvb-serv-eurx-abcd-efgh"


def _fake_relay(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "ok": True,
                "nom": "En ligne",
                "reste_jour": 14,
                "quota_jour": 20,
                "credit_epuise": False,
                "modele": "gemini-3.5-flash-lite",
            },
        )

    real = httpx.AsyncClient

    def client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        return real(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(llm.httpx, "AsyncClient", client)
    return seen


@pytest.fixture
def online(server: Path, monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    monkeypatch.setenv("RELAIS_CODE", SERVER_CODE)
    monkeypatch.setenv("RELAIS_URL", RELAY)
    # Même si la machine était réglée sur une autre IA, en ligne c'est le relais.
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    return _fake_relay(monkeypatch)


def test_settings_show_my_quota_never_the_keys(online: list[httpx.Request]) -> None:
    out = TestClient(app).get("/api/settings", headers=as_("alice@example.com")).json()
    assert out["ai"]["provider"] == "relais"
    assert out["keys"] == {"relais": True, "gemini": False, "mistral": False}
    assert out["usage"]["calls"] == 0
    assert out["online"] == {"ok": True, "left": 14, "quota": 20, "exhausted": False, "message": ""}
    sent = online[0]
    assert sent.headers["authorization"] == f"Bearer {SERVER_CODE}"
    assert sent.headers["x-cvb-utilisateur"] == hashlib.sha256(b"alice@example.com").hexdigest()
    assert SERVER_CODE not in json.dumps(out)


def test_each_person_chooses_their_own_ai(online: list[httpx.Request], server: Path) -> None:
    client = TestClient(app)
    alice, bob = as_("alice@example.com"), as_("bob@example.com")
    ai = client.get("/api/settings", headers=alice).json()["ai"]

    # Ollama, la démo : pas en ligne. Le code du relais : celui du serveur.
    for refused in ("ollama", "demo"):
        put = client.put("/api/settings", headers=alice, json={**ai, "provider": refused})
        assert put.status_code == 422
    relay = client.put("/api/settings/keys/relais", headers=alice, json={"key": "cvb-autre-code-x"})
    assert relay.status_code == 403
    assert client.delete("/api/settings/keys/relais", headers=alice).status_code == 403

    # Alice passe à sa propre clé Gemini ; Bob reste sur le relais.
    put = client.put("/api/settings", headers=alice, json={**ai, "provider": "gemini"})
    assert put.status_code == 200
    with paths.as_user("alice@example.com"):
        settings.write_key("gemini", "AIzaCleDAliceQuiNeSortJamais0000")
        provider = llm.provider_from_settings()
    assert isinstance(provider, llm.GeminiProvider)
    assert not isinstance(provider, llm.RelayProvider)
    with paths.as_user("bob@example.com"):
        assert isinstance(llm.provider_from_settings(), llm.RelayProvider)
        assert settings.secret("gemini") is None

    # La clé est chiffrée sur le disque et ne ressort ni par l'API ni par l'export.
    raw = (server / "users" / "alice@example.com" / "cles.json").read_text()
    assert "AIzaCleDAlice" not in raw
    out = client.get("/api/settings", headers=alice).json()
    assert out["ai"]["provider"] == "gemini"
    assert out["keys"]["gemini"] is True
    assert "AIzaCleDAlice" not in json.dumps(out)
    zipped = client.get("/api/export", headers=alice).content
    assert b"cles.json" not in zipped and b"AIzaCleDAlice" not in zipped
    assert client.get("/api/settings", headers=bob).json()["ai"]["provider"] == "relais"
    assert not (settings.ENV_FILE).exists()

    # Supprimer sa clé : seulement la sienne.
    assert client.delete("/api/settings/keys/gemini", headers=alice).status_code == 200
    with paths.as_user("alice@example.com"):
        assert settings.secret("gemini") is None


def test_server_refuses_to_start_without_secret(
    server: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CVB_SECRET")
    with pytest.raises(user_keys.SecretMissing), TestClient(app):
        pass


def test_no_setup_screen_online(online: list[httpx.Request]) -> None:
    state = TestClient(app).get("/api/welcome", headers=as_("alice@example.com")).json()
    assert state["setup"] is False


def test_provider_is_the_relay_for_the_signed_in_person(online: list[httpx.Request]) -> None:
    with paths.as_user("bob@example.com"):
        provider = llm.provider_from_settings()
    assert isinstance(provider, llm.RelayProvider)
    assert provider.user == "bob@example.com"
    # Hors requête (personne de connecté), pas d'IA.
    with pytest.raises(llm.LLMError):
        llm.provider_from_settings()


def test_export_gives_only_my_data(server: Path) -> None:
    import io
    import zipfile

    client = TestClient(app)
    alice, bob = as_("alice@example.com"), as_("bob@example.com")
    client.put("/api/rules/lettre", headers=alice, json={"rules": ["Règle d'Alice"]})
    client.get("/api/cvs", headers=bob)
    answer = client.get("/api/export", headers=alice)
    assert answer.status_code == 200
    assert answer.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(answer.content)).namelist()
    assert "cv-builder-pro/base/content.json" in names
    assert any(name.startswith("cv-builder-pro/rules/") for name in names)
    assert not any("bob" in name or "users" in name for name in names)
    assert client.get("/api/export").status_code == 401


# L'administration, réservée à CVB_ADMIN.

ADMIN = "yahya@example.com"


def test_only_invited_people_get_in(server: Path) -> None:
    client = TestClient(app)
    stranger = client.get("/api/cvs", headers=as_("inconnu@example.com"))
    assert stranger.status_code == 403
    # L'administrateur entre sans figurer dans la liste.
    assert client.get("/api/me", headers=as_(ADMIN)).json()["admin"] is True


def test_admin_pages_are_for_the_admin_only(server: Path) -> None:
    client = TestClient(app)
    for url in ("/api/admin/people", "/api/admin/people/alice@example.com"):
        assert client.get(url, headers=as_("alice@example.com")).status_code == 403
    answer = client.post(
        "/api/admin/people", headers=as_("alice@example.com"), json={"email": "x@example.com"}
    )
    assert answer.status_code == 403
    assert "x@example.com" not in people.load()


def test_admin_invites_removes_and_erases(server: Path) -> None:
    client = TestClient(app)
    admin = as_(ADMIN)
    out = client.post("/api/admin/people", headers=admin, json={"email": " Dana@Example.com "})
    assert out.status_code == 200
    assert "dana@example.com" in [p["email"] for p in out.json()["people"]]
    assert client.get("/api/cvs", headers=as_("dana@example.com")).status_code == 200

    # Retirée : coupée tout de suite, données gardées.
    assert client.delete("/api/admin/people/dana@example.com", headers=admin).status_code == 200
    assert client.get("/api/cvs", headers=as_("dana@example.com")).status_code == 403
    assert (server / "users" / "dana@example.com").is_dir()

    # Réinvitée, puis retirée et effacée pour de bon.
    client.post("/api/admin/people", headers=admin, json={"email": "dana@example.com"})
    erase = client.delete("/api/admin/people/dana@example.com/data", headers=admin)
    assert erase.status_code == 409
    client.delete("/api/admin/people/dana@example.com", headers=admin)
    assert (
        client.delete("/api/admin/people/dana@example.com/data", headers=admin).status_code == 200
    )
    assert not (server / "users" / "dana@example.com").exists()
    assert "dana@example.com" not in people.load()

    assert client.delete(f"/api/admin/people/{ADMIN}", headers=admin).status_code == 409
    bad = client.post("/api/admin/people", headers=admin, json={"email": "../../etc"})
    assert bad.status_code == 422


def test_admin_reads_a_person_without_changing_anything(server: Path) -> None:
    client = TestClient(app)
    alice = as_("alice@example.com")
    client.put("/api/rules/lettre", headers=alice, json={"rules": ["Règle d'Alice"]})
    before = sorted(str(p) for p in (server / "users" / "alice@example.com").rglob("*"))
    admin = as_(ADMIN)
    listing = client.get("/api/admin/people", headers=admin).json()
    alice_row = next(p for p in listing["people"] if p["email"] == "alice@example.com")
    assert alice_row["cvs"] == 1 and alice_row["applications"] == 0
    assert alice_row["last_seen"] is not None
    detail = client.get("/api/admin/people/alice@example.com", headers=admin).json()
    assert [cv["slug"] for cv in detail["cvs"]] == ["base"]
    zipped = client.get("/api/admin/people/alice@example.com/export", headers=admin)
    assert zipped.status_code == 200 and zipped.content[:2] == b"PK"
    after = sorted(str(p) for p in (server / "users" / "alice@example.com").rglob("*"))
    assert before == after
    # Les données de l'admin ne se mélangent pas à celles d'Alice.
    assert client.get("/api/rules/lettre", headers=admin).json()["rules"] != ["Règle d'Alice"]


def test_cloudflare_group_gets_the_active_list(
    server: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CF_API_TOKEN", "jeton-essai")
    monkeypatch.setenv("CF_ACCOUNT_ID", "compte")
    monkeypatch.setenv("CF_ACCESS_GROUP_ID", "groupe")
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer jeton-essai"
        assert request.url.path == "/client/v4/accounts/compte/access/groups/groupe"
        if request.method == "GET":
            return httpx.Response(200, json={"result": {"name": "CV Builder Pro", "include": []}})
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"result": {}})

    real = httpx.Client
    monkeypatch.setattr(
        people.httpx,
        "Client",
        lambda *a, **k: real(*a, transport=httpx.MockTransport(handler), **k),
    )
    client = TestClient(app)
    client.delete("/api/admin/people/bob@example.com", headers=as_(ADMIN))
    assert sent[-1]["name"] == "CV Builder Pro"
    assert [r["email"]["email"] for r in sent[-1]["include"]] == [
        "alice@example.com",
        "carla@example.com",
        ADMIN,
    ]


class FakeCloudflare:
    """Le groupe Access : GET le rend, PUT le remplace (ou échoue sur commande)."""

    def __init__(self) -> None:
        self.include: list[dict[str, Any]] = []
        self.refuse_put = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"result": {"name": "G", "include": self.include}})
        if self.refuse_put:
            return httpx.Response(500, json={"success": False})
        self.include = json.loads(request.content)["include"]
        return httpx.Response(200, json={"result": {}})


@pytest.fixture
def cloudflare(server: Path, monkeypatch: pytest.MonkeyPatch) -> FakeCloudflare:
    monkeypatch.setenv("CF_API_TOKEN", "jeton-essai")
    monkeypatch.setenv("CF_ACCOUNT_ID", "compte")
    monkeypatch.setenv("CF_ACCESS_GROUP_ID", "groupe")
    fake = FakeCloudflare()
    real = httpx.Client
    monkeypatch.setattr(
        people.httpx,
        "Client",
        lambda *a, **k: real(*a, transport=httpx.MockTransport(fake.handler), **k),
    )
    return fake


def _state(answer: httpx.Response, email: str) -> bool | None:
    return next(p["cloudflare"] for p in answer.json()["people"] if p["email"] == email)


def test_admin_sees_whether_cloudflare_took_the_address(cloudflare: FakeCloudflare) -> None:
    client = TestClient(app)
    admin = as_(ADMIN)
    out = client.post("/api/admin/people", headers=admin, json={"email": "dana@example.com"})
    assert _state(out, "dana@example.com") is True and out.json()["warning"] is None

    # Cloudflare refuse la liste : l'appli le voit en relisant le groupe.
    cloudflare.refuse_put = True
    out = client.post("/api/admin/people", headers=admin, json={"email": "eli@example.com"})
    assert _state(out, "eli@example.com") is False
    assert "Cloudflare" in out.json()["warning"]

    # « Réessayer » une fois Cloudflare revenu.
    cloudflare.refuse_put = False
    out = client.post("/api/admin/people/sync", headers=admin)
    assert _state(out, "eli@example.com") is True
    assert (
        client.post("/api/admin/people/sync", headers=as_("alice@example.com")).status_code == 403
    )


def test_without_cloudflare_the_state_is_unknown(server: Path) -> None:
    out = TestClient(app).get("/api/admin/people", headers=as_(ADMIN))
    assert {p["cloudflare"] for p in out.json()["people"]} == {None}


def test_a_removed_person_gets_the_pause_screen(server: Path) -> None:
    client = TestClient(app)
    client.delete("/api/admin/people/bob@example.com", headers=as_(ADMIN))
    answer = client.get("/api/me", headers=as_("bob@example.com"))
    assert answer.status_code == 403
    assert answer.json()["code"] == "paused"
    assert answer.json()["email"] == "bob@example.com"


def test_reinvited_after_erase_gets_in_and_is_seen(server: Path) -> None:
    client = TestClient(app)
    admin = as_(ADMIN)
    dana = as_("dana@example.com")
    client.post("/api/admin/people", headers=admin, json={"email": "dana@example.com"})
    assert client.get("/api/cvs", headers=dana).status_code == 200
    client.delete("/api/admin/people/dana@example.com", headers=admin)
    client.delete("/api/admin/people/dana@example.com/data", headers=admin)
    client.post("/api/admin/people", headers=admin, json={"email": "dana@example.com"})
    assert client.get("/api/cvs", headers=dana).status_code == 200
    # La visite d'après la réinvitation est notée, même dans les 5 minutes.
    assert people.load()["dana@example.com"].last_seen is not None


def test_the_page_is_never_cached_but_its_assets_are(tmp_path: Path) -> None:
    """Après une mise à jour, le navigateur reprend la nouvelle interface (index.html sans
    cache) ; les fichiers d'assets/, au nom changé à chaque version, restent en cache."""
    from fastapi import FastAPI

    from app.main import _Web

    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (tmp_path / "assets" / "app-1a2b.js").write_text("//", encoding="utf-8")
    web = FastAPI()
    web.mount("/", _Web(directory=tmp_path, html=True), name="web")
    client = TestClient(web)
    assert client.get("/").headers["Cache-Control"] == "no-cache"
    assert "immutable" in client.get("/assets/app-1a2b.js").headers["Cache-Control"]
