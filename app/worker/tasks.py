"""Tâches exécutées par le worker RQ.

- ``process_batch_job`` : traite un lot Excel (anonymisation -> nettoyage ->
  inférence) et persiste les résultats avec progression incrémentale.
- ``sync_registry_job`` : (re)synchronise le registre des modèles.
- ``ping`` : diagnostic.
"""
from __future__ import annotations

import logging
import math
import os
import platform
from collections import Counter
from datetime import datetime, timezone

from common.db import SessionLocal
from common.models import Batch, Result

from .classifiers import get_predictor
from .config_worker import build_worker_cfg
from .model_registry import get_active, sync_registry

logger = logging.getLogger("worker.tasks")

PROGRESS_CHUNK = 250  # nb de verbatims entre deux mises à jour de progression


def ping() -> dict:
    return {"pong": True, "python": platform.python_version(), "arch": platform.machine(),
            "models_dir": os.environ.get("MODELS_DIR", "/data/models")}


def sync_registry_job() -> dict:
    cfg = build_worker_cfg()
    sync_registry(cfg)
    return {"status": "synced"}


def purge_old_data_job() -> dict:
    """Purge RGPD des lots au-delà de la rétention (lue dans app_config)."""
    from common.models import AppConfig
    from common.retention import purge_old_batches

    with SessionLocal() as db:
        cfg = db.get(AppConfig, "retention_months")
        months = int(float(cfg.value)) if cfg else 13
        return purge_old_batches(db, months, uploads_dir=os.environ.get("UPLOADS_DIR", "/data/uploads"))


def reconcile_orphan_batches() -> dict:
    """Au démarrage du worker : un lot resté 'running' = job interrompu (worker
    tombé). On le repasse en 'failed' avec un message clair. Les lots 'pending'
    restent en file (RQ les rejoue). Évite les lots « en cours » fantômes (§8)."""
    with SessionLocal() as db:
        orphans = db.query(Batch).filter(Batch.status == "running").all()
        for b in orphans:
            b.status = "failed"
            b.error_message = "Traitement interrompu (redémarrage du worker)."
            b.finished_at = _now()
        n = len(orphans)
        if n:
            db.commit()
        return {"reconciled": n}


def predict_one_job(text: str, satisfaction=None) -> dict:
    """Prédiction unitaire (test à la volée) avec le modèle actif. Renvoie le dict de sortie."""
    cfg = build_worker_cfg()
    with SessionLocal() as db:
        active = get_active(db)
        label = active.label if active else None
    predictor = get_predictor(active, cfg)
    masked, _ = predictor.anonymizer.anonymize(text or "")
    cleaned = predictor.cleaner.clean(masked)
    result = predictor.predict_cleaned_batch([cleaned], [satisfaction])[0]
    result["model_label"] = label
    return result


def _now():
    return datetime.now(timezone.utc)


def _jsonable(value):
    """Convertit une valeur pandas/numpy en type JSON-sérialisable."""
    if value is None:
        return None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value
    # Timestamps, numpy scalars, etc.
    try:
        import numpy as np
        if isinstance(value, np.generic):
            return value.item()
    except Exception:
        pass
    return str(value)


def _to_result(batch_id: int, gidx: int, source, pred: dict, original: dict) -> Result:
    def _s(key):
        v = pred.get(key)
        return v if v not in ("", None) else None

    return Result(
        batch_id=batch_id, row_index=int(gidx), source=source,
        verbatim_analyse=pred.get("verbatim_analysé", ""),
        nb_themes=int(pred.get("nb_themes", 0)),
        theme1_niv1=_s("theme1_niv1"), theme1_niv2=_s("theme1_niv2"),
        theme1_sentiment=_s("theme1_sentiment"),
        theme1_score=pred.get("theme1_score_confiance") or None,
        theme2_niv1=_s("theme2_niv1"), theme2_niv2=_s("theme2_niv2"),
        theme2_sentiment=_s("theme2_sentiment"),
        theme2_score=(pred.get("theme2_score_confiance") or None) if pred.get("theme2_score_confiance") not in ("", None) else None,
        signal_rupture=bool(pred.get("signal_rupture_client", False)),
        signal_churn=bool(pred.get("signal_churn", False)),
        signal_insatisfaction=bool(pred.get("signal_insatisfaction_forte", False)),
        confidence_globale=pred.get("confidence_globale"),
        revue_requise=bool(pred.get("revue_humaine_requise", False)),
        original_columns=original,
    )


