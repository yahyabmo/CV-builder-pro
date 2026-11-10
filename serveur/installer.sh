#!/usr/bin/env bash
# Prépare un serveur Ubuntu 24.04 neuf pour CV Builder Pro en ligne. À lancer une fois,
# en root, depuis le dossier cloné (étape 8 de serveur/README.md) :
#
#   sudo serveur/installer.sh
#
# Il installe Docker, ferme tous les ports sauf SSH, active les mises à jour de sécurité
# automatiques, prépare serveur/.env et le dossier des données, et programme la copie de
# secours de chaque nuit. Le relancer ne casse rien.
set -euo pipefail

ICI="$(cd "$(dirname "$0")" && pwd)"
[ "$(id -u)" -eq 0 ] || { echo "À lancer avec sudo." >&2; exit 1; }

echo "1/5 Paquets : Docker, pare-feu, mises à jour automatiques"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q docker.io docker-compose-v2 git ufw unattended-upgrades
systemctl enable --now docker
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "2/5 Pare-feu : SSH seulement (le site passe par le tunnel, sans port ouvert)"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw --force enable

echo "3/5 Réglages : serveur/.env"
if [ ! -f "$ICI/.env" ]; then
  install -m 600 "$ICI/env.exemple" "$ICI/.env"
  echo "    serveur/.env créé : remplis-le (README, étape 9)."
else
  chmod 600 "$ICI/.env"
  echo "    serveur/.env existe déjà : gardé tel quel."
fi
# Le secret qui chiffre les clés des utilisateurs : tiré au hasard une fois, jamais affiché.
if grep -q '^CVB_SECRET=$' "$ICI/.env"; then
  sed -i "s/^CVB_SECRET=\$/CVB_SECRET=$(openssl rand -hex 32)/" "$ICI/.env"
  echo "    secret de chiffrement des clés : créé."
fi

echo "4/5 Données : serveur/donnees (à l'utilisateur de l'appli, uid 1000)"
mkdir -p "$ICI/donnees"
chown -R 1000:1000 "$ICI/donnees"
chmod 700 "$ICI/donnees"

echo "5/5 Copie de secours chaque nuit à 3 h (les 7 dernières gardées)"
cat > /etc/systemd/system/cvb-sauvegarde.service <<UNIT
[Unit]
Description=Copie de secours de CV Builder Pro

[Service]
Type=oneshot
ExecStart=$ICI/sauvegarde.sh
UNIT
cat > /etc/systemd/system/cvb-sauvegarde.timer <<UNIT
[Unit]
Description=Copie de secours de CV Builder Pro, chaque nuit

[Timer]
OnCalendar=*-*-* 03:00:00
RandomizedDelaySec=10min
Persistent=true

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now cvb-sauvegarde.timer

echo
echo "Serveur prêt. Il reste :"
echo "  1. remplir serveur/.env :   sudo nano $ICI/.env"
echo "  2. démarrer :               cd $ICI && sudo docker compose up -d --build"
echo "  3. vérifier :               sudo docker compose ps"
