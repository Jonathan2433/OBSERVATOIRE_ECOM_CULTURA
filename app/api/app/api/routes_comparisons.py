"""Endpoints de comparaison de moteurs (V5, lot C4).

RBAC (SPEC_V5 §16) : **lancer** un run = admin uniquement (gouvernance coût + égress) ;
**consulter** = analyste+. Le replay ne porte que sur ``results.verbatim_analyse``
(déjà anonymisé). Claude est autorisé comme moteur de comparaison (jamais en prod).
"""
from __future__ import annotations

import csv
import io
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..core.audit import record_audit
from ..core.db import get_db
from ..core.security import get_current_user, require_admin
from ..schemas.comparison import ComparisonCreate, ComparisonRunOut
from ..services.jobs import enqueue_comparison
from common.models import Batch, ComparisonRun, EnginePrediction, ModelVersion

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["comparisons"], dependencies=[Depends(get_current_user)])

DEFAULT_SAMPLE_SIZE = 50
MAX_SAMPLE_SIZE = 200   # borne dure (V5-D10) ; voir config.yaml comparison.max_sample_size


@router.post("/batches/{batch_id}/comparisons", response_model=ComparisonRunOut,
             status_code=status.HTTP_201_CREATED)
def create_comparison(batch_id: int, payload: ComparisonCreate,
                      db: Session = Depends(get_db), admin=Depends(require_admin)):
    """Lance un run de comparaison sur un échantillon d'un lot terminé (ADMIN)."""
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lot introuvable")
    if batch.status != "done":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="La comparaison ne s'applique qu'à un lot terminé.")

    # Dé-doublonnage + validation : chaque moteur doit exister et être disponible.
    labels = list(dict.fromkeys(payload.engines))
    if len(labels) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Sélectionnez au moins 2 moteurs distincts à comparer.")
    if len(labels) > 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="3 moteurs maximum.")
    for label in labels:
        m = db.query(ModelVersion).filter_by(label=label).one_or_none()
        if m is None or not m.available:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"Moteur indisponible : {label}")

    sample_size = payload.sample_size if payload.sample_size and payload.sample_size > 0 else DEFAULT_SAMPLE_SIZE
    sample_size = min(sample_size, MAX_SAMPLE_SIZE)

    run = ComparisonRun(
        batch_id=batch_id, created_by=admin.id, status="pending",
        engine_labels=labels, sample_size=sample_size, seed=int(payload.seed or 0),
        judge_enabled=bool(payload.judge_enabled),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    try:
        enqueue_comparison(run.id)
    except Exception as exc:  # Redis indisponible
        run.status = "failed"
        run.error_message = f"Mise en file impossible : {exc}"
        db.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="File de traitement indisponible.")
    record_audit(db, action="comparison.run", user=admin, entity="comparison", entity_id=run.id,
                 details=f"lot={batch_id} moteurs={','.join(labels)} n={sample_size} juge={run.judge_enabled}")
    logger.info("Comparaison %s créée (lot %s) par %s", run.id, batch_id, admin.username)
    return run


@router.get("/comparisons", response_model=list[ComparisonRunOut])
def list_comparisons(batch_id: Optional[int] = Query(None), db: Session = Depends(get_db), limit: int = 50):
    q = db.query(ComparisonRun)
    if batch_id is not None:
        q = q.filter_by(batch_id=batch_id)
    return q.order_by(ComparisonRun.id.desc()).limit(min(limit, 200)).all()


@router.get("/comparisons/{run_id}", response_model=ComparisonRunOut)
def get_comparison(run_id: int, db: Session = Depends(get_db)):
    run = db.get(ComparisonRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run de comparaison introuvable")
    return run


@router.get("/comparisons/{run_id}/verdicts")
def get_verdicts(run_id: int, offset: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """Verdicts du juge Claude (lot C5). En C4 : toujours vide (mode dégradé)."""
    run = db.get(ComparisonRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run de comparaison introuvable")
    # Le juge arrive au lot C5 ; tant qu'il n'a pas tourné, aucune divergence n'est jugée.
    return {"total": 0, "offset": offset, "limit": limit, "items": []}


@router.get("/comparisons/{run_id}/export")
def export_comparison(run_id: int, db: Session = Depends(get_db)):
    """Export CSV des prédictions rejouées (une ligne par moteur × verbatim)."""
    run = db.get(ComparisonRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run de comparaison introuvable")
    rows = (db.query(EnginePrediction).filter_by(comparison_run_id=run_id)
            .order_by(EnginePrediction.row_index, EnginePrediction.engine_label).all())
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["row_index", "engine_label", "theme1_niv1", "theme1_niv2", "theme1_sentiment",
                "confidence_globale", "signal_rupture", "signal_churn", "signal_insatisfaction", "latency_ms"])
    for r in rows:
        w.writerow([r.row_index, r.engine_label, r.theme1_niv1 or "", r.theme1_niv2 or "",
                    r.theme1_sentiment or "", r.confidence_globale if r.confidence_globale is not None else "",
                    int(r.signal_rupture), int(r.signal_churn), int(r.signal_insatisfaction),
                    round(r.latency_ms, 2) if r.latency_ms is not None else ""])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="comparison_{run_id}.csv"'})
