"""Endpoints KPI : tableau de bord du lot, volumétrie globale, métriques modèle."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import get_current_user
from common.models import Batch, ModelVersion, Result

router = APIRouter(prefix="/api", tags=["kpi"], dependencies=[Depends(get_current_user)])


def _distribution(db: Session, batch_id: int, column) -> dict:
    rows = (
        db.query(column, func.count(Result.id))
        .filter(Result.batch_id == batch_id, column.isnot(None), column != "")
        .group_by(column)
        .all()
    )
    return {k: v for k, v in sorted(rows, key=lambda x: -x[1])}


def _theme_sentiment(db: Session, batch_id: int | None = None) -> dict:
    """Croisement thème niv.1 × sentiment (volumétrie) -> {niv1: {sentiment: n}}."""
    q = db.query(Result.theme1_niv1, Result.theme1_sentiment, func.count(Result.id)).filter(
        Result.theme1_niv1.isnot(None), Result.theme1_niv1 != "",
        Result.theme1_sentiment.isnot(None),
    )
    if batch_id is not None:
        q = q.filter(Result.batch_id == batch_id)
    out: dict = {}
    for niv1, sent, n in q.group_by(Result.theme1_niv1, Result.theme1_sentiment).all():
        out.setdefault(niv1, {})[sent] = n
    # Trié par volume total décroissant.
    return dict(sorted(out.items(), key=lambda kv: -sum(kv[1].values())))


def _signal_counts(db: Session, batch_id: int) -> dict:
    base = db.query(func.count(Result.id)).filter(Result.batch_id == batch_id)
    return {
        "rupture": base.filter(Result.signal_rupture == True).scalar() or 0,  # noqa: E712
        "churn": base.filter(Result.signal_churn == True).scalar() or 0,  # noqa: E712
        "insatisfaction": base.filter(Result.signal_insatisfaction == True).scalar() or 0,  # noqa: E712
    }


@router.get("/batches/{batch_id}/kpi")
def batch_kpi(batch_id: int, db: Session = Depends(get_db)):
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lot introuvable")
    return {
        "batch_id": batch.id,
        "label": batch.label,
        "status": batch.status,
        "model_label": batch.model_label,
        "n_total": batch.n_total,
        "n_processed": batch.n_processed,
        "n_review": batch.n_review,
        "review_rate": (batch.n_review / batch.n_total) if batch.n_total else 0.0,
        "n_errors": batch.n_errors,
        "duration_s": batch.duration_s,
        "themes": _distribution(db, batch_id, Result.theme1_niv1),
        "subthemes": _distribution(db, batch_id, Result.theme1_niv2),
        "sentiments": _distribution(db, batch_id, Result.theme1_sentiment),
        "sources": _distribution(db, batch_id, Result.source),
        "signals": _signal_counts(db, batch_id),
        "theme_sentiment": _theme_sentiment(db, batch_id),
    }


@router.get("/kpi/volumetry")
def volumetry(db: Session = Depends(get_db)):
    """Séries par lot (volume, taux de revue, signaux) + top thèmes global."""
    batches = db.query(Batch).filter(Batch.status == "done").order_by(Batch.created_at).all()
    series = []
    for b in batches:
        series.append({
            "id": b.id,
            "label": b.label,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "n_total": b.n_total,
            "n_review": b.n_review,
            "review_rate": (b.n_review / b.n_total) if b.n_total else 0.0,
            "signals": _signal_counts(db, b.id),
        })

    global_themes = dict(
        sorted(
            db.query(Result.theme1_niv1, func.count(Result.id))
            .filter(Result.theme1_niv1.isnot(None), Result.theme1_niv1 != "")
            .group_by(Result.theme1_niv1)
            .all(),
            key=lambda x: -x[1],
        )
    )
    return {
        "n_batches": len(batches),
        "total_verbatims": sum(b.n_total for b in batches),
        "series": series,
        "global_themes": global_themes,
        "theme_sentiment": _theme_sentiment(db, None),
    }


@router.get("/kpi/model")
def model_kpi(db: Session = Depends(get_db)):
    """Métriques de la version de modèle active (None si stub)."""
    active = db.query(ModelVersion).filter_by(is_active=True).first()
    if active is None:
        return {"active": None}
    return {
        "active": {
            "label": active.label,
            "kind": active.kind,
            "available": active.available,
            "metrics": active.metrics,
        }
    }
