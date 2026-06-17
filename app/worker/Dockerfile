# Worker ML (RQ + CamemBERT). Image lourde. Contexte de build = racine du projet.
# Compatible linux/arm64 (Apple Silicon) et amd64 — wheels torch/onnxruntime/spaCy.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TAXONOMY_PATH=/app/taxonomy.json

WORKDIR /app

# 1) Dépendances ML (couche cache) — requirements.txt racine (versions épinglées).
COPY requirements.txt ./requirements-ml.txt
RUN pip install --no-cache-dir -r requirements-ml.txt

# 2) Dépendances worker (file de jobs + accès DB)
COPY app/worker/requirements.txt ./requirements-worker.txt
RUN pip install --no-cache-dir -r requirements-worker.txt

# 3) Modèle spaCy FR embarqué (anonymisation) -> fonctionne hors ligne au runtime
RUN python -m spacy download fr_core_news_sm

# 4) Code : moteur ML réutilisé + package partagé + config + taxonomie + worker
COPY src ./src
COPY app/common ./common
COPY config ./config
COPY data/raw/taxonomy_cultura_poc.json ./taxonomy.json
COPY app/worker ./worker

# Démarre le worker RQ (consomme la file 'default').
CMD ["python", "-m", "worker.worker_main"]
