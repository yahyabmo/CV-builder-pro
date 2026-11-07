"""Le raccourci du bureau et son lanceur (scripts/raccourci.py, scripts/appli.py).

Tout se passe dans des dossiers jetables : ni le vrai bureau, ni le vrai menu des
applis, ni les vraies données ne sont touchés.
"""

import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Un dossier personnel jetable, avec un bureau."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".local" / "share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    (tmp_path / "Desktop").mkdir()
    return tmp_path


def test_desktop_entry_quotes_paths_and_offers_stop():
    raccourci = load("raccourci")
    entry = raccourci.desktop_entry()
    assert "Name=CV Builder Pro\n" in entry
    assert "Terminal=false\n" in entry
    assert f'Exec="{raccourci.PYTHON}" "{raccourci.LAUNCHER}" ouvrir\n' in entry
    assert f"Icon={ROOT / 'assets' / 'icone.png'}\n" in entry
    assert "[Desktop Action arreter]" in entry and entry.rstrip().endswith("arreter")
    assert (ROOT / "assets" / "icone.png").exists()


def test_linux_shortcut_in_menu_and_on_desktop_then_removed(home):
    raccourci = load("raccourci")
    made = raccourci.create_linux()
    menu = home / ".local" / "share" / "applications" / "cv-builder-pro.desktop"
    desktop = home / "Desktop" / "cv-builder-pro.desktop"
    assert made == [str(menu), str(desktop)]
    for path in (menu, desktop):
        assert path.read_text() == raccourci.desktop_entry()
        assert os.access(path, os.X_OK)
    assert raccourci.remove_linux() == made
    assert not menu.exists() and not desktop.exists()


def test_no_desktop_folder_means_menu_only(home):
    (home / "Desktop").rmdir()
    raccourci = load("raccourci")
    assert raccourci.desktop_dir() is None


def test_windows_shortcut_runs_the_launcher_hidden_in_this_wsl(monkeypatch):
    """Sous WSL : PowerShell caché lance wsl.exe sur cette distribution, sans passer par bash."""
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu-24.04")
    raccourci = load("raccourci")
    user = raccourci.pwd.getpwuid(os.getuid()).pw_name
    command = raccourci.windows_command("ouvrir --garder")
    assert command == (
        f"& wsl.exe -d 'Ubuntu-24.04' -u '{user}' --exec "
        f"'{raccourci.PYTHON}' '{raccourci.LAUNCHER}' ouvrir --garder"
    )
    assert raccourci.windows_arguments("arreter").startswith(
        '-NoProfile -WindowStyle Hidden -Command "& wsl.exe'
    )


def test_windows_shortcut_survives_an_apostrophe_in_the_path(monkeypatch):
    raccourci = load("raccourci")
    monkeypatch.setattr(raccourci, "PYTHON", Path("/home/o'neil/CV-builder-pro/.venv/bin/python"))
    assert "'/home/o''neil/CV-builder-pro/.venv/bin/python'" in raccourci.windows_command("ouvrir")
    icon = "C:\\Users\\O'Neil\\AppData\\Local\\CV Builder Pro\\icone.ico"
    script = raccourci.shortcut_script(icon)
    # Les arguments sont eux-mêmes une chaîne PowerShell : chaque apostrophe y est doublée.
    assert raccourci.ps_literal(raccourci.windows_arguments("ouvrir --garder")) in script
    assert "$icon = 'C:\\Users\\O''Neil\\AppData\\Local\\CV Builder Pro\\icone.ico'" in script
    for name in ("'CV Builder Pro.lnk'", "'Arrêter CV Builder Pro.lnk'"):
        assert name in script


