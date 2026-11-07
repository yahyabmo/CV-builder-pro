"""Le lanceur de CV Builder Pro : ce que fait un clic sur le raccourci.

    python3 scripts/appli.py ouvrir     démarre le serveur au besoin, puis ouvre le navigateur
    python3 scripts/appli.py demarrer   démarre le serveur en arrière-plan, sans navigateur
    python3 scripts/appli.py arreter    arrête le serveur lancé par le raccourci
    python3 scripts/appli.py etat       dit si l'appli tourne, et à quelle adresse

« ouvrir --garder » (raccourci Windows) reste ensuite en attente tant que le serveur
tourne : sous WSL, Windows referme Ubuntu, et le serveur avec, quand plus aucune
commande lancée depuis Windows n'y tourne.

Le port est 8000. S'il est pris par un autre programme, le lanceur prend le premier
port libre suivant et le garde pour les fois suivantes (local/appli.json). CVB_PORT
impose un port, sans repli. Le serveur tourne sans fenêtre ; son journal est dans
local/serveur.log. Seule la bibliothèque standard de Python.
"""

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = Path(os.environ.get("CVB_LOCAL") or ROOT / "local")
WEB = Path(os.environ.get("CVB_WEB") or ROOT / "frontend" / "dist")
STATE = LOCAL / "appli.json"
LOG_FILE = LOCAL / "serveur.log"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
APP = "cv-builder-pro"
DEFAULT_PORT = 8000
FIXED_PORT = os.environ.get("CVB_PORT")


def wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def windows_program(name: str) -> str | None:
    """Un programme de Windows (explorer.exe, powershell.exe…), vu depuis WSL."""
    found = shutil.which(name)
    if found:
        return found
    for folder in ("/mnt/c/Windows", "/mnt/c/Windows/System32"):
        candidate = Path(folder) / name
        if candidate.exists():
            return str(candidate)
    candidate = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0") / name
    return str(candidate) if candidate.exists() else None


def url(port: int) -> str:
    return f"http://localhost:{port}"


def open_browser(address: str) -> None:
    """Le navigateur par défaut ; sous WSL, celui de Windows."""
    explorer = windows_program("explorer.exe") if wsl() else None
    if explorer:
        subprocess.run([explorer, address], capture_output=True)
    else:
        webbrowser.open(address)


def ours(port: int) -> bool:
    """CV Builder Pro répond-il sur ce port ? Une autre appli peut aussi avoir /api/health."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as reply:
            return json.load(reply).get("app") == APP
    except (OSError, ValueError, AttributeError):
        return False


def free(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) != 0


def load() -> dict:
    try:
        state = json.loads(STATE.read_text())
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def save(state: dict) -> None:
    LOCAL.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state))


def port() -> int:
    """Le port voulu : CVB_PORT, sinon celui de la dernière fois, sinon 8000."""
    if FIXED_PORT:
        return int(FIXED_PORT)
    saved = load().get("port")
    return saved if isinstance(saved, int) and 0 < saved < 65536 else DEFAULT_PORT


def tell(message: str, error: bool = False) -> None:
    """Un message visible même sans terminal : notification ou fenêtre, et la sortie."""
    print(message, file=sys.stderr if error else sys.stdout)
    if wsl():
        powershell = windows_program("powershell.exe")
        if error and powershell:
            text = message.replace("'", "''")
            box = (
                "Add-Type -AssemblyName PresentationFramework; "
                f"[System.Windows.MessageBox]::Show('{text}', 'CV Builder Pro') | Out-Null"
            )
            subprocess.run([powershell, "-NoProfile", "-Command", box], capture_output=True)
    elif os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        subprocess.run(["notify-send", "CV Builder Pro", message], capture_output=True)


def start() -> tuple[int, int | None] | None:
    """Démarre le serveur s'il ne tourne pas.

    Renvoie (port, numéro du serveur lancé ici, ou None s'il tournait déjà), ou None
    en cas d'échec.
    """
    wanted = port()
    if ours(wanted):
        return wanted, None
    chosen = wanted
    if not free(wanted):
        taken = f"Le port {wanted} est pris par un autre programme"
        if FIXED_PORT:
            tell(f"{taken} : l'appli ne peut pas démarrer.", error=True)
            return None
        chosen = next((p for p in range(wanted + 1, wanted + 100) if free(p)), 0)
        if not chosen:
            tell(f"{taken}, et aucun des 99 suivants n'est libre.", error=True)
            return None
        tell(f"{taken} : CV Builder Pro passe sur le {chosen}.")
    if not (WEB / "index.html").exists():
        tell("L'interface n'est pas construite : relance ./install.sh.", error=True)
        return None
    LOCAL.mkdir(parents=True, exist_ok=True)
    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    with LOG_FILE.open("ab") as log:
        server = subprocess.Popen(
            [python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1"]
            + ["--port", str(chosen), "--log-level", "warning"],
            cwd=ROOT / "backend",
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    save({"port": chosen, "pid": server.pid})
    for _ in range(120):
        if ours(chosen):
            return chosen, server.pid
        if server.poll() is not None:
            break
        time.sleep(0.25)
    tail = LOG_FILE.read_text(errors="replace").strip().splitlines()[-1:]
    tell("L'appli n'a pas démarré. " + (tail[0] if tail else f"Voir {LOG_FILE}"), error=True)
    return None


def stop() -> bool:
    state = load()
    current = port()
    pid = state.get("pid")
    if isinstance(pid, int) and _is_our_server(pid):
        os.killpg(pid, signal.SIGTERM)
        for _ in range(40):
            if not ours(current):
                break
            time.sleep(0.25)
    state.pop("pid", None)
    if state:
        save(state)
    if ours(current):
        print("L'appli tourne, mais pas depuis le raccourci : arrête-la là où tu l'as lancée.")
        return False
    print("CV Builder Pro est arrêtée.")
    return True


def _is_our_server(pid: int) -> bool:
    """Le numéro enregistré est-il encore notre serveur ? (il a pu être réattribué)"""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
    except (OSError, UnicodeDecodeError):
        return False
    return "uvicorn" in command and "app.main:app" in command


def main(argv: list[str]) -> int:
    action = argv[0] if argv else "ouvrir"
    if action in ("ouvrir", "demarrer"):
        started = start()
        if started is None:
            return 1
        current, pid = started
        if action == "ouvrir":
            open_browser(url(current))
        if "--garder" in argv and pid:
            while _is_our_server(pid):
                time.sleep(3)
        return 0
    if action == "arreter":
        return 0 if stop() else 1
    if action == "etat":
        current = port()
        if ours(current):
            print(f"CV Builder Pro tourne : {url(current)}")
        else:
            print("CV Builder Pro est arrêtée.")
        return 0
    if action == "navigateur" and len(argv) > 1:
        # Pour « make start » : ouvre l'appli sur ce port (navigateur de Windows sous WSL).
        open_browser(url(int(argv[1])))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
