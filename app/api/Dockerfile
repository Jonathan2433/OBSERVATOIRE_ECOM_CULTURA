# API FastAPI — image légère (sans torch). Compatible linux/arm64 et amd64.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dépendances d'abord (cache de couche)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Code applicatif
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

EXPOSE 8000

# Applique les migrations puis démarre l'API.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
