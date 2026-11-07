#!/usr/bin/env bash
# CV Builder Pro : installation ou mise à jour en une commande, sous Linux (Ubuntu,
# Debian) ou Windows (dans WSL, le Linux intégré à Windows).
#
#   ./install.sh                installe ce qui manque, prépare l'appli, pose le raccourci, l'ouvre
#   ./install.sh --sans-ouvrir  pareil, sans ouvrir l'appli à la fin
#
# Le mot de passe (sudo) n'est demandé que s'il faut installer des logiciels du système.
# Relancer le script met l'appli à jour. Le détail de chaque étape est dans SETUP.md.
set -euo pipefail
cd "$(dirname "$0")"

OPEN=1
for arg in "$@"; do
  case "$arg" in
    --sans-ouvrir) OPEN=0 ;;
    -h | --help) sed -n '2,9p' "$0" | cut -c3-; exit 0 ;;
    *) echo "Option inconnue : $arg (voir ./install.sh --help)" >&2; exit 2 ;;
  esac
done

if [ -t 1 ]; then BOLD=$'\033[1m' BLUE=$'\033[34m' RED=$'\033[31m' GREEN=$'\033[32m' RESET=$'\033[0m'
else BOLD="" BLUE="" RED="" GREEN="" RESET=""; fi
step() { printf '\n%s==>%s %s%s%s\n' "$BLUE" "$RESET" "$BOLD" "$*" "$RESET"; }
fail() { printf '\n%sErreur :%s %s\n' "$RED" "$RESET" "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || fail "lance ce script sans sudo : il le demande lui-même si besoin."
[ "$(uname -s)" = Linux ] || fail "CV Builder Pro s'installe sous Linux, ou sous Windows dans WSL (voir SETUP.md)."
command -v apt-get >/dev/null || fail "il faut Ubuntu ou Debian (apt). Sinon : Docker, voir SETUP.md."
WSL=0
grep -qi microsoft /proc/version 2>/dev/null && WSL=1
# Sur le disque Windows (/mnt/c…), Python ne sait pas créer .venv et tout est très lent.
if [ "$WSL" = 1 ] && [[ "$PWD" == /mnt/* ]]; then
  fail "le projet est sur le disque Windows ($PWD). Place-le dans Ubuntu : « cd » puis « git clone … » (voir SETUP.md)."
fi

NODE_MIN="20.19"
# Ce que le CV demande à LaTeX.
LATEX_FILES="fontspec.sty enumitem.sty tikz.sty hyperref.sty xcolor.sty geometry.sty graphicx.sty french.ldf"
# libatomic1 : Node.js 26 en a besoin, et une Ubuntu minimale ne l'a pas.
APT_PACKAGES="git make curl ca-certificates libatomic1 python3 python3-venv texlive-xetex
  texlive-latex-extra texlive-pictures texlive-lang-french latexmk poppler-utils"

python_ok() { "$1" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; }
find_python() {
  for candidate in python3.13 python3.12 python3; do
    if command -v "$candidate" >/dev/null && python_ok "$candidate"; then command -v "$candidate"; return; fi
  done
}
load_nvm() {
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  # nvm.sh ne supporte ni -e ni -u.
  if [ -s "$NVM_DIR/nvm.sh" ]; then set +eu; . "$NVM_DIR/nvm.sh"; set -eu; fi
}
node_ok() {
  command -v node >/dev/null && node -e '
    const [a, b] = process.versions.node.split(".").map(Number);
    const [x, y] = process.argv[1].split(".").map(Number);
    process.exit(a > x || (a === x && b >= y) ? 0 : 1)' "$NODE_MIN"
}
latex_ok() {
  command -v xelatex >/dev/null && command -v latexmk >/dev/null || return 1
  for file in $LATEX_FILES; do [ -n "$(kpsewhich "$file" 2>/dev/null)" ] || return 1; done
}
# Ouvre l'appli : sous Windows, par le raccourci du menu Démarrer, pour qu'elle survive
# à la fin de ce script (WSL referme Ubuntu quand plus rien n'y tourne depuis Windows).
open_app() {
  if [ "$WSL" = 1 ]; then
    .venv/bin/python scripts/raccourci.py --lancer
  else
    .venv/bin/python scripts/appli.py ouvrir
  fi
}

# --- Mise à jour du code, si c'est un clone Git --------------------------------------
WAS_RUNNING=0
if [ -x .venv/bin/python ] && .venv/bin/python scripts/appli.py etat 2>/dev/null | grep -q tourne; then
  WAS_RUNNING=1
  .venv/bin/python scripts/appli.py arreter >/dev/null || true
fi
if [ -d .git ] && git rev-parse --abbrev-ref '@{upstream}' >/dev/null 2>&1; then
  step "Mise à jour du code"
  git pull --ff-only || echo "Pas de mise à jour automatique (modifications locales ?) : je continue avec ce code."
fi

# --- Logiciels du système -----------------------------------------------------------
missing=()
for package in $APT_PACKAGES; do
  dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q "install ok installed" || missing+=("$package")
done
if [ ${#missing[@]} -gt 0 ]; then
  step "Installation des logiciels du système : ${missing[*]}"
  echo "LaTeX pèse environ 1 Go : compte quelques minutes."
  sudo env DEBIAN_FRONTEND=noninteractive apt-get update -q
  sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${missing[@]}"
fi
PYTHON="$(find_python)"
if [ -z "$PYTHON" ]; then
  # Ubuntu 22.04 n'a que Python 3.10 : le dépôt deadsnakes apporte 3.13.
  . /etc/os-release
  [ "${ID:-}" = ubuntu ] || fail "il faut Python 3.12 ou plus récent ; ta distribution n'en propose pas."
  step "Installation de Python 3.13 (dépôt deadsnakes)"
  sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -q software-properties-common
  sudo add-apt-repository -y ppa:deadsnakes/ppa
  sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3.13 python3.13-venv
  PYTHON="$(command -v python3.13)"
fi
if ! "$PYTHON" -c 'import ensurepip' 2>/dev/null; then
  version="$("$PYTHON" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
  step "Installation du module venv de Python $version"
  sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -q "python$version-venv"
fi
load_nvm
if ! node_ok; then
  step "Installation de Node.js (nvm, dans ton dossier personnel)"
  curl -fsSL -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
  load_nvm
  set +eu; nvm install --lts; set -eu
fi
node_ok || fail "Node.js $NODE_MIN ou plus récent est introuvable."
latex_ok || fail "LaTeX est incomplet : lance « make doctor » pour le détail."

# --- L'appli ------------------------------------------------------------------------
step "Préparation de l'appli (dépendances Python et interface)"
make install PYTHON="$PYTHON"
make build

step "Vérification"
make doctor PYTHON="$PYTHON" || fail "la vérification signale un manque (ci-dessus)."

if [ "$WSL" = 1 ]; then step "Raccourci sur le bureau Windows et dans le menu Démarrer"
else step "Raccourci sur le bureau et dans le menu des applis"; fi
.venv/bin/python scripts/raccourci.py

if [ "$OPEN" = 1 ] || [ "$WAS_RUNNING" = 1 ]; then
  step "Ouverture de CV Builder Pro"
  open_app || fail "l'appli n'a pas démarré : voir local/serveur.log"
fi

printf '\n%sC'"'"'est prêt.%s ' "$GREEN" "$RESET"
if [ "$WSL" = 1 ]; then
  echo "Clique sur « CV Builder Pro », sur le bureau Windows ou dans le menu Démarrer."
  echo "Pour l'arrêter : « Arrêter CV Builder Pro » dans le menu Démarrer."
else
  echo "Clique sur « CV Builder Pro », sur ton bureau ou dans tes applis."
  echo "Pour l'arrêter : clic droit sur l'icône › Arrêter, ou « make stop »."
fi
