"""Construction de la configuration du moteur ML côté worker.

Charge la config.yaml du POC (seuils, nettoyage, anonymisation, sentiment,
signaux) puis réécrit les CHEMINS en absolu vers les volumes du conteneur
(/data/...), au lieu des chemins relatifs du POC.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from src.utils import load_config


def build_worker_cfg() -> Dict[str, Any]:
    cfg = load_config(os.environ.get("CONFIG_PATH") or None)
    models = os.environ.get("MODELS_DIR", "/data/models")
    processed = os.environ.get("PROCESSED_DIR", "/data/processed")

    cfg["paths"]["models"] = models
    cfg["paths"]["model_classifier_niv1"] = f"{models}/classifier_niv1"
    cfg["paths"]["model_classifier_niv2"] = f"{models}/classifier_niv2"
    cfg["paths"]["model_sentiment"] = f"{models}/sentiment"
    cfg["paths"]["model_signals"] = f"{models}/signals"
    cfg["paths"]["taxonomy"] = os.environ.get("TAXONOMY_PATH", "/app/taxonomy.json")
    cfg["paths"]["eval_report"] = f"{processed}/eval_report.json"
    cfg["model"]["local_model_dir"] = os.environ.get("CAMEMBERT_DIR", f"{models}/camembert-base")

    # --- Moteur Ollama (V4) : surcharge env du bloc ollama de config.yaml -------
    oll = cfg.setdefault("ollama", {})
    enabled_env = os.environ.get("OLLAMA_ENABLED")
    if enabled_env is not None:
        oll["enabled"] = enabled_env.strip().lower() in ("1", "true", "yes", "on")
    oll["base_url"] = os.environ.get("OLLAMA_BASE_URL", oll.get("base_url", "http://host.docker.internal:11434"))
    oll["model"] = os.environ.get("OLLAMA_MODEL", oll.get("model", "qwen2.5:7b"))
    return cfg
