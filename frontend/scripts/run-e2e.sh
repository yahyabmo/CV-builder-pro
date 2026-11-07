#!/usr/bin/env bash
# Essais de l'interface sur une copie jetable du CV fictif : un backend (port 8001)
# et une interface (port 5174) à part, arrêtés à la fin. Tes données (data/,
# local/) et ton .env ne sont jamais lus ni modifiés : le backend d'essai a son
# propre .env, avec une fausse clé Gemini (elle ne doit jamais ressortir de l'API).
#
#   frontend/scripts/run-e2e.sh        (depuis la racine, via make e2e)

set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DATA="$ROOT/build/e2e-data"
LOCAL="$ROOT/build/e2e-local"
OUT="$ROOT/build/e2e"
PY="$ROOT/.venv/bin/python"

rm -rf "$DATA" "$LOCAL" "$OUT"
mkdir -p "$DATA/cvs/essai-ui" "$LOCAL" "$OUT"
cp "$ROOT/demo/content.json" "$ROOT/demo/style.json" "$ROOT/demo/imgcv.jpg" "$DATA/cvs/essai-ui/"
printf '{"name": "Essai interface", "kind": "cv"}\n' > "$DATA/cvs/essai-ui/meta.json"
printf 'GEMINI_API_KEY=AIzaFausseCleDesEssaisDeLInterface000\n' > "$LOCAL/.env"

(cd "$ROOT/backend" && CVB_DATA="$DATA" CVB_LOCAL="$LOCAL" CVB_ENV="$LOCAL/.env" RELAIS_URL=http://127.0.0.1:8002 \
  exec "$PY" -m uvicorn app.main:app --port 8001 --log-level warning) &
api=$!
(cd "$ROOT/frontend" && CVB_PORT=5174 CVB_API=http://127.0.0.1:8001 \
  exec node node_modules/vite/bin/vite.js --host 127.0.0.1 --logLevel warn) &
app=$!
trap 'kill $api $app 2>/dev/null; wait 2>/dev/null' EXIT

curl -s -o /dev/null --retry 60 --retry-connrefused --retry-delay 1 http://127.0.0.1:8001/api/health
curl -s -o /dev/null --retry 60 --retry-connrefused --retry-delay 1 http://127.0.0.1:5174/
# Les parcours partent d'une appli déjà accueillie ; e2e-welcome rouvre l'accueil lui-même.
curl -s -o /dev/null -X POST http://127.0.0.1:8001/api/welcome/dismiss

cd "$ROOT/frontend" || exit 1
node scripts/e2e.mjs "$OUT" &&
  node scripts/e2e-style.mjs "$OUT" "$ROOT/demo/imgcv.jpg" &&
  node scripts/e2e-library.mjs "$OUT" &&
  node scripts/e2e-target.mjs "$OUT" &&
  node scripts/e2e-latex.mjs "$OUT" &&
  node scripts/e2e-editor.mjs "$OUT" &&
  node scripts/e2e-welcome.mjs "$OUT"
