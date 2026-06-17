"""Revue humaine : taxonomie, file de revue, correction, export des corrections."""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..core import taxonomy as taxo
from ..core.db import get_db
from ..core.security import get_current_user
from ..models.user import User
from ..schemas.result import CorrectionRequest, ResultOut, ResultsResponse
from common.models import Batch, Correction, Result

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["review"], dependencies=[Depends(get_current_user)])

SENTIMENTS = {"Négatif", "Neutre", "Positif"}

# Champs corrigeables -> (attribut ORM, type)
_FIELDS = {
    "theme1_niv1": str, "theme1_niv2": str, "theme1_sentiment": str,
    "signal_rupture": bool, "signal_churn": bool, "signal_insatisfaction": bool,
}


@router.get("/taxonomy")
def get_taxonomy():
    """Référentiel des thèmes (pour les listes contraintes de la revue)."""
    return {"themes": taxo.themes()}


@router.get("/batches/{batch_id}/review", response_model=ResultsResponse)
def review_queue(batch_id: int, db: Session = Depends(get_db),
                 limit: int = Query(50, le=500), offset: int = 0):
    """File de revue : verbatims à revoir, triés par confiance croissante."""
    if db.get(Batch, batch_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lot introuvable")
    base = db.query(Result).filter(
        Result.batch_id == batch_id, Result.revue_requise == True, Result.reviewed == False  # noqa: E712
    )
    total = base.count()
    items = base.order_by(Result.confidence_globale.asc()).offset(offset).limit(limit).all()
    return ResultsResponse(total=total, limit=limit, offset=offset,
                           items=[ResultOut.model_validate(r) for r in items])


@router.patch("/results/{result_id}", response_model=ResultOut)
def review_result(result_id: int, payload: CorrectionRequest,
                  db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Valide (tel quel) ou corrige un verbatim, puis le sort de la file de revue."""
    res = db.get(Result, result_id)
    if res is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Résultat introuvable")

    changed = False
    if payload.action == "correct":
        # Cible niv.1/niv.2 (valeur fournie ou existante) -> contrôle hiérarchique.
        target_niv1 = payload.theme1_niv1 if payload.theme1_niv1 is not None else res.theme1_niv1
        target_niv2 = payload.theme1_niv2 if payload.theme1_niv2 is not None else res.theme1_niv2
        if (payload.theme1_niv1 is not None or payload.theme1_niv2 is not None):
            if not (target_niv1 and target_niv2 and taxo.is_valid_pair(target_niv1, target_niv2)):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail=f"Couple thème invalide : « {target_niv1} » / « {target_niv2} »")
        if payload.theme1_sentiment is not None and payload.theme1_sentiment not in SENTIMENTS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sentiment invalide")

        for field in _FIELDS:
            new = getattr(payload, field)
            if new is None:
                continue
            old = getattr(res, field)
            if new != old:
                db.add(Correction(result_id=res.id, batch_id=res.batch_id, user_id=current_user.id,
                                  field=field, old_value=str(old), new_value=str(new)))
                setattr(res, field, new)
                changed = True

    res.reviewed = True
    res.reviewed_by = current_user.id
    res.reviewed_at = datetime.now(timezone.utc)
    if changed:
        res.corrected = True
    db.commit()
    db.refresh(res)
    logger.info("Verbatim %s revu par %s (corrigé=%s)", res.id, current_user.username, changed)
    return ResultOut.model_validate(res)


@router.get("/corrections/export")
def export_corrections(db: Session = Depends(get_db)):
    """Exporte le jeu « corrections validées » (à fusionner à l'historique pour le ré-entraînement)."""
    rows = db.query(Result).filter(Result.corrected == True).order_by(Result.id).all()  # noqa: E712
    headers = ["batch_id", "source", "verbatim_analyse", "theme1_niv1", "theme1_niv2", "theme1_sentiment",
               "theme2_niv1", "theme2_niv2", "theme2_sentiment",
               "signal_rupture_client", "signal_churn", "signal_insatisfaction_forte", "reviewed_at"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow([r.batch_id, r.source or "", r.verbatim_analyse, r.theme1_niv1 or "", r.theme1_niv2 or "",
                    r.theme1_sentiment or "", r.theme2_niv1 or "", r.theme2_niv2 or "", r.theme2_sentiment or "",
                    r.signal_rupture, r.signal_churn, r.signal_insatisfaction,
                    r.reviewed_at.isoformat() if r.reviewed_at else ""])
    data = ("﻿" + buf.getvalue()).encode("utf-8")
    return StreamingResponse(io.BytesIO(data), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="corrections_validees.csv"'})
