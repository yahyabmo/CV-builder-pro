"""Pose le raccourci « CV Builder Pro » sur le bureau et parmi les applis du système.

    python3 scripts/raccourci.py            le crée (ou le refait)
    python3 scripts/raccourci.py --retirer  l'enlève
    python3 scripts/raccourci.py --lancer   clique dessus (install.sh s'en sert)

Linux : un lanceur dans le menu des applis et sur le bureau, avec « Arrêter » au
clic droit. Windows (WSL) : un raccourci sur le bureau Windows et dans le menu
Démarrer, plus « Arrêter CV Builder Pro » dans le menu Démarrer. Un clic lance
scripts/appli.py : serveur en arrière-plan, puis navigateur. Seule la bibliothèque
standard de Python.
"""

import base64
import json
import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "CV Builder Pro"
ICON = ROOT / "assets" / "icone.png"
ICON_WINDOWS = ROOT / "assets" / "icone.ico"
LAUNCHER = ROOT / "scripts" / "appli.py"
PYTHON = ROOT / ".venv" / "bin" / "python"
STOP_NAME = f"Arrêter {NAME}"

# Un terminal ouvert dans une appli snap (VS Code…) remplace les modules GIO du système :
# « gio set » échoue alors (« metadata::trusted not supported »). On les retire.
SNAP_VARIABLES = (
    "GIO_MODULE_DIR",
    "GSETTINGS_SCHEMA_DIR",
    "GTK_PATH",
    "GTK_EXE_PREFIX",
    "GTK_IM_MODULE_FILE",
    "GDK_PIXBUF_MODULE_FILE",
)


def _env() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not (key in SNAP_VARIABLES and "/snap/" in value)
    }


def _quiet(*command: str) -> str:
    try:
        out = subprocess.run(command, capture_output=True, text=True, timeout=60, env=_env())
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def _ok(*command: str) -> bool:
    try:
        return subprocess.run(command, capture_output=True, timeout=60, env=_env()).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


# --- Linux ------------------------------------------------------------------------------


def desktop_dir() -> Path | None:
    """Le bureau de l'utilisateur, même nommé autrement (~/Bureau…), s'il existe."""
    home = Path.home()
    named = _quiet("xdg-user-dir", "DESKTOP")
    for candidate in (Path(named) if named else None, home / "Desktop"):
        if candidate and candidate != home and candidate.is_dir():
            return candidate
    return None


def _exec(action: str) -> str:
    """La ligne Exec d'un fichier .desktop : chemins entre guillemets (espaces permis)."""

    def quote(path: Path) -> str:
        text = str(path).replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")
        return f'"{text}"'

    return f"{quote(PYTHON)} {quote(LAUNCHER)} {action}"


def desktop_entry() -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        f"Name={NAME}\n"
        "Comment=Adapter son CV à chaque offre d'emploi\n"
        f"Exec={_exec('ouvrir')}\n"
        f"Icon={ICON}\n"
        "Terminal=false\n"
        "Categories=Office;\n"
        "Keywords=CV;resume;emploi;job;LaTeX;\n"
        "StartupNotify=false\n"
        "Actions=arreter;\n"
        "\n"
        "[Desktop Action arreter]\n"
        f"Name={STOP_NAME}\n"
        f"Exec={_exec('arreter')}\n"
    )


def linux_paths() -> list[Path]:
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    paths = [data / "applications" / "cv-builder-pro.desktop"]
    desktop = desktop_dir()
    if desktop:
        paths.append(desktop / "cv-builder-pro.desktop")
    return paths


def create_linux() -> list[str]:
    entry = desktop_entry()
    made = []
    for path in linux_paths():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry)
        path.chmod(0o755)
        made.append(path)
    if len(made) > 1:
        # Sans cette marque, le bureau d'Ubuntu demande « Autoriser le lancement ».
        _ok("gio", "set", "-t", "string", str(made[1]), "metadata::trusted", "true")
    _ok("update-desktop-database", str(made[0].parent))
    return [str(path) for path in made]


def remove_linux() -> list[str]:
    gone = []
    for path in linux_paths():
        if path.is_file():
            path.unlink()
            gone.append(str(path))
    return gone


# --- Windows (WSL) ----------------------------------------------------------------------


def _powershell() -> str | None:
    found = shutil.which("powershell.exe")
    if found:
        return found
    default = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
    return str(default) if default.exists() else None


def ps_literal(text: str) -> str:
    """Une chaîne PowerShell entre apostrophes (les apostrophes y sont doublées)."""
    return "'" + text.replace("'", "''") + "'"


def run_powershell(script: str) -> str:
    """Lance un script PowerShell sous Windows ; il passe encodé, sans souci d'échappement."""
    powershell = _powershell()
    if not powershell:
        raise RuntimeError("powershell.exe introuvable : l'accès à Windows depuis WSL est coupé")
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    out = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True,
        timeout=120,
    )
    text = out.stdout.decode("utf-8", errors="replace").strip()
    if out.returncode != 0:
        error = out.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"PowerShell a échoué : {error or text}")
    return text


