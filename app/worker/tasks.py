"""Tâches exécutées par le worker.

L0 : une tâche ``ping`` triviale pour prouver le bout-en-bout (API -> Redis ->
worker). Les tâches ML (traitement d'un lot de verbatims, réutilisant
``src.inference.batch_processor``) seront ajoutées au lot L2.
"""
from __future__ import annotations

import os
import platform


def ping() -> dict:
    """Tâche de diagnostic : confirme que le worker exécute bien les jobs."""
    return {
        "pong": True,
        "python": platform.python_version(),
        "arch": platform.machine(),
        "models_dir": os.environ.get("MODELS_DIR", "/data/models"),
    }
