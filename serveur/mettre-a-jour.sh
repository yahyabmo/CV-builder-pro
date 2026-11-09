#!/usr/bin/env bash
# Met l'appli à la dernière version du dépôt, sans toucher aux données.
#
#   sudo serveur/mettre-a-jour.sh
set -euo pipefail

ICI="$(cd "$(dirname "$0")" && pwd)"
cd "$ICI/.."
# Une copie de secours avant chaque mise à jour, au cas où.
"$ICI/sauvegarde.sh"
git pull --ff-only
cd "$ICI"
docker compose up -d --build
docker image prune -f >/dev/null
echo "À jour : $(git -C "$ICI/.." log --oneline -1)"
