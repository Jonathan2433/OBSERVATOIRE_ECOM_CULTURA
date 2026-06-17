# API FastAPI — image légère (sans torch). Contexte de build = ./app
# (pour embarquer le package partagé `common`). Compatible arm64/amd64.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# Dépendances d'abord (cache de couche)
COPY api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Code : package partagé + API
COPY common ./common
COPY api/alembic.ini ./
COPY api/migrations ./migrations
COPY api/app ./app

EXPOSE 8000

# Applique les migrations puis démarre l'API.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
