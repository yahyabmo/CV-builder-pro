#!/usr/bin/env bash
# Les captures du README (docs/captures/), sur un serveur d'essai à part (ports 8001
# et 5174) et une copie jetable du CV fictif. Tes données (data/, local/) ne sont
# jamais lues ni modifiées.
#
#   frontend/scripts/run-captures.sh        (depuis la racine, via make captures)

set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export E2E_DATA="$ROOT/build/captures-data"
export E2E_LOCAL="$ROOT/build/captures-local"
OUT="$ROOT/docs/captures"
PY="$ROOT/.venv/bin/python"

rm -rf "$E2E_DATA" "$E2E_LOCAL"
mkdir -p "$E2E_DATA" "$E2E_LOCAL" "$OUT"

(cd "$ROOT/backend" && CVB_DATA="$E2E_DATA" CVB_LOCAL="$E2E_LOCAL" CVB_ENV="$E2E_LOCAL/.env" RELAIS_URL=http://127.0.0.1:8002 \
  exec "$PY" -m uvicorn app.main:app --port 8001 --log-level warning) &
api=$!
(cd "$ROOT/frontend" && CVB_PORT=5174 CVB_API=http://127.0.0.1:8001 \
  exec node node_modules/vite/bin/vite.js --host 127.0.0.1 --logLevel warn) &
app=$!
trap 'kill $api $app 2>/dev/null; wait 2>/dev/null' EXIT

curl -s -o /dev/null --retry 60 --retry-connrefused --retry-delay 1 http://127.0.0.1:8001/api/health
curl -s -o /dev/null --retry 60 --retry-connrefused --retry-delay 1 http://127.0.0.1:5174/

cd "$ROOT/frontend" || exit 1
node scripts/captures.mjs "$OUT"
