# CV Builder Pro en une image : l'interface construite, le serveur, LaTeX et poppler.
#
#   docker compose up -d          puis http://localhost:8000
#
# Tes données vivent dans le volume /data : data/ (CV, bibliothèque…), local/
# (réglages, consommation) et .env (clés d'API). Elles survivent aux mises à jour.

# ─── L'interface ─────────────────────────────────────────────────────────────
FROM node:24-bookworm-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build -- --logLevel error

# ─── Le serveur ──────────────────────────────────────────────────────────────
FROM python:3.13-slim-trixie

# LaTeX avec ses recommandations : sans elles, les polices Latin Modern manquent.
RUN apt-get update \
    && apt-get install -y -q texlive-xetex texlive-latex-extra texlive-pictures \
        texlive-lang-french latexmk poppler-utils \
        tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* /usr/share/doc/* /usr/share/man/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/app backend/app
COPY demo demo
COPY fonts fonts
COPY prompts prompts
COPY --from=web /app/frontend/dist frontend/dist

RUN useradd --create-home --uid 1000 cvb && mkdir -p /data && chown cvb:cvb /data
USER cvb
VOLUME /data

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CVB_DATA=/data/data \
    CVB_LOCAL=/data/local \
    CVB_ENV=/data/.env

WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"]
