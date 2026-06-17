"""Fine-tuning du modèle de sentiment (3 classes : Négatif / Neutre / Positif).

Architecture : CamemBERT + tête de classification 3 classes (softmax, CE
pondérée). Le score de satisfaction (1-10) est injecté en préfixe textuel
(cf. utils.features.sentiment_input) — signal auxiliaire fortement corrélé au
sentiment, compatible avec l'export ONNX standard.

NB : le sentiment est appris au niveau du verbatim (theme1_sentiment). À
l'inférence, il est appliqué à chaque thème détecté ; pour les rares verbatims
bi-thèmes (0,4 %), un sentiment par span demanderait un jeu de données annoté au
niveau du span, hors périmètre POC.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from torch.utils.data import DataLoader

from ..modeling import build_sequence_classifier, base_model_path, load_tokenizer, save_versioned
from ..utils import load_config, resolve_path, set_seed, sentiment_input
from .dataset import EncodedDataset
from .prepare_dataset import ProcessedDataset
from .trainer import append_training_log, fine_tune

logger = logging.getLogger(__name__)


def _build_texts(df, cfg: Dict[str, Any]):
    """Construit les entrées (avec préfixe satisfaction) pour le modèle sentiment."""
    sat_col = "__satisfaction__"
    sats = df[sat_col] if sat_col in df.columns else [None] * len(df)
    return [
        sentiment_input(t, s, cfg)
        for t, s in zip(df["text_clean"].tolist(), list(sats))
    ]


def train_sentiment(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Entraîne le modèle de sentiment 3 classes et renvoie un résumé."""
    set_seed(cfg["model"]["seed"])
    logger.info("=== Entraînement modèle de sentiment (3 classes) ===")
    data = ProcessedDataset.load(cfg)
    tokenizer = load_tokenizer(base_model_path(cfg))
    max_length = cfg["model"]["max_length"]
    if cfg.get("smoke_test", {}).get("enabled"):
        max_length = cfg["smoke_test"]["max_length"]

    train_df, val_df = data.split("train"), data.split("val")
    train_ds = EncodedDataset(
        _build_texts(train_df, cfg), data.sentiment_targets(train_df),
        tokenizer, max_length, multilabel=False,
    )
    val_ds = EncodedDataset(
        _build_texts(val_df, cfg), data.sentiment_targets(val_df),
        tokenizer, max_length, multilabel=False,
    )

    model = build_sequence_classifier(
        base_model_path(cfg), num_labels=len(data.sentiment_labels), multilabel=False
    )
    model, history = fine_tune(
        model,
        DataLoader(train_ds, batch_size=cfg["model"]["batch_size_train"], shuffle=True,
                   num_workers=cfg["model"].get("num_workers", 0)),
        DataLoader(val_ds, batch_size=cfg["model"]["batch_size_inference"], shuffle=False,
                   num_workers=cfg["model"].get("num_workers", 0)),
        cfg, multilabel=False, class_weight=data.sentiment_class_weight, task_name="sentiment",
    )

    card = {
        "task": "sentiment",
        "type": "multi_class",
        "labels": data.sentiment_labels,
        "use_satisfaction_prefix": cfg["sentiment"]["use_satisfaction_prefix"],
        "base_model": cfg["model"]["base_model"],
        "best_val_f1_macro": max(h["f1_macro"] for h in history) if history else None,
    }
    version_dir = save_versioned(
        model, tokenizer, resolve_path(cfg, cfg["paths"]["model_sentiment"]), card
    )
    append_training_log(cfg, "sentiment", history)
    return {"version_dir": str(version_dir), "history": history}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    train_sentiment(load_config())
