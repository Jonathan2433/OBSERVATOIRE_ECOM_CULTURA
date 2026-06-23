"""Endpoints du registre de modèles : liste, activation (admin), rescan (admin)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.audit import record_audit
from ..core.db import get_db
from ..core.security import get_current_user, require_admin
from ..schemas.model import ModelVersionOut
from ..services.jobs import enqueue_registry_sync
from common.models import MODEL_KIND_CLAUDE, ModelVersion

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", response_model=list[ModelVersionOut], dependencies=[Depends(get_current_user)])
def list_models(db: Session = Depends(get_db)):
    return db.query(ModelVersion).order_by(ModelVersion.kind, ModelVersion.label).all()


@router.post("/{model_id}/activate", response_model=ModelVersionOut)
def activate_model(model_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    model = db.get(ModelVersion, model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Modèle introuvable")
    if model.kind == MODEL_KIND_CLAUDE:
        # Garde-fou offline strict (V5-D1) : Claude est un moteur de comparaison/test,
        # JAMAIS utilisable en production -> refus serveur à l'activation.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Moteur Claude : comparaison/test uniquement, non activable en production.")
    if not model.available:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Modèle indisponible (artefacts absents)")
    db.query(ModelVersion).update({ModelVersion.is_active: False})
    model.is_active = True
    db.commit()
    db.refresh(model)
    record_audit(db, action="model.activate", user=admin, entity="model", entity_id=model.id, details=model.label)
    logger.info("Modèle actif : %s (par %s)", model.label, admin.username)
    return model


@router.post("/rescan")
def rescan_models(admin=Depends(require_admin)):
    """Demande au worker de re-scanner /data/models (après dépôt d'un nouveau modèle)."""
    job_id = enqueue_registry_sync()
    return {"status": "scheduled", "job_id": job_id}
