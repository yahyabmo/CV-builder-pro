#!/usr/bin/env bash
# La copie de secours de chaque nuit : tout le dossier donnees/ dans une archive datée.
# Les 7 plus récentes sont gardées, les plus anciennes effacées. Les données de l'appli,
# elles, ne sont jamais touchées. Lancé chaque nuit à 3 h par cvb-sauvegarde.timer.
#
#   sudo serveur/sauvegarde.sh            une copie tout de suite
#   ls -lh /var/backups/cv-builder-pro    les copies gardées
set -euo pipefail

ICI="$(cd "$(dirname "$0")" && pwd)"
COPIES="${CVB_COPIES:-/var/backups/cv-builder-pro}"
GARDER=7

mkdir -p "$COPIES"
chmod 700 "$COPIES"
archive="$COPIES/donnees-$(date +%F-%H%M).tar.gz"
tar -czf "$archive.part" -C "$ICI" donnees
mv "$archive.part" "$archive"
chmod 600 "$archive"

# Les plus récentes d'abord ; tout ce qui vient après la 7e est effacé.
ls -1t "$COPIES"/donnees-*.tar.gz | tail -n +$((GARDER + 1)) | xargs -r rm -f --
echo "Copie faite : $archive ($(du -h "$archive" | cut -f1))"
