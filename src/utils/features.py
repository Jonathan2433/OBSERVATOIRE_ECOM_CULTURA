"""Feature engineering textuel partagé entre entraînement et inférence.

``sentiment_input`` formate l'entrée du modèle de sentiment en injectant
(optionnellement) le score de satisfaction sous forme de PRÉFIXE textuel
normalisé. Ce signal auxiliaire est fortement corrélé au sentiment.

Choix : préfixe textuel plutôt que concaténation à l'embedding [CLS]. La
concaténation imposerait une tête custom, incompatible avec l'export ONNX
standard d'optimum (contrainte CPU du POC). Le préfixe exploite le même signal
tout en conservant une architecture HuggingFace standard.

IMPORTANT : cette fonction DOIT être appelée de manière identique à
l'entraînement (train_sentiment) et à l'inférence (predictor), sinon les
distributions divergent.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional


def sentiment_input(text: str, satisfaction: Optional[float], cfg: Dict[str, Any]) -> str:
    """Construit l'entrée du modèle de sentiment (préfixe satisfaction optionnel)."""
    text = "" if text is None else str(text)
    use_prefix = cfg.get("sentiment", {}).get("use_satisfaction_prefix", True)
    if not use_prefix:
        return text
    score = _valid_score(satisfaction)
    if score is None:
        return text
    return f"[SATISFACTION {score}/10] {text}"


def _valid_score(value: Any) -> Optional[int]:
    """Renvoie un score entier 1..10 valide, sinon None."""
    if value is None:
        return None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
        score = int(round(float(value)))
    except (ValueError, TypeError):
        return None
    if 1 <= score <= 10:
        return score
    return None
