"""Boucle de fine-tuning générique partagée par les modèles transformer.

Fournit ``fine_tune`` : entraîne un ``AutoModelForSequenceClassification`` avec
  - optimiseur AdamW + scheduler linéaire avec warmup ;
  - perte pondérée (BCEWithLogits + pos_weight en multi-label, CrossEntropy +
    class_weight en multi-classes) — calculée en externe pour garder le contrôle
    des pondérations de classes ;
  - early stopping sur le F1-macro de validation (patience configurable) ;
  - journalisation des métriques par epoch.

Conçue pour le CPU (POC) : pas de mixed precision, pas de gradient accumulation.
"""
from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def append_training_log(cfg: Dict[str, Any], task_name: str, history: List[Dict[str, float]]) -> None:
    """Ajoute/écrase l'historique d'un task dans data/processed/training_logs.json."""
    from ..utils.config import resolve_path

    path = resolve_path(cfg, cfg["paths"]["training_logs"])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    logs: Dict[str, Any] = {}
    if Path(path).is_file():
        try:
            with open(path, "r", encoding="utf-8") as fh:
                logs = json.load(fh)
        except (json.JSONDecodeError, OSError):
            logs = {}
    logs[task_name] = history
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(logs, fh, ensure_ascii=False, indent=2)


def _evaluate(model, loader, device, multilabel: bool, threshold: float) -> Dict[str, float]:
    """Évalue le modèle et renvoie F1-macro / précision / rappel macro + loss n/a."""
    import torch
    from sklearn.metrics import f1_score, precision_score, recall_score

    model.eval()
    all_logits: List[np.ndarray] = []
    all_labels: List[np.ndarray] = []
    with torch.no_grad():
        for batch in loader:
            labels = batch.pop("labels")
            batch = {k: v.to(device) for k, v in batch.items()}
            logits = model(**batch).logits.cpu().numpy()
            all_logits.append(logits)
            all_labels.append(labels.numpy())
    logits = np.concatenate(all_logits, axis=0)
    labels = np.concatenate(all_labels, axis=0)

    if multilabel:
        probs = 1.0 / (1.0 + np.exp(-logits))
        preds = (probs >= threshold).astype(int)
        y_true = labels.astype(int)
    else:
        preds = logits.argmax(axis=1)
        y_true = labels.astype(int)

    return {
        "f1_macro": float(f1_score(y_true, preds, average="macro", zero_division=0)),
        "f1_micro": float(f1_score(y_true, preds, average="micro", zero_division=0)),
        "precision_macro": float(precision_score(y_true, preds, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true, preds, average="macro", zero_division=0)),
    }


def fine_tune(
    model,
    train_loader,
    val_loader,
    cfg: Dict[str, Any],
    *,
    multilabel: bool,
    pos_weight: Optional[np.ndarray] = None,
    class_weight: Optional[np.ndarray] = None,
    threshold: float = 0.5,
    task_name: str = "model",
) -> Tuple[Any, List[Dict[str, float]]]:
    """Fine-tune le modèle. Renvoie (meilleur_modèle, historique_par_epoch)."""
    import torch
    from torch.optim import AdamW
    from transformers import get_linear_schedule_with_warmup

    from ..utils.config import resolve_device

    device = resolve_device(cfg)
    model = model.to(device)

    epochs = cfg["model"]["epochs"]
    lr = float(cfg["model"]["learning_rate"])
    weight_decay = float(cfg["model"]["weight_decay"])
    warmup_ratio = float(cfg["model"]["warmup_ratio"])
    patience = int(cfg["model"]["early_stopping_patience"])
    if cfg.get("smoke_test", {}).get("enabled"):
        epochs = cfg["smoke_test"].get("epochs", 1)

    # Perte pondérée (cf. gestion des classes rares).
    if multilabel:
        pw = torch.tensor(pos_weight, dtype=torch.float32, device=device) if pos_weight is not None else None
        loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=pw)
    else:
        cw = torch.tensor(class_weight, dtype=torch.float32, device=device) if class_weight is not None else None
        loss_fn = torch.nn.CrossEntropyLoss(weight=cw)

    optimizer = AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    total_steps = max(1, len(train_loader) * epochs)
    scheduler = get_linear_schedule_with_warmup(
        optimizer, num_warmup_steps=int(warmup_ratio * total_steps), num_training_steps=total_steps
    )

    history: List[Dict[str, float]] = []
    best_metric = -1.0
    best_state = copy.deepcopy(model.state_dict())
    epochs_no_improve = 0

    for epoch in range(1, epochs + 1):
        model.train()
        running_loss = 0.0
        for batch in train_loader:
            optimizer.zero_grad()
            labels = batch.pop("labels").to(device)
            batch = {k: v.to(device) for k, v in batch.items()}
            logits = model(**batch).logits
            if multilabel:
                loss = loss_fn(logits, labels.float())
            else:
                loss = loss_fn(logits, labels.long())
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            running_loss += loss.item()

        train_loss = running_loss / max(1, len(train_loader))
        metrics = _evaluate(model, val_loader, device, multilabel, threshold)
        metrics["epoch"] = epoch
        metrics["train_loss"] = train_loss
        history.append(metrics)
        logger.info(
            "[%s] epoch %d/%d | loss=%.4f | val F1-macro=%.4f (P=%.3f R=%.3f)",
            task_name, epoch, epochs, train_loss,
            metrics["f1_macro"], metrics["precision_macro"], metrics["recall_macro"],
        )

        if metrics["f1_macro"] > best_metric + 1e-4:
            best_metric = metrics["f1_macro"]
            best_state = copy.deepcopy(model.state_dict())
            epochs_no_improve = 0
        else:
            epochs_no_improve += 1
            if epochs_no_improve >= patience:
                logger.info("[%s] Early stopping (patience=%d) à l'epoch %d.", task_name, patience, epoch)
                break

    model.load_state_dict(best_state)
    logger.info("[%s] Meilleur F1-macro val = %.4f", task_name, best_metric)
    return model, history
