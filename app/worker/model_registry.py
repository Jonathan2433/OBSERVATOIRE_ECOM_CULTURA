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
from common.models import (
    MODEL_KIND_CLAUDE, MODEL_KIND_LMSTUDIO, MODEL_KIND_REAL, MODEL_KIND_STUB, ModelVersion,
)

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


def _detect_lmstudio(cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Sonde le moteur LM Studio (V4). None si le moteur est désactivé en config.

    Si activé, renvoie toujours une entrée (pour que l'admin la voie) avec un drapeau
    ``available`` dynamique : vrai uniquement si LM Studio répond ET que le modèle est
    chargé. Le « test de connexion » côté UI = relancer cette synchro (Re-scanner).
    """
    lms = cfg.get("lmstudio", {}) or {}
    if not lms.get("enabled"):
        return None

    model = lms.get("model", "local-model")
    base_url = lms.get("base_url", "http://host.docker.internal:1234/v1")
    label = f"lmstudio:{model}"
    reachable, present = False, False
    try:
        from .lmstudio_predictor import list_llm_models, model_is_installed

        installed = list_llm_models(base_url, timeout_s=5)  # ping court (test de connexion)
        reachable = True
        present = model_is_installed(model, installed)
    except Exception as exc:  # LMStudioError ou import : injoignable
        logger.info("LM Studio non disponible (%s) : %s", base_url, exc)

    return {
        "label": label,
        "available": bool(reachable and present),
        "path": f"{model} @ {base_url}",
        "metrics": {"reachable": reachable, "model_present": present, "model": model},
    }


def _detect_claude(cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Décrit le moteur Claude (V5). None si désactivé en config.

    **Comparaison/test uniquement** : l'entrée n'est jamais auto-activée et son
    activation est refusée côté serveur. ``available`` = vrai ssi une clé
    ``ANTHROPIC_API_KEY`` est présente — détection **offline** (aucun ping réseau :
    on ne contacte Anthropic que lors d'un test/comparaison explicite). La présence
    de la clé est transmise par ``config_worker`` via ``api_key_present`` (le secret
    lui-même n'entre jamais dans la config).
    """
    cl = cfg.get("claude", {}) or {}
    if not cl.get("enabled"):
        return None

    model = cl.get("model", "claude-opus-4-8")
    base_url = cl.get("base_url", "https://api.anthropic.com")
    key_present = bool(cl.get("api_key_present"))
    return {
        "label": f"claude:{model}",
        "available": key_present,
        "path": f"{model} @ {base_url}",
        "metrics": {"api_key_present": key_present, "model": model, "comparison_only": True},
    }


def sync_registry(cfg: Dict[str, Any]) -> None:
    """Met à jour le registre : stub + modèle réel + LM Studio (si activé) + Claude (si activé)."""
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

        # --- Moteur LM Studio (V4) : enregistré uniquement si activé en config --
        lmstudio = _detect_lmstudio(cfg)
        if lmstudio:
            existing = db.query(ModelVersion).filter_by(label=lmstudio["label"]).one_or_none()
            if existing is None:
                db.add(ModelVersion(
                    kind=MODEL_KIND_LMSTUDIO, label=lmstudio["label"], path=lmstudio["path"],
                    metrics=lmstudio["metrics"], available=lmstudio["available"],
                ))
            else:
                existing.available = lmstudio["available"]
                existing.path = lmstudio["path"]
                existing.metrics = lmstudio["metrics"]
            logger.info("Moteur LM Studio %s : disponible=%s", lmstudio["label"], lmstudio["available"])
        else:
            # Moteur désactivé : neutraliser toute entrée LM Studio résiduelle.
            for row in db.query(ModelVersion).filter_by(kind=MODEL_KIND_LMSTUDIO).all():
                row.available = False

        # --- Moteur Claude (V5) : comparaison/test uniquement, JAMAIS auto-activé --
        claude = _detect_claude(cfg)
        if claude:
            existing = db.query(ModelVersion).filter_by(label=claude["label"]).one_or_none()
            if existing is None:
                db.add(ModelVersion(
                    kind=MODEL_KIND_CLAUDE, label=claude["label"], path=claude["path"],
                    metrics=claude["metrics"], available=claude["available"],
                ))
            else:
                existing.available = claude["available"]
                existing.path = claude["path"]
                existing.metrics = claude["metrics"]
            logger.info("Moteur Claude %s : disponible=%s (comparaison uniquement)",
                        claude["label"], claude["available"])
        else:
            # Moteur désactivé : neutraliser toute entrée Claude résiduelle.
            for row in db.query(ModelVersion).filter_by(kind=MODEL_KIND_CLAUDE).all():
                row.available = False

        # Garantir au moins un modèle actif (jamais Claude : non activable).
        if db.query(ModelVersion).filter_by(is_active=True).count() == 0:
            stub.is_active = True
        db.commit()


def get_active(db) -> Optional[ModelVersion]:
    """Modèle actif (repli sur le stub si l'actif est indisponible)."""
    active = db.query(ModelVersion).filter_by(is_active=True, available=True).first()
    if active:
        return active
    return db.query(ModelVersion).filter_by(label=STUB_LABEL).first()