def test_windows_icon_has_every_size():
    from PIL import Image

    with Image.open(ROOT / "assets" / "icone.ico") as icon:
        assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= set(icon.info["sizes"])


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def launcher(tmp_path: Path, port: int | None = None):
    """Le lanceur sur des dossiers jetables ; port imposé (CVB_PORT) ou choisi par lui."""
    web = tmp_path / "web"
    web.mkdir(exist_ok=True)
    (web / "index.html").write_text('<div id="root"></div>')
    env = dict(
        os.environ,
        CVB_WEB=str(web),
        CVB_DATA=str(tmp_path / "data"),
        CVB_LOCAL=str(tmp_path / "local"),
        CVB_ENV=str(tmp_path / ".env"),
    )
    env.pop("CVB_PORT", None)
    if port:
        env["CVB_PORT"] = str(port)
    # Pas de notification sur le bureau pendant les essais.
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)

    def run(action: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "appli.py"), action],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    return run


def state(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "local" / "appli.json").read_text())


def test_launcher_starts_in_background_then_stops(tmp_path):
    port = free_port()
    run = launcher(tmp_path, port)
    started = run("demarrer")
    try:
        assert started.returncode == 0, started.stderr
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as page:
            assert 'id="root"' in page.read().decode()
        assert f"tourne : http://localhost:{port}" in run("etat").stdout
        assert state(tmp_path)["port"] == port and state(tmp_path)["pid"]
        # Un deuxième clic ne lance pas un deuxième serveur.
        pid = state(tmp_path)["pid"]
        assert run("demarrer").returncode == 0
        assert state(tmp_path)["pid"] == pid
    finally:
        stopped = run("arreter")
    assert stopped.returncode == 0, stopped.stdout
    assert "arrêtée" in run("etat").stdout
    assert state(tmp_path) == {"port": port}


class Impostor(BaseHTTPRequestHandler):
    """Une autre appli sur le même port, qui répond aussi « ok » sur /api/health."""

    def do_GET(self) -> None:
        body = b'{"status": "ok"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


def test_launcher_moves_to_the_next_port_when_another_app_holds_its_own(tmp_path):
    impostor = ThreadingHTTPServer(("127.0.0.1", 0), Impostor)
    taken = impostor.server_address[1]
    Thread(target=impostor.serve_forever, daemon=True).start()
    (tmp_path / "local").mkdir()
    (tmp_path / "local" / "appli.json").write_text(json.dumps({"port": taken}))
    run = launcher(tmp_path)
    try:
        started = run("demarrer")
        assert started.returncode == 0, started.stderr
        assert f"Le port {taken} est pris par un autre programme" in started.stdout
        moved = state(tmp_path)["port"]
        assert moved != taken
        assert f"tourne : http://localhost:{moved}" in run("etat").stdout
        # La fois suivante, il reprend le même port (les préférences du navigateur suivent).
        again = run("demarrer")
        assert again.returncode == 0 and "est pris" not in again.stdout
        assert state(tmp_path)["port"] == moved
    finally:
        run("arreter")
        impostor.shutdown()
    assert state(tmp_path) == {"port": moved}


def test_launcher_keeps_waiting_while_its_server_runs(tmp_path):
    """« --garder » (raccourci Windows) : le lanceur attend tant que son serveur tourne."""
    port = free_port()
    run = launcher(tmp_path, port)
    env = dict(os.environ, CVB_PORT=str(port), CVB_WEB=str(tmp_path / "web"))
    env.update(CVB_DATA=str(tmp_path / "data"), CVB_LOCAL=str(tmp_path / "local"))
    env["CVB_ENV"] = str(tmp_path / ".env")
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)
    keeper = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "appli.py"), "demarrer", "--garder"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(120):
            if "tourne" in run("etat").stdout:
                break
            time.sleep(0.25)
        assert "tourne" in run("etat").stdout
        assert keeper.poll() is None, "le lanceur doit rester en attente"
    finally:
        run("arreter")
    assert keeper.wait(timeout=15) == 0


def test_launcher_refuses_a_port_taken_by_another_program(tmp_path):
    with socket.socket() as other:
        other.bind(("127.0.0.1", 0))
        other.listen()
        port = other.getsockname()[1]
        # Port imposé par CVB_PORT : pas de repli sur un autre.
        out = launcher(tmp_path, port)("demarrer")
    assert out.returncode == 1
    assert f"port {port} est pris" in out.stderr
