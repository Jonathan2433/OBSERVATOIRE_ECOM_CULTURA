"""Génération du CSV enrichi mensuel.

Le fichier de sortie conserve TOUTES les colonnes d'origine du fichier source et
y ajoute les colonnes du modèle (cf. inference.predictor.OUTPUT_COLUMNS).

Encodage UTF-8 avec BOM (``utf-8-sig``) pour une ouverture directe dans Excel
français sans casser les accents.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ..inference.predictor import OUTPUT_COLUMNS

logger = logging.getLogger(__name__)

# Colonne technique renommée en sortie pour lisibilité.
_RENAME = {"__source__": "source"}


def export_enriched_csv(enriched: pd.DataFrame, output_path: str | Path) -> Path:
    """Écrit le DataFrame enrichi en CSV. Renvoie le chemin du fichier produit."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = enriched.rename(columns=_RENAME)

    # Contrôle : toutes les colonnes du modèle doivent être présentes.
    missing = [c for c in OUTPUT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes de sortie manquantes : {missing}")

    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logger.info("CSV enrichi écrit : %s (%d lignes, %d colonnes)",
                output_path, len(df), df.shape[1])
    return output_path
