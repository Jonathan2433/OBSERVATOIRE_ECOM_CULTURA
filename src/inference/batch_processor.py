"""Traitement par lots des verbatims (pipeline mensuel de production).

Enchaîne : Anonymisation -> Nettoyage -> Inférence par lots, avec :
  - journalisation du nombre d'entités PII masquées ;
  - comptage des verbatims filtrés (trop courts / vides) -> routés en revue ;
  - barre de progression tqdm ;
  - gestion des erreurs PAR verbatim (un échec n'interrompt pas le lot) ;
  - rapport final (n traités, n en revue, durée, distribution des thèmes).

Renvoie le DataFrame ENRICHI (colonnes d'origine + colonnes du modèle) et un
dict de rapport.
"""
from __future__ import annotations

import logging
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..preprocessing.loader import COL_SATISFACTION, COL_TEXT
from .predictor import OUTPUT_COLUMNS, VerbatimPredictor, _empty_result

logger = logging.getLogger(__name__)


def _progress(iterable, total: int, desc: str):
    """tqdm si disponible, sinon itérateur nu (robuste sans dépendance)."""
    try:
        from tqdm import tqdm

        return tqdm(iterable, total=total, desc=desc, unit="verb.")
    except ImportError:  # pragma: no cover
        return iterable


def process_dataframe(
    df: pd.DataFrame,
    predictor: VerbatimPredictor,
    cfg: Dict[str, Any],
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Anonymise, nettoie et classe tous les verbatims d'un DataFrame chargé.

    ``df`` doit contenir les colonnes techniques ``__text_raw__`` et
    ``__satisfaction__`` (produites par les loaders).
    """
    start = time.time()
    n = len(df)
    texts = df[COL_TEXT].tolist() if COL_TEXT in df.columns else [""] * n
    sats = df[COL_SATISFACTION].tolist() if COL_SATISFACTION in df.columns else [None] * n

    # --- 1. Anonymisation + nettoyage (par verbatim, tolérant aux erreurs) ----
    pii_counts: Counter = Counter()
    cleaned: List[str] = []
    n_errors = 0
    n_filtered = 0
    for raw in _progress(texts, n, "Anonymisation+nettoyage"):
        try:
            masked, counts = predictor.anonymizer.anonymize(raw)
            pii_counts.update(counts)
            text_clean = predictor.cleaner.clean(masked)
            if predictor.cleaner.is_empty(text_clean) or predictor.cleaner.is_too_short(text_clean):
                n_filtered += 1
            cleaned.append(text_clean)
        except Exception as exc:  # un verbatim défaillant ne stoppe pas le lot
            logger.warning("Erreur de prétraitement sur un verbatim (%s) -> ignoré.", exc)
            cleaned.append("")
            n_errors += 1
    logger.info("PII masquées : %s", dict(pii_counts))
    if n_filtered:
        logger.info("%d verbatims trop courts/vides -> revue humaine.", n_filtered)

    # --- 2. Inférence par lots -------------------------------------------------
    logger.info("Inférence sur %d verbatims (batch=%d)...", n, predictor.batch_size)
    try:
        preds = predictor.predict_cleaned_batch(cleaned, sats)
    except Exception as exc:
        logger.error("Échec de l'inférence par lots (%s) ; repli verbatim par verbatim.", exc)
        preds = _predict_one_by_one(cleaned, sats, predictor)

    # --- 3. Construction du DataFrame enrichi ---------------------------------
    pred_df = pd.DataFrame(preds, columns=OUTPUT_COLUMNS)
    pred_df.index = df.index
    enriched = pd.concat([df, pred_df], axis=1)
    # On retire les colonnes techniques internes du rendu final.
    enriched = enriched.drop(columns=[c for c in (COL_TEXT, COL_SATISFACTION) if c in enriched.columns])

    # --- 4. Rapport ------------------------------------------------------------
    elapsed = time.time() - start
    theme_counts = pred_df["theme1_niv1"].replace("", pd.NA).dropna().value_counts()
    report = {
        "n_total": n,
        "n_review": int(pred_df["revue_humaine_requise"].sum()),
        "review_rate": float(pred_df["revue_humaine_requise"].mean()) if n else 0.0,
        "n_filtered": n_filtered,
        "n_errors": n_errors,
        "pii_masked": dict(pii_counts),
        "elapsed_seconds": elapsed,
        "seconds_per_verbatim": elapsed / n if n else 0.0,
        "top_themes": theme_counts.head(5).to_dict(),
        "theme_distribution": theme_counts.to_dict(),
        "signals": {
            "rupture": int(pred_df["signal_rupture_client"].sum()),
            "churn": int(pred_df["signal_churn"].sum()),
            "insatisfaction_forte": int(pred_df["signal_insatisfaction_forte"].sum()),
        },
    }
    return enriched, report


def _predict_one_by_one(cleaned, sats, predictor) -> List[Dict[str, Any]]:
    """Repli : inférence verbatim par verbatim (isole les échecs individuels)."""
    out = []
    for c, s in zip(_progress(cleaned, len(cleaned), "Inférence (repli)"), sats):
        try:
            out.append(predictor.predict_cleaned_batch([c], [s])[0])
        except Exception as exc:
            logger.warning("Échec d'inférence sur un verbatim (%s) -> revue humaine.", exc)
            out.append(_empty_result(c))
    return out
