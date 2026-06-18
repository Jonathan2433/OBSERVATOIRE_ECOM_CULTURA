"""Métadonnées applicatives non sensibles (pour la page d'aide & les info-bulles).

Accessible à tout utilisateur authentifié (contrairement à /api/config, réservé
admin) : seuil de revue par défaut + modèle actif. Aucune donnée sensible.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core import runtime_config as rc
from ..core.db import get_db
from ..core.security import get_current_user
from common.models import ModelVersion

router = APIRouter(prefix="/api", tags=["meta"], dependencies=[Depends(get_current_user)])


@router.get("/meta")
def app_meta(db: Session = Depends(get_db)):
    active = db.query(ModelVersion).filter_by(is_active=True, available=True).first()
    return {
        "default_seuil_revue": rc.default_seuil_revue(db),
        "active_model": ({"label": active.label, "kind": active.kind} if active else None),
    }
