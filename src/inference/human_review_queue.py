"""File de revue humaine (human-in-the-loop).

Extrait les verbatims dont ``confidence_globale < seuil_revue`` (ou non
classifiables) et les exporte dans un CSV dédié, trié par confiance croissante
(les cas les plus incertains d'abord) pour faciliter la revue manuelle.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def extract_review_queue(enriched: pd.DataFrame) -> pd.DataFrame:
    """Sous-ensemble des verbatims nécessitant une revue humaine."""
    if "revue_humaine_requise" not in enriched.columns:
        raise ValueError("Le DataFrame ne contient pas 'revue_humaine_requise'.")
    queue = enriched[enriched["revue_humaine_requise"] == True].copy()  # noqa: E712
    if "confidence_globale" in queue.columns:
        queue = queue.sort_values("confidence_globale", ascending=True)
    return queue


def export_review_queue(enriched: pd.DataFrame, output_path: str | Path) -> int:
    """Écrit le CSV de revue humaine. Renvoie le nombre de verbatims exportés."""
    queue = extract_review_queue(enriched)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    queue.to_csv(output_path, index=False, encoding="utf-8-sig")
    logger.info("File de revue humaine : %d verbatims -> %s", len(queue), output_path)
    return len(queue)