def process_batch_job(batch_id: int) -> dict:
    """Traite un lot complet et persiste les résultats. Renvoie un résumé."""
    from src.preprocessing.loader import COL_SATISFACTION, COL_SOURCE, COL_TEXT, load_for_batch

    cfg = build_worker_cfg()
    with SessionLocal() as db:
        batch = db.get(Batch, batch_id)
        if batch is None:
            logger.error("Lot %s introuvable.", batch_id)
            return {"status": "missing"}
        if batch.status == "canceled":  # annulé avant la prise en charge
            logger.info("Lot %s annulé avant démarrage — ignoré.", batch_id)
            return {"status": "canceled"}

        active = get_active(db)
        cfg["thresholds"]["revue_humaine"] = batch.seuil_revue
        started = _now()
        batch.status = "running"
        batch.started_at = started
        batch.model_label = active.label if active else None
        db.commit()
        logger.info("Lot %s : démarrage (modèle=%s)", batch_id, batch.model_label)

        try:
            predictor = get_predictor(active, cfg)
            files = batch.source_files or {}
            df = load_for_batch(files.get("mdtc"), files.get("mopinion"), cfg)
            total = len(df)
            batch.n_total = total
            db.commit()

            texts = df[COL_TEXT].tolist() if COL_TEXT in df.columns else [""] * total
            sats = df[COL_SATISFACTION].tolist() if COL_SATISFACTION in df.columns else [None] * total
            orig_cols = [c for c in df.columns if not str(c).startswith("__")]

            pii = Counter()
            n_review = 0
            n_err = 0

            for start in range(0, total, PROGRESS_CHUNK):
                # Annulation coopérative : l'API a pu passer le lot en 'canceled'
                # (requête fraîche, hors cache de session).
                if db.query(Batch.status).filter(Batch.id == batch_id).scalar() == "canceled":
                    batch.status = "canceled"
                    batch.n_processed = start
                    batch.n_review = n_review
                    batch.n_errors = n_err
                    batch.pii_masked = dict(pii)
                    batch.finished_at = _now()
                    db.commit()
                    logger.info("Lot %s annulé en cours (%d/%d traités).", batch_id, start, total)
                    return {"status": "canceled", "n_processed": start}
                rows = df.iloc[start:start + PROGRESS_CHUNK]
                raw_chunk = texts[start:start + PROGRESS_CHUNK]
                sat_chunk = sats[start:start + PROGRESS_CHUNK]

                cleaned = []
                for raw in raw_chunk:
                    try:
                        masked, counts = predictor.anonymizer.anonymize(raw)
                        pii.update(counts)
                        cleaned.append(predictor.cleaner.clean(masked))
                    except Exception as exc:  # un verbatim défaillant n'arrête pas le lot
                        logger.warning("Prétraitement KO (lot %s, ligne %s) : %s", batch_id, start, exc)
                        cleaned.append("")
                        n_err += 1

                preds = predictor.predict_cleaned_batch(cleaned, sat_chunk)
                for i, pred in enumerate(preds):
                    gidx = start + i
                    row = rows.iloc[i]
                    original = {c: _jsonable(row[c]) for c in orig_cols}
                    db.add(_to_result(batch_id, gidx, _jsonable(row.get(COL_SOURCE)), pred, original))
                    if pred.get("revue_humaine_requise"):
                        n_review += 1

                batch.n_processed = min(start + PROGRESS_CHUNK, total)
                db.commit()

            finished = _now()
            batch.status = "done"
            batch.finished_at = finished
            batch.n_review = n_review
            batch.n_errors = n_err
            batch.pii_masked = dict(pii)
            batch.duration_s = (finished - started).total_seconds()
            db.commit()
            logger.info("Lot %s terminé : %d traités, %d en revue, %d erreurs.", batch_id, total, n_review, n_err)
            return {"status": "done", "n_total": total, "n_review": n_review, "n_errors": n_err}

        except Exception as exc:
            logger.exception("Lot %s en échec : %s", batch_id, exc)
            db.rollback()
            batch = db.get(Batch, batch_id)
            if batch:
                batch.status = "failed"
                batch.error_message = str(exc)[:1000]
                batch.finished_at = _now()
                db.commit()
            return {"status": "failed", "error": str(exc)}
