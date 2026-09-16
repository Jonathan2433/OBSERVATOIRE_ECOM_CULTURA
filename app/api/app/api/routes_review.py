"""Revue humaine : taxonomie, file de revue, correction, export des corrections."""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..core import taxonomy as taxo
from ..core.audit import record_audit
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
    "theme2_niv1": str, "theme2_niv2": str, "theme2_sentiment": str,
    "signal_rupture": bool, "signal_churn": bool, "signal_insatisfaction": bool,
}


def _prepare_theme_correction(payload: CorrectionRequest, res: Result, rank: int,
                              db: Session, user_id: int) -> bool:
    """Valide et normalise un couple thème/sous-thème envoyé en revue.

    Le thème principal reste obligatoire. Le second thème est atomique mais
    facultatif : niv.1 et niv.2 doivent être renseignés ensemble, ou tous deux
    vidés pour le supprimer. Le booléen retourné indique que le rang a été
    explicitement touché, afin de remettre ``nb_themes`` en cohérence ensuite.
    """
    n1_field = f"theme{rank}_niv1"
    n2_field = f"theme{rank}_niv2"
    sentiment_field = f"theme{rank}_sentiment"
    provided = payload.model_fields_set
    pair_touched = n1_field in provided or n2_field in provided
    sentiment_touched = sentiment_field in provided

    current_n1 = getattr(res, n1_field)
    current_n2 = getattr(res, n2_field)
    target_n1 = ((getattr(payload, n1_field) if n1_field in provided else current_n1) or "").strip()
    target_n2 = ((getattr(payload, n2_field) if n2_field in provided else current_n2) or "").strip()

    if pair_touched:
        if rank == 1 and (not target_n1 or not target_n2):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Thème principal et sous-thème sont obligatoires.")
        if rank == 2 and bool(target_n1) != bool(target_n2):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Le second thème et son sous-thème doivent être renseignés ensemble.")
        if len(target_n1) > 120 or len(target_n2) > 120:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Thème / sous-thème trop long (120 caractères maximum).")

        # Les valeurs explicitement envoyées sont persistées sous leur forme
        # normalisée (sans espaces en début/fin).
        if n1_field in provided:
            setattr(payload, n1_field, target_n1)
        if n2_field in provided:
            setattr(payload, n2_field, target_n2)

        if target_n1 and not taxo.pair_is_known(db, target_n1, target_n2):
            taxo.register_pair(db, target_n1, target_n2, user_id=user_id)

        # Supprimer le thème 2 supprime aussi son sentiment : aucune valeur
        # orpheline ne doit rester dans l'export ou les KPI.
        if rank == 2 and not target_n1:
            payload.theme2_sentiment = ""
            sentiment_touched = True

    target_sentiment = (
        (getattr(payload, sentiment_field) if sentiment_touched else getattr(res, sentiment_field)) or ""
    ).strip()
    if sentiment_touched:
        setattr(payload, sentiment_field, target_sentiment)
        if target_sentiment and target_sentiment not in SENTIMENTS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sentiment invalide")
        if rank == 1 and not target_sentiment:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Le sentiment du thème principal est obligatoire.")
        if rank == 2 and target_n1 and not target_sentiment:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Le sentiment du second thème est obligatoire.")
        if rank == 2 and not target_n1 and target_sentiment:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Un sentiment secondaire nécessite un second thème.")

    # Lors de l'ajout d'un thème 2 à une ligne mono-thème, le sentiment fait
    # partie du contrat du thème et doit être fourni.
    if rank == 2 and pair_touched and target_n1 and not current_n1 and target_sentiment not in SENTIMENTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Le sentiment du second thème est obligatoire.")

    return pair_touched or sentiment_touched


@router.get("/taxonomy")
def get_taxonomy(batch_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Référentiel des thèmes (base + ajouts en revue) pour les listes de la revue.

    ``batch_id`` sert à relire un lot produit par un AUTRE moteur que l'actif —
    situation courante depuis que plusieurs modèles coexistent. Les deux
    référentiels ne partagent aucun sous-thème (D-36) : servir celui de l'actif
    proposerait au relecteur une liste sans rapport avec ce qu'il relit.
    Sans ``batch_id``, c'est le référentiel du modèle actif qui est servi.
    """
    label = None
    if batch_id is not None:
        lot = db.get(Batch, batch_id)
        if lot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lot introuvable")
        label = lot.model_label
    return {"themes": taxo.merged_themes(db, label), "model_label": label}


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
        _prepare_theme_correction(payload, res, 1, db, current_user.id)
        theme2_touched = _prepare_theme_correction(payload, res, 2, db, current_user.id)

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

        if theme2_touched:
            # ``nb_themes`` est une donnée dérivée, mais elle est exportée et
            # affichée. L'ajout/suppression du thème 2 doit donc la maintenir.
            new_count = 2 if res.theme2_niv1 and res.theme2_niv2 else (1 if res.theme1_niv1 else 0)
            if new_count != res.nb_themes:
                db.add(Correction(result_id=res.id, batch_id=res.batch_id, user_id=current_user.id,
                                  field="nb_themes", old_value=str(res.nb_themes), new_value=str(new_count)))
                res.nb_themes = new_count
                changed = True
            if not res.theme2_niv1 and res.theme2_score is not None:
                db.add(Correction(result_id=res.id, batch_id=res.batch_id, user_id=current_user.id,
                                  field="theme2_score", old_value=str(res.theme2_score), new_value="None"))
                res.theme2_score = None
                changed = True

    res.reviewed = True
    res.reviewed_by = current_user.id
    res.reviewed_at = datetime.now(timezone.utc)
    if changed:
        res.corrected = True
    db.commit()
    db.refresh(res)
    record_audit(db, action="result.correct" if changed else "result.validate",
                 user=current_user, entity="result", entity_id=res.id)
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
