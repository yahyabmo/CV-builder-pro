# CV Builder Pro en ligne

Ce guide met l'appli en ligne : on l'ouvre par un lien, on se connecte avec son e-mail,
sans rien installer. Il se suit une seule fois, dans l'ordre. Compte une heure.

Ce qu'on met en place :

- **un serveur** chez OVHcloud (VPS-1 : Ubuntu 24.04, 2 processeurs, 4 Go) : il fait tourner l'appli ;
- **un domaine** chez Cloudflare : l'adresse du site ;
- **Cloudflare Access** : la page de connexion. Une personne donne son e-mail, reçoit un code,
  et n'entre que si elle est invitée ;
- **un tunnel Cloudflare** : le serveur va vers Cloudflare, jamais l'inverse. Aucun port du
  serveur n'est ouvert sur Internet, hormis SSH.

Ensuite, tout se gère depuis le site, page **Administration** : inviter, retirer, voir les CV.

Les noms des menus de Cloudflare changent parfois un peu : cherche le plus proche.

---

## 1. Le serveur

1. Sur [ovhcloud.com/fr/vps](https://www.ovhcloud.com/fr/vps/), **VPS-1** › **Configurer** :
   - engagement : **Aucun engagement** ;
   - localisation : une ville en Europe disponible (en novembre 2026, seule Prague l'était) ;
   - image : **Distribution uniquement › Ubuntu 24.04** ;
   - options : **Sauvegarde automatique Premium** si elle est proposée (7 jours de copies du
     serveur entier, hors du serveur), rien d'autre.
2. Si une clé SSH est demandée, colle la tienne (`cat ~/.ssh/id_ed25519.pub` sur ton PC ; si
   elle n'existe pas : `ssh-keygen -t ed25519`).
3. OVH envoie par e-mail l'adresse IPv4 et l'utilisateur **`ubuntu`** (pas `root`) : toutes les
   commandes du serveur se lancent avec `sudo`.

Autre hébergeur : n'importe quel serveur Ubuntu 24.04 avec 2 processeurs et 4 Go convient.

## 2. Le domaine

1. Sur [dash.cloudflare.com](https://dash.cloudflare.com), **Domaines › Acheter un domaine**
   (par exemple `cvbuilderpro.fr`, environ 10 € par an).
2. Choisis l'adresse du site, par exemple `app.cvbuilderpro.fr`. On s'en sert aux étapes 4 et 5.

## 3. Cloudflare Zero Trust

1. Ouvre [one.dash.cloudflare.com](https://one.dash.cloudflare.com).
2. Choisis un **nom d'équipe** (par exemple `cv-pro`) : ton domaine d'équipe sera
   `cv-pro.cloudflareaccess.com`. Note-le.
3. Choisis l'offre **Free** (jusqu'à 50 personnes).
4. Dans **Paramètres › Authentification**, vérifie que **One-time PIN** est actif : c'est la
   connexion par code reçu par e-mail.

## 4. La liste des invités et la protection du site

1. **Access › Rule groups** (ou « Access groups ») › **Ajouter un groupe** :
   - nom : `CV Builder Pro, invités` ;
   - règle **Include › Emails** : ton adresse.

   Enregistre. Dans l'adresse de la page du groupe, ou dans ses détails, note son **identifiant**.
2. **Access › Applications › Ajouter › Self-hosted** :
   - nom : `CV Builder Pro` ;
   - domaine : `app.cvbuilderpro.fr` ;
   - durée de session : 7 jours (la personne retape un code une fois par semaine) ;
   - politique : **Allow**, règle **Include › Rule group › CV Builder Pro, invités**.

   Enregistre, puis note l'**Application Audience (AUD) Tag** de l'application.
3. Facultatif : **Paramètres › Pages personnalisées › Page de connexion** : ton logo
   (`assets/icone.png`), la couleur `#2D43A3`.

## 5. Le tunnel

1. **Réseaux › Tunnels › Créer un tunnel › Cloudflared**, nom : `cv-builder`.
2. Dans le choix de l'environnement, prends **Docker** : la commande affichée contient le
   **jeton** (la longue suite après `--token`). Copie seulement le jeton.
3. **Nom d'hôte public** : sous-domaine `app`, domaine `cvbuilderpro.fr`, service
   **HTTP** `app:8000`.

## 6. La clé qui laisse ton site tenir la liste des invités

1. Sur [dash.cloudflare.com/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens),
   **Créer un jeton › Jeton personnalisé** :
   - nom : `CV Builder Pro, invités` ;
   - autorisation : **Compte › Access: Organizations, Identity Providers, and Groups ›
     Modifier**, et rien d'autre ;
   - ressources du compte : ton compte.
2. Copie le jeton (il n'est montré qu'une fois).
3. Note l'**identifiant du compte** (page d'accueil du tableau de bord, colonne de droite,
   « Account ID »).

## 7. Le code du relais Gemini pour le serveur

Sur ton PC, dans `relais/` :

```bash
npm run code -- serveur "En ligne"
```

Copie le code affiché. Le quota de 20 demandes par jour comptera par personne connectée.

## 8. Installer le serveur

```bash
ssh ubuntu@<adresse IPv4>
sudo git clone https://github.com/yahyabmo/CV-builder-pro.git /srv/cv-builder-pro
sudo /srv/cv-builder-pro/serveur/installer.sh
```

Il installe Docker, ferme les ports, active les mises à jour de sécurité, programme la copie
de secours de chaque nuit et crée `serveur/.env`.

## 9. Les réglages, puis le démarrage

```bash
sudo nano /srv/cv-builder-pro/serveur/.env
```

| Ligne | Valeur |
|---|---|
| `CVB_ADMIN` | ton adresse e-mail |
| `CF_ACCESS_TEAM` | le domaine d'équipe (étape 3), par exemple `cv-pro.cloudflareaccess.com` |
| `CF_ACCESS_AUD` | l'AUD Tag (étape 4) |
| `TUNNEL_TOKEN` | le jeton du tunnel (étape 5) |
| `CF_ACCOUNT_ID` | l'identifiant du compte (étape 6) |
| `CF_ACCESS_GROUP_ID` | l'identifiant du groupe (étape 4) |
| `CF_API_TOKEN` | le jeton de l'étape 6 |
| `RELAIS_CODE` | le code de l'étape 7 |

```bash
cd /srv/cv-builder-pro/serveur
sudo docker compose up -d --build     # 5 à 10 minutes la première fois (LaTeX)
sudo docker compose ps                # « app » doit finir en « healthy »
```

Ouvre `https://app.cvbuilderpro.fr` : la page de connexion de Cloudflare demande ton e-mail,
puis le code reçu. Tu arrives dans l'appli, avec la page **Administration**. Invite une
première personne pour essayer.

---

## Au quotidien

| Pour | Commande, sur le serveur |
|---|---|
| Mettre l'appli à jour | `sudo /srv/cv-builder-pro/serveur/mettre-a-jour.sh` (une copie de secours d'abord) |
| Voir les copies de secours | `ls -lh /var/backups/cv-builder-pro` |
| Faire une copie tout de suite | `sudo /srv/cv-builder-pro/serveur/sauvegarde.sh` |
| Voir les erreurs de l'appli | `cd /srv/cv-builder-pro/serveur && sudo docker compose logs --tail 100 app` |

### Les copies de secours

Chaque nuit à 3 h, tout le dossier `serveur/donnees` part dans une archive datée de
`/var/backups/cv-builder-pro`. Les 7 plus récentes sont gardées. Les données de l'appli,
elles, ne sont jamais effacées : seules les vieilles copies le sont.

Récupérer un CV supprimé (ici celui d'une personne, depuis la copie de la veille) :

```bash
cd /tmp && tar -xzf /var/backups/cv-builder-pro/donnees-<date>.tar.gz
ls /tmp/donnees/data/users/<e-mail>/cvs/
sudo cp -a /tmp/donnees/data/users/<e-mail>/cvs/<cv> /srv/cv-builder-pro/serveur/donnees/data/users/<e-mail>/cvs/
```

Tout remettre comme la nuit dernière :

```bash
cd /srv/cv-builder-pro/serveur && sudo docker compose stop app
sudo mv donnees donnees.avant && sudo tar -xzf /var/backups/cv-builder-pro/donnees-<date>.tar.gz
sudo docker compose start app
```

La sauvegarde automatique d'OVH (étape 1) garde en plus des copies du serveur entier, ailleurs
que sur le serveur : si le serveur est perdu, on le restaure depuis l'espace client OVH.
