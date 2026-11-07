#!/usr/bin/env bash
# Linux, après ./install.sh : le raccourci est-il posé, et un clic dessus lance-t-il
# l'appli ? Lancé par .github/workflows/install.yml, comme l'utilisateur (pas root).
# Windows a son propre essai, côté Windows, dans le même workflow.
set -euxo pipefail
cd "$(dirname "$0")/../.."

entry="$HOME/.local/share/applications/cv-builder-pro.desktop"
test -x "$entry"
test -x "$HOME/Desktop/cv-builder-pro.desktop"
if command -v desktop-file-validate >/dev/null; then desktop-file-validate "$entry"; fi
# Le clic : la ligne Exec du raccourci, sans ouvrir de navigateur.
launch="$(sed -n 's/^Exec=//p' "$entry" | head -1)"
eval "${launch% ouvrir} demarrer"

curl -sf -o /dev/null --retry 60 --retry-all-errors --retry-delay 1 http://127.0.0.1:8000/api/health
curl -sf http://127.0.0.1:8000/api/health | grep -q '"app":"cv-builder-pro"'
curl -sf http://127.0.0.1:8000/ | grep -q 'id="root"'
curl -sf http://127.0.0.1:8000/api/system/check \
  | python3 -c "import json, sys; r = json.load(sys.stdin); assert r['ok'], r"
curl -sf -X POST http://127.0.0.1:8000/api/cvs/base/compile \
  | python3 -c "import json, sys; r = json.load(sys.stdin); assert r['ok'] and r['pages'] == 1, r"

make stop
if curl -sf -o /dev/null http://127.0.0.1:8000/api/health; then
  echo "L'appli tourne encore après make stop" >&2
  exit 1
fi