def windows_command(action: str) -> str:
    """La commande d'un raccourci Windows : le lanceur, dans cette distribution WSL.

    --exec lance le programme sans passer par le shell d'Ubuntu : les chemins arrivent
    tels quels.
    """
    distribution = os.environ.get("WSL_DISTRO_NAME") or "Ubuntu"
    user = pwd.getpwuid(os.getuid()).pw_name
    return (
        f"& wsl.exe -d {ps_literal(distribution)} -u {ps_literal(user)} --exec "
        f"{ps_literal(str(PYTHON))} {ps_literal(str(LAUNCHER))} {action}"
    )


def windows_arguments(action: str) -> str:
    """Les arguments de powershell.exe : fenêtre cachée, puis la commande du lanceur."""
    return f'-NoProfile -WindowStyle Hidden -Command "{windows_command(action)}"'


def shortcut_script(icon: str) -> str:
    """Le script PowerShell qui pose les trois raccourcis et renvoie leurs chemins (JSON)."""
    open_args = ps_literal(windows_arguments("ouvrir --garder"))
    stop_args = ps_literal(windows_arguments("arreter"))
    app_lnk = ps_literal(NAME + ".lnk")
    stop_lnk = ps_literal(STOP_NAME + ".lnk")
    return f"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$shell = New-Object -ComObject WScript.Shell
$ps = Join-Path $env:SystemRoot 'System32\\WindowsPowerShell\\v1.0\\powershell.exe'
$icon = {ps_literal(icon)}
function Make($path, $arguments, $description) {{
  $s = $shell.CreateShortcut($path)
  $s.TargetPath = $ps
  $s.Arguments = $arguments
  $s.WindowStyle = 7
  $s.IconLocation = "$icon,0"
  $s.Description = $description
  $s.WorkingDirectory = $env:USERPROFILE
  $s.Save()
  $path
}}
$desktop = [Environment]::GetFolderPath('Desktop')
$programs = [Environment]::GetFolderPath('Programs')
ConvertTo-Json -Compress -InputObject @(
  (Make (Join-Path $desktop {app_lnk}) {open_args} 'Adapter son CV à chaque offre'),
  (Make (Join-Path $programs {app_lnk}) {open_args} 'Adapter son CV à chaque offre'),
  (Make (Join-Path $programs {stop_lnk}) {stop_args} 'Arrêter le serveur de CV Builder Pro')
)
"""


def windows_local_appdata() -> str:
    return run_powershell(
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n$env:LOCALAPPDATA"
    )


def to_wsl(windows_path: str) -> Path:
    out = subprocess.run(["wslpath", "-u", windows_path], capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError(f"chemin Windows illisible depuis WSL : {windows_path}")
    return Path(out.stdout.strip())


def create_windows() -> list[str]:
    # L'icône est copiée côté Windows : lue dans Ubuntu, elle resterait vide tant que
    # WSL n'a pas démarré.
    folder = windows_local_appdata() + "\\" + NAME
    target = to_wsl(folder)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ICON_WINDOWS, target / "icone.ico")
    made = json.loads(run_powershell(shortcut_script(folder + "\\icone.ico")))
    return made if isinstance(made, list) else [made]


def remove_windows() -> list[str]:
    script = f"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$desktop = [Environment]::GetFolderPath('Desktop')
$programs = [Environment]::GetFolderPath('Programs')
$paths = @(
  (Join-Path $desktop {ps_literal(NAME + ".lnk")}),
  (Join-Path $programs {ps_literal(NAME + ".lnk")}),
  (Join-Path $programs {ps_literal(STOP_NAME + ".lnk")}),
  (Join-Path $env:LOCALAPPDATA {ps_literal(NAME)})
)
$gone = @($paths | Where-Object {{ Test-Path -LiteralPath $_ }})
$gone | ForEach-Object {{ Remove-Item -LiteralPath $_ -Recurse -Force }}
ConvertTo-Json -Compress -InputObject $gone
"""
    gone = json.loads(run_powershell(script) or "[]")
    return gone if isinstance(gone, list) else [gone]


def launch_windows() -> None:
    """Un clic sur le raccourci du menu Démarrer, depuis WSL."""
    run_powershell(
        "Start-Process -FilePath (Join-Path ([Environment]::GetFolderPath('Programs')) "
        f"{ps_literal(NAME + '.lnk')})"
    )


# --- Commande ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    if not sys.platform.startswith("linux"):
        print("Raccourci prévu pour Linux et Windows (WSL) seulement.")
        return 1
    windows = is_wsl()
    try:
        if "--lancer" in argv:
            if windows:
                launch_windows()
            else:
                subprocess.Popen(
                    [str(PYTHON), str(LAUNCHER), "ouvrir"],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            return 0
        if "--retirer" in argv:
            gone = remove_windows() if windows else remove_linux()
            print("Raccourci retiré." if gone else "Pas de raccourci à retirer.")
            return 0
        made = create_windows() if windows else create_linux()
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as error:
        print(f"Raccourci non posé : {error}", file=sys.stderr)
        return 1
    print(f"Raccourci « {NAME} » posé :")
    for path in made:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
