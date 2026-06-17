"""Entraînement des 3 détecteurs de signaux (rupture / churn / insatisfaction).

ARCHITECTURE (justification) : régression logistique scikit-learn sur des
embeddings CamemBERT GELÉS (mean pooling), une LogReg par signal.

Pourquoi pas un fine-tuning CamemBERT par signal ?
  - signal_rupture_client ne compte que ~0,4 % de positifs (29/7000). Un
    fine-tuning complet sur si peu de positifs sur-apprendrait massivement.
  - Une LogReg pondérée (class_weight='balanced') sur embeddings figés est
    robuste à ce déséquilibre extrême, rapide à entraîner, et son seuil de
    décision est ajustable pour PRIVILÉGIER LE RAPPEL (priorité métier : ne
    jamais rater une rupture client). On calibre d'ailleurs le seuil de rupture
    sur la validation pour viser recall >= 0,80.

Les 3 signaux PARTAGENT l'architecture (mêmes embeddings, même type de modèle)
mais sont entraînés SÉPARÉMENT (un classifieur binaire chacun).

Pour signal_insatisfaction_forte, le cahier des charges précise "note <= 3 ET
sentiment très négatif". On entraîne le modèle sur le label fourni ; la règle
déterministe (score de satisfaction) est combinée à l'inférence (predictor) en
booster haute-précision.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from ..modeling import EmbeddingExtractor
from ..modeling.architecture import CURRENT_POINTER
from ..utils import load_config, resolve_path, set_seed
from .prepare_dataset import ProcessedDataset

logger = logging.getLogger(__name__)

# Correspondance label historique -> nom court de signal + clé de seuil config.
SIGNALS = [
    ("signal_rupture_client", "rupture", "signal_rupture"),
    ("signal_churn", "churn", "signal_churn"),
    ("signal_insatisfaction_forte", "insatisfaction", "signal_insatisfaction"),
]


def _threshold_for_recall(y_true: np.ndarray, proba: np.ndarray, target_recall: float) -> float:
    """Seuil le plus haut atteignant le rappel cible (maximise la précision).

    Renvoie le plus grand seuil tel que recall(>=seuil) >= target_recall.
    """
    pos = proba[y_true == 1]
    if len(pos) == 0:
        return 0.5
    # Le seuil = quantile (1 - target_recall) des proba des positifs : on capture
    # au moins target_recall % des positifs.
    thr = float(np.quantile(np.sort(pos), max(0.0, 1.0 - target_recall)))
    # Borne pour éviter un seuil dégénéré.
    return float(np.clip(thr, 0.05, 0.95))


def _metrics(y_true: np.ndarray, proba: np.ndarray, threshold: float) -> Dict[str, float]:
    from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score

    preds = (proba >= threshold).astype(int)
    out = {
        "threshold": float(threshold),
        "precision": float(precision_score(y_true, preds, zero_division=0)),
        "recall": float(recall_score(y_true, preds, zero_division=0)),
        "f1": float(f1_score(y_true, preds, zero_division=0)),
        "n_positives": int(y_true.sum()),
    }
    try:
        if len(np.unique(y_true)) > 1:
            out["auc_roc"] = float(roc_auc_score(y_true, proba))
    except ValueError:
        pass
    return out


def train_signals(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Entraîne les 3 détecteurs binaires et sauvegarde modèles + métadonnées."""
    import joblib
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    set_seed(cfg["model"]["seed"])
    logger.info("=== Entraînement des détecteurs de signaux (3 binaires) ===")
    data = ProcessedDataset.load(cfg)
    train_df, val_df, test_df = data.split("train"), data.split("val"), data.split("test")

    # --- Embeddings CamemBERT gelés (une seule passe, réutilisée par signal) --
    extractor = EmbeddingExtractor(cfg)
    bs = cfg["model"]["batch_size_inference"]
    logger.info("Extraction des embeddings (train/val/test)...")
    X_train = extractor.embed(train_df["text_clean"].tolist(), batch_size=bs)
    X_val = extractor.embed(val_df["text_clean"].tolist(), batch_size=bs)
    X_test = extractor.embed(test_df["text_clean"].tolist(), batch_size=bs)

    # --- Dossier de sortie versionné ------------------------------------------
    base_dir = resolve_path(cfg, cfg["paths"]["model_signals"])
    base_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    version_dir = base_dir / ts
    version_dir.mkdir(parents=True, exist_ok=True)

    metadata: Dict[str, Any] = {
        "version": ts,
        "pooling": extractor.pooling,
        "embedding_dim": int(X_train.shape[1]) if X_train.size else 0,
        "signals": {},
    }
    sig_cfg = cfg.get("signals", {})

    for label_col, short, thr_key in SIGNALS:
        y_train = data.signal_targets(train_df, label_col)
        y_val = data.signal_targets(val_df, label_col)
        y_test = data.signal_targets(test_df, label_col)

        clf = Pipeline([
            ("scaler", StandardScaler()),
            ("logreg", LogisticRegression(
                class_weight=sig_cfg.get("class_weight", "balanced"),
                max_iter=sig_cfg.get("max_iter", 2000),
                C=1.0, random_state=cfg["model"]["seed"],
            )),
        ])
        clf.fit(X_train, y_train)

        proba_val = clf.predict_proba(X_val)[:, 1]
        proba_test = clf.predict_proba(X_test)[:, 1]

        threshold = float(cfg["thresholds"][thr_key])
        # Priorité au rappel pour la rupture : calibrage du seuil sur la val.
        if short == "rupture" and sig_cfg.get("rupture_recall_priority", True):
            calibrated = _threshold_for_recall(y_val, proba_val, target_recall=0.80)
            logger.info("Rupture : seuil calibré sur val pour recall>=0.80 = %.3f (défaut %.2f)",
                        calibrated, threshold)
            threshold = calibrated

        joblib.dump(clf, version_dir / f"{short}.joblib")
        metadata["signals"][short] = {
            "label_col": label_col,
            "threshold": threshold,
            "val": _metrics(y_val, proba_val, threshold),
            "test": _metrics(y_test, proba_test, threshold),
            "train_positives": int(y_train.sum()),
        }
        m = metadata["signals"][short]["test"]
        logger.info("[signal:%s] test P=%.3f R=%.3f F1=%.3f (seuil=%.2f, n+=%d)",
                    short, m["precision"], m["recall"], m["f1"], threshold, m["n_positives"])

    with open(version_dir / "signals_metadata.json", "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, ensure_ascii=False, indent=2)
    (base_dir / CURRENT_POINTER).write_text(ts, encoding="utf-8")
    logger.info("Détecteurs de signaux sauvegardés (version %s) dans %s", ts, version_dir)
    return metadata


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    train_signals(load_config())
