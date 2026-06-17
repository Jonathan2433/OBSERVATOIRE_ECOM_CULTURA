"""Registre des modèles : découverte (stub + réel) et synchronisation en base.

- Le **stub** (heuristique mots-clés) est toujours disponible.
- Le modèle **réel** est détecté si les artefacts CamemBERT sont présents dans
  le volume monté (/data/models). Ses métriques sont lues depuis eval_report.json.

La synchronisation est exécutée par le worker (qui a accès au volume + au moteur
`src`). L'API ne fait que lire/activer les entrées en base.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from common.db import SessionLocal
from common.models import MODEL_KIND_REAL, MODEL_KIND_STUB, ModelVersion

logger = logging.getLogger("worker.registry")

STUB_LABEL = "stub-heuristique"


def _summary_metrics(report: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if isinstance(report.get("niv1"), dict):
        out["f1_macro_niv1"] = report["niv1"].get("f1_macro")
    if isinstance(report.get("niv2"), dict):
        out["f1_macro_niv2"] = report["niv2"].get("f1_macro")
    if isinstance(report.get("sentiment"), dict):
        out["accuracy_sentiment"] = report["sentiment"].get("accuracy")
    sig = report.get("signals", {})
    if isinstance(sig, dict) and isinstance(sig.get("rupture"), dict):
        out["recall_rupture"] = sig["rupture"].get("recall")
    return out


def _detect_real(cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Détecte un modèle CamemBERT complet dans le volume. None si absent/incomplet."""
    from src.modeling.architecture import resolve_model_dir
    from src.utils import resolve_path

    needed = ["model_classifier_niv1", "model_classifier_niv2", "model_sentiment", "model_signals"]
    dirs = {}
    for key in needed:
        d = Path(resolve_model_dir(resolve_path(cfg, cfg["paths"][key])))
        if not (d.is_dir() and any(d.iterdir())):
            return None
        dirs[key] = d

    label = f"camembert-{dirs['model_classifier_niv1'].name}"
    metrics = None
    eval_path = Path(resolve_path(cfg, cfg["paths"]["eval_report"]))
    if eval_path.is_file():
        try:
            with open(eval_path, "r", encoding="utf-8") as fh:
                metrics = _summary_metrics(json.load(fh))
        except Exception:  # pragma: no cover
            metrics = None
    return {"label": label, "path": str(resolve_path(cfg, cfg["paths"]["models"])), "metrics": metrics}


def sync_registry(cfg: Dict[str, Any]) -> None:
    """Met à jour le registre en base : stub + modèle réel détecté."""
    with SessionLocal() as db:
        stub = db.query(ModelVersion).filter_by(label=STUB_LABEL).one_or_none()
        if stub is None:
            stub = ModelVersion(kind=MODEL_KIND_STUB, label=STUB_LABEL, available=True)
            db.add(stub)
            db.flush()
        else:
            stub.available = True

        try:
            real = _detect_real(cfg)
        except Exception as exc:  # pragma: no cover
            logger.warning("Détection du modèle réel impossible : %s", exc)
            real = None

        if real:
            existing = db.query(ModelVersion).filter_by(label=real["label"]).one_or_none()
            if existing is None:
                db.add(ModelVersion(
                    kind=MODEL_KIND_REAL, label=real["label"], path=real["path"],
                    metrics=real["metrics"], available=True,
                ))
            else:
                existing.available = True
                existing.path = real["path"]
                existing.metrics = real["metrics"]
            logger.info("Modèle réel détecté : %s", real["label"])
        else:
            logger.info("Aucun modèle CamemBERT détecté -> mode stub.")

        # Garantir au moins un modèle actif.
        if db.query(ModelVersion).filter_by(is_active=True).count() == 0:
            stub.is_active = True
        db.commit()


def get_active(db) -> Optional[ModelVersion]:
    """Modèle actif (repli sur le stub si l'actif est indisponible)."""
    active = db.query(ModelVersion).filter_by(is_active=True, available=True).first()
    if active:
        return active
    return db.query(ModelVersion).filter_by(label=STUB_LABEL).first()
