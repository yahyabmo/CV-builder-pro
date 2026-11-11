# Installer CV Builder Pro

CV Builder Pro s'installe sous **Windows 10 et 11**, dans WSL (le Linux intégré
à Windows), et sous **Linux** (Ubuntu, Debian). macOS n'est pas pris en charge.

Dans les deux cas, une commande installe tout et pose l'icône **CV Builder Pro**.
Au premier lancement, l'appli te fait choisir ton modèle d'IA, colle et vérifie
ta clé, puis contrôle LaTeX et les outils PDF.

## Windows

### La première fois : WSL

Si WSL n'est pas encore installé, dans PowerShell ouvert **en administrateur**
(clic droit sur PowerShell › Exécuter en tant qu'administrateur) :

```powershell
wsl --install -d Ubuntu
```

Redémarre le PC. Au redémarrage, Ubuntu s'ouvre et te demande un nom
d'utilisateur et un mot de passe : garde ce mot de passe, l'installation le
demandera.

### Installer

Dans PowerShell (pas besoin d'être administrateur) :

```powershell
wsl -d Ubuntu -- bash -lc "cd && git clone https://github.com/yahyabmo/CV-builder-pro.git && CV-builder-pro/install.sh"
```

Le script installe ce qui manque dans Ubuntu (LaTeX, environ 1 Go, les outils
PDF, Python, Node.js), prépare l'appli, puis pose :

- l'icône **CV Builder Pro** sur le bureau Windows et dans le menu Démarrer ;
- **Arrêter CV Builder Pro** dans le menu Démarrer.

Il ouvre ensuite l'appli dans ton navigateur.

### Démarrer, arrêter

- **Par l'icône** : l'appli démarre sans fenêtre et s'ouvre dans ton navigateur
  Windows. Un deuxième clic rouvre seulement le navigateur. Pour l'arrêter :
  **Arrêter CV Builder Pro** dans le menu Démarrer.
- **Par une commande**, dans PowerShell ; Ctrl+C l'arrête :

  ```powershell
  wsl -d Ubuntu -- bash -lc "cd && make -C CV-builder-pro start"
  ```

### Mettre à jour

```powershell
wsl -d Ubuntu -- bash -lc "cd && CV-builder-pro/install.sh"
```

L'appli et tes données vivent dans Ubuntu, dans `~/CV-builder-pro`. L'Explorateur
Windows y accède par `\\wsl.localhost\Ubuntu\home\<ton nom Ubuntu>\CV-builder-pro`.

## Linux

### Installer

```bash
git clone https://github.com/yahyabmo/CV-builder-pro.git && cd CV-builder-pro && ./install.sh
```

Le script :

1. installe ce qui manque avec `apt` : LaTeX (environ 1 Go), les outils PDF
   poppler, Python 3.12 ou plus récent (Python 3.13 par le dépôt deadsnakes sur
   Ubuntu 22.04), et Node.js (par nvm, dans ton dossier personnel) ;
2. prépare l'appli : environnement Python dans `.venv`, puis construction de
   l'interface ;
3. vérifie le tout avec `make doctor` ;
4. pose l'icône **CV Builder Pro** sur le bureau et dans le menu des applis ;
5. ouvre l'appli dans ton navigateur.

Il ne demande ton mot de passe (`sudo`) que pour installer des logiciels du
système. Il ne faut pas le lancer lui-même avec `sudo`.
`./install.sh --sans-ouvrir` fait tout, sauf ouvrir l'appli à la fin.

### Démarrer, arrêter

- **Par l'icône** : l'appli démarre en arrière-plan, sans fenêtre, puis s'ouvre
  dans le navigateur. Un deuxième clic rouvre seulement le navigateur. Pour
  l'arrêter : clic droit sur l'icône › **Arrêter CV Builder Pro**, ou `make stop`
  dans le dossier du projet. Si le bureau d'Ubuntu demande la permission au
  premier clic : clic droit, puis **Autoriser le lancement**.
- **Par une commande**, dans le dossier du projet ; Ctrl+C l'arrête :

  ```bash
  make start
  ```

### Mettre à jour

```bash
./install.sh
```

Il récupère la dernière version (`git pull`) et ne réinstalle que ce qui manque.

## Bon à savoir

- **Port déjà pris** : si un autre programme occupe le port 8000, l'icône prend
  le premier port libre suivant (8001, 8002…), le signale et le garde pour les
  fois suivantes. `python3 scripts/appli.py etat` donne l'adresse en cours.
  `make start` refuse un port pris : `PORT=8010 make start`.
- **Journal du serveur** lancé par l'icône : `local/serveur.log`.

| Commande (dans le dossier du projet) | Rôle |
|---|---|
| `make doctor` | ce qui manque sur la machine, avec la commande pour l'installer |
| `make stop` | arrêter l'appli lancée par l'icône |
| `make shortcut` | reposer l'icône (si elle a été supprimée ou le dossier déplacé) |
| `.venv/bin/python scripts/raccourci.py --retirer` | retirer l'icône |

## Autre façon : Docker

Pour qui a déjà [Docker Desktop](https://www.docker.com/products/docker-desktop/)
(Windows) ou Docker Engine (Linux), et Git. L'image contient tout, LaTeX compris ;
pas d'icône, l'appli se garde en favori.

```bash
git clone https://github.com/yahyabmo/CV-builder-pro.git
cd CV-builder-pro
docker compose up -d --build
```

La première construction prend quelques minutes. L'appli redémarre ensuite toute
seule avec Docker, sur <http://localhost:8000>.

| Commande | Rôle |
|---|---|
| `docker compose up -d` | démarrer l'appli |
| `docker compose down` | l'arrêter |
| `git pull && docker compose up -d --build` | passer à la dernière version |
| `CVB_PORT=8010 docker compose up -d` | l'appli sur <http://localhost:8010>, si le port 8000 est pris |

Tes CV, ta bibliothèque, tes réglages et ta clé d'API vivent dans le volume
Docker `cv-builder-pro_cv-builder-data`. Pour en garder une copie dans le
dossier courant :

```bash
docker run --rm -v cv-builder-pro_cv-builder-data:/data -v "$PWD":/copie alpine \
  tar czf /copie/cv-builder-sauvegarde.tgz -C /data .
```

L'appli n'a pas de mot de passe : `docker-compose.yml` ne l'ouvre que sur ta
machine (`127.0.0.1`). Garde ce réglage.

## À la main

Ce que fait `install.sh`, étape par étape, sous Linux ou dans le terminal Ubuntu
de WSL. Il faut Python 3.12 ou plus récent, Node.js 20.19 ou plus récent, LaTeX
(XeLaTeX et latexmk), les outils PDF poppler, Git et make. À tout moment,
`make doctor` liste ce qui manque et donne la commande exacte pour l'installer.

```bash
sudo apt install -y git make curl libatomic1 python3 python3-venv texlive-xetex \
  texlive-latex-extra texlive-pictures texlive-lang-french latexmk poppler-utils \
  tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng
```

Ubuntu 22.04 n'a que Python 3.10 : Python 3.13 vient alors du dépôt deadsnakes.

```bash
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt install -y python3.13 python3.13-venv
```

Node.js, par exemple avec nvm :

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
. "$HOME/.nvm/nvm.sh" && nvm install --lts
```

Puis :

```bash
git clone https://github.com/yahyabmo/CV-builder-pro.git
cd CV-builder-pro
make doctor
make install
make build
make shortcut   # facultatif : l'icône (bureau Windows et menu Démarrer sous WSL)
make start      # ou un clic sur l'icône
```

## Tes données

Elles restent dans le dossier du projet : `data/` (CV, bibliothèque), `local/`
(réglages, consommation, journal du serveur) et `.env` (clés d'API). Aucun de
ces dossiers n'est versionné, et `./install.sh` n'y touche pas.
