# CV Builder Pro — commandes du projet. Voir README.md.

VENV := .venv
PY := $(CURDIR)/$(VENV)/bin/python
# Python 3.12 ou plus récent, celui du système d'abord (jamais celui d'un autre
# environnement virtuel), sinon le premier trouvé. install.sh le choisit lui-même.
PYTHON ?= $(firstword $(wildcard /usr/bin/python3.13 /usr/bin/python3.12) \
  $(shell command -v python3.13 || command -v python3.12 || command -v python3))
# Node par nvm s'il est là, sinon celui du système.
NVM := export NVM_DIR="$$HOME/.nvm"; [ -s "$$NVM_DIR/nvm.sh" ] && . "$$NVM_DIR/nvm.sh";

.PHONY: install build doctor start stop shortcut dev demo test e2e captures lint

install:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q --upgrade pip
	$(VENV)/bin/pip install -q -r backend/requirements-dev.txt
	$(NVM) cd frontend && npm install --no-audit --no-fund

# L'interface construite (frontend/dist), servie par le serveur sur le port 8000.
build:
	@$(NVM) cd frontend && npm run build --silent -- --logLevel error

# Ce qui manque sur cette machine, avec la commande exacte pour chaque manque.
doctor:
	@$(NVM) $(PYTHON) scripts/doctor.py

# L'appli sur une seule adresse, http://localhost:8000 (PORT=8010 make start pour un
# autre port), ouverte dans le navigateur. L'interface est construite une fois
# (frontend/dist), puis refaite si son code change. Ctrl+C l'arrête.
PORT ?= 8000
start:
	@$(NVM) cd frontend && if [ ! -f dist/index.html ] || [ -n "$$(find src index.html package.json -newer dist/index.html -print -quit)" ]; then echo "Construction de l'interface…"; npm run build --silent -- --logLevel error; fi
	@$(PY) -c "import socket, sys; sys.exit(socket.socket().connect_ex(('127.0.0.1', $(PORT))) == 0)" || { echo "Le port $(PORT) est déjà pris (l'appli du raccourci : make stop ; sinon un autre programme). Autre port : PORT=8010 make start"; exit 1; }
	@(curl -s -o /dev/null --retry 30 --retry-connrefused --retry-delay 1 http://127.0.0.1:$(PORT)/api/health && $(PY) scripts/appli.py navigateur $(PORT) >/dev/null 2>&1) &
	@echo "CV Builder Pro : http://localhost:$(PORT) (Ctrl+C pour arrêter)"
	@cd backend && $(PY) -m uvicorn app.main:app --port $(PORT) --log-level warning

# Arrête l'appli lancée par le raccourci du bureau (scripts/appli.py).
stop:
	@$(PY) scripts/appli.py arreter

# Pose (ou refait) le raccourci du bureau et du menu des applis (sous WSL : bureau Windows
# et menu Démarrer) ; install.sh le fait déjà.
shortcut:
	@$(PY) scripts/raccourci.py

# Pour développer : serveur (localhost:8000) et interface Vite (http://localhost:5173),
# rechargés à chaque modification ; Ctrl+C arrête les deux.
dev:
	@trap 'kill 0' INT TERM EXIT; \
	(cd backend && $(PY) -m uvicorn app.main:app --reload --port 8000) & \
	($(NVM) cd frontend && npm run dev -- --host 127.0.0.1) & \
	wait

# Régénère le CV fictif : build/demo/cv.pdf, et demo/main.tex suivi par Git.
demo:
	cd backend && $(PY) -m app.tools.make_demo

test:
	cd backend && $(PY) -m pytest -q

# Parcours de l'interface dans Chrome sans affichage, sur un serveur d'essai à part
# (ports 8001 et 5174) et une copie jetable du CV fictif : éditeur, Style, Mes CV,
# Bibliothèque, ciblage, lettre, LaTeX et ATS. Tes données ne sont jamais touchées.
e2e:
	$(NVM) frontend/scripts/run-e2e.sh

# Les captures du README (docs/captures/), en mode démo sur le CV fictif.
captures:
	$(NVM) frontend/scripts/run-captures.sh

lint:
	$(VENV)/bin/ruff check backend
	$(VENV)/bin/ruff format --check backend
	$(VENV)/bin/ruff check --config backend/pyproject.toml scripts
	$(VENV)/bin/ruff format --config backend/pyproject.toml --check scripts
	$(NVM) cd frontend && npx tsc -b && npx oxlint src
