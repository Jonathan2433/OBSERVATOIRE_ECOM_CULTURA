"""Fine-tuning de la classification thématique hiérarchique (niv.1 + niv.2).

==============================================================================
 JUSTIFICATION DE L'ARCHITECTURE
==============================================================================
Le cahier des charges propose deux pistes :
  (1) niv.1 multi-label + 20 classifieurs niv.2 conditionnés (un par niv.1) ;
  (2) une tête multi-têtes à sortie hiérarchique.

Nous retenons une 3e variante, plus performante ET plus simple à maintenir sur
ce volume de données, qui reste strictement contrainte par la taxonomie :

  * MODÈLE niv.1  : CamemBERT fine-tuné en MULTI-LABEL (20 sigmoïdes, BCE).
                    Gère nativement les verbatims bi-thèmes (max 2 retenus).
  * MODÈLE niv.2  : CamemBERT fine-tuné en MULTI-CLASSES sur les 67 sous-thèmes
                    (softmax, CE). À l'inférence, on MASQUE les logits niv.2
                    pour ne conserver que les enfants du niv.1 prédit, puis on
                    prend l'argmax -> la hiérarchie est TOUJOURS respectée
                    (aucune combinaison hors-référentiel possible).

Pourquoi pas 20 classifieurs niv.2 séparés ?
  - Avec ~100 exemples/sous-thème, un encodeur partagé unique apprend de
    meilleures représentations qu'une vingtaine de petites têtes affamées de
    données.
  - Maintenance : ajouter un sous-thème = ajouter une classe + réentraîner UN
    modèle (cf. README "Ajouter un nouveau thème"), sans recâbler 20 têtes.
  - Export ONNX/int8 trivial (têtes HuggingFace standard), exigé pour le CPU.

La contrainte hiérarchique est donc imposée à l'INFÉRENCE (masquage), pas à
l'entraînement — c'est ce qui garantit zéro sortie hors-taxonomie.
==============================================================================
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from torch.utils.data import DataLoader

from ..modeling import build_sequence_classifier, base_model_path, load_tokenizer, save_versioned
from ..utils import load_config, resolve_path, set_seed, Taxonomy
from .dataset import EncodedDataset
from .prepare_dataset import ProcessedDataset
from .trainer import append_training_log, fine_tune

logger = logging.getLogger(__name__)


def _loader(ds: EncodedDataset, batch_size: int, shuffle: bool, cfg: Dict[str, Any]) -> DataLoader:
    return DataLoader(
        ds, batch_size=batch_size, shuffle=shuffle,
        num_workers=cfg["model"].get("num_workers", 0),
    )


def train_niv1(data: ProcessedDataset, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Entraîne le classifieur niv.1 multi-label (20 thèmes)."""
    logger.info("=== Entraînement classifieur niv.1 (multi-label, 20 thèmes) ===")
    tokenizer = load_tokenizer(base_model_path(cfg))
    max_length = cfg["model"]["max_length"]
    if cfg.get("smoke_test", {}).get("enabled"):
        max_length = cfg["smoke_test"]["max_length"]

    train_df, val_df = data.split("train"), data.split("val")
    train_ds = EncodedDataset(
        train_df["text_clean"].tolist(), data.niv1_matrix(train_df),
        tokenizer, max_length, multilabel=True,
    )
    val_ds = EncodedDataset(
        val_df["text_clean"].tolist(), data.niv1_matrix(val_df),
        tokenizer, max_length, multilabel=True,
    )

    model = build_sequence_classifier(base_model_path(cfg), num_labels=len(data.niv1_labels), multilabel=True)
    model, history = fine_tune(
        model,
        _loader(train_ds, cfg["model"]["batch_size_train"], True, cfg),
        _loader(val_ds, cfg["model"]["batch_size_inference"], False, cfg),
        cfg, multilabel=True, pos_weight=data.niv1_pos_weight,
        threshold=cfg["thresholds"]["classification_niv1"], task_name="niv1",
    )

    card = {
        "task": "classification_niv1",
        "type": "multi_label",
        "labels": data.niv1_labels,
        "threshold": cfg["thresholds"]["classification_niv1"],
        "base_model": cfg["model"]["base_model"],
        "best_val_f1_macro": max(h["f1_macro"] for h in history) if history else None,
    }
    version_dir = save_versioned(
        model, tokenizer, resolve_path(cfg, cfg["paths"]["model_classifier_niv1"]), card
    )
    append_training_log(cfg, "niv1", history)
    return {"version_dir": str(version_dir), "history": history}


def train_niv2(data: ProcessedDataset, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Entraîne le classifieur niv.2 multi-classes (67 sous-thèmes)."""
    logger.info("=== Entraînement classifieur niv.2 (multi-classes, 67 sous-thèmes) ===")
    tokenizer = load_tokenizer(base_model_path(cfg))
    max_length = cfg["model"]["max_length"]
    if cfg.get("smoke_test", {}).get("enabled"):
        max_length = cfg["smoke_test"]["max_length"]

    train_df, val_df = data.split("train"), data.split("val")
    tr_texts, tr_idx = data.niv2_examples(train_df)   # explosion par sous-thème
    va_texts, va_idx = data.niv2_examples(val_df)
    train_ds = EncodedDataset(tr_texts, tr_idx, tokenizer, max_length, multilabel=False)
    val_ds = EncodedDataset(va_texts, va_idx, tokenizer, max_length, multilabel=False)

    model = build_sequence_classifier(base_model_path(cfg), num_labels=len(data.niv2_labels), multilabel=False)
    model, history = fine_tune(
        model,
        _loader(train_ds, cfg["model"]["batch_size_train"], True, cfg),
        _loader(val_ds, cfg["model"]["batch_size_inference"], False, cfg),
        cfg, multilabel=False, class_weight=data.niv2_class_weight,
        task_name="niv2",
    )

    card = {
        "task": "classification_niv2",
        "type": "multi_class",
        "labels": data.niv2_labels,
        "base_model": cfg["model"]["base_model"],
        "best_val_f1_macro": max(h["f1_macro"] for h in history) if history else None,
    }
    version_dir = save_versioned(
        model, tokenizer, resolve_path(cfg, cfg["paths"]["model_classifier_niv2"]), card
    )
    append_training_log(cfg, "niv2", history)
    return {"version_dir": str(version_dir), "history": history}


def train_classifier(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Entraîne les deux niveaux de classification et renvoie un résumé."""
    set_seed(cfg["model"]["seed"])
    # Vérifie que la taxonomie est cohérente avec les encodeurs sauvegardés.
    Taxonomy.from_json(resolve_path(cfg, cfg["paths"]["taxonomy"]))
    data = ProcessedDataset.load(cfg)
    res1 = train_niv1(data, cfg)
    res2 = train_niv2(data, cfg)
    return {"niv1": res1, "niv2": res2}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    train_classifier(load_config())
