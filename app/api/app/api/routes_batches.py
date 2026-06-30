"""Endpoints des lots de traitement : création (upload + enqueue), liste, détail."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..core.audit import record_audit
from ..core.config import settings
from ..core.db import get_db
from ..core.security import get_current_user
from ..models.user import User
from ..schemas.batch import BatchOut, BatchProgress
from ..services.jobs import enqueue_batch
from common.models import Batch, MODEL_KIND_CLAUDE, MODEL_KIND_LMSTUDIO, ModelVersion

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/batches", tags=["batches"], dependencies=[Depends(get_current_user)])

_ALLOWED_SUFFIX = ".xlsx"


def resolve_refiner(db: Session, refiner_label: str) -> ModelVersion:
    """Valide le 2e moteur d'une cascade (V5). Retourne le ModelVersion ou lève 400.

    Garde-fous : le raffineur DOIT être un moteur **LLM local** (`lmstudio`) disponible.
    **Claude est exclu** (offline strict de prod, V5-D1) ; **CamemBERT/stub** aussi
    (ils n'implémentent pas `refine_cleaned_batch`).
    """
    m = db.query(ModelVersion).filter_by(label=refiner_label).one_or_none()
    if m is None or not m.available:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Raffineur introuvable ou indisponible : {refiner_label}")
    if m.kind == MODEL_KIND_CLAUDE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Claude ne peut pas être raffineur en production (comparaison/test uniquement).")
    if m.kind != MODEL_KIND_LMSTUDIO:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Le raffineur doit être un moteur LLM local (LM Studio).")
    return m


async def _save_upload(upload: UploadFile, dest_dir: Path, name: str) -> str:
    if not upload.filename.lower().endswith(_ALLOWED_SUFFIX):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Format non supporté pour {upload.filename} (.xlsx attendu)")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    content = await upload.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"Fichier trop volumineux (> {settings.max_upload_mb} Mo)")
    dest.write_bytes(content)
    return str(dest)


@router.post("", response_model=BatchOut, status_code=status.HTTP_201_CREATED)
async def create_batch(
    label: Optional[str] = Form(None),
    seuil_revue: float = Form(0.70),
    refiner_label: Optional[str] = Form(None),
    mdtc: Optional[UploadFile] = File(None),
    mopinion: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if mdtc is None and mopinion is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Fournir au moins un fichier (MDTC ou Mopinion).")
    if not (0.0 <= seuil_revue <= 1.0):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="seuil_revue doit être entre 0 et 1.")

    # Cascade V5 (opt-in) : valide le raffineur AVANT toute création (refus si non LLM/indispo).
    refiner = (refiner_label or "").strip() or None
    if refiner is not None:
        resolve_refiner(db, refiner)

    # Crée d'abord le lot pour obtenir un id, puis range les fichiers sous cet id.
    batch = Batch(label=label or "lot", status="pending", seuil_revue=seuil_revue,
                  created_by=current_user.id, refiner_label=refiner)
    db.add(batch)
    db.flush()  # -> batch.id
    if not label:
        batch.label = f"lot-{batch.id}"

    dest_dir = Path(settings.uploads_dir) / str(batch.id)
    source_files = {}
    if mdtc is not None:
        source_files["mdtc"] = await _save_upload(mdtc, dest_dir, "mdtc.xlsx")
    if mopinion is not None:
        source_files["mopinion"] = await _save_upload(mopinion, dest_dir, "mopinion.xlsx")
    batch.source_files = source_files
    db.commit()
    db.refresh(batch)

    try:
        enqueue_batch(batch.id)
    except Exception as exc:  # Redis indisponible : on marque l'échec proprement
        batch.status = "failed"
        batch.error_message = f"Mise en file impossible : {exc}"
        db.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="File de traitement indisponible.")
    _cascade = f" ▶ raffineur={refiner}" if refiner else ""
    record_audit(db, action="batch.create", user=current_user, entity="batch", entity_id=batch.id,
                 details=f"{batch.label} (seuil={seuil_revue}){_cascade}")
    logger.info("Lot %s créé par %s", batch.id, current_user.username)
    return batch


@router.get("", response_model=list[BatchOut])
def list_batches(db: Session = Depends(get_db), limit: int = 100):
    return db.query(Batch).order_by(Batch.id.desc()).limit(min(limit, 500)).all()


@router.get("/{batch_id}", response_model=BatchOut)
def get_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lot introuvable")
    return batch


@router.get("/{batch_id}/progress", response_model=BatchProgress)
def get_progress(batch_id: int, db: Session = Depends(get_db)):
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lot introuvable")
    return BatchProgress(id=batch.id, status=batch.status, n_total=batch.n_total,
                         n_processed=batch.n_processed, progress=batch.progress)


@router.post("/{batch_id}/cancel", response_model=BatchOut)
def cancel_batch(batch_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """Annule un lot en attente ou en cours. Le worker s'arrête proprement
    (annulation coopérative, vérifiée entre deux tranches)."""
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lot introuvable")
    if batch.status not in ("pending", "running"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Lot non annulable (statut : {batch.status}).")
    batch.status = "canceled"
    batch.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(batch)
    record_audit(db, action="batch.cancel", user=current_user, entity="batch", entity_id=batch.id)
    logger.info("Lot %s annulé par %s", batch_id, current_user.username)
    return batch
