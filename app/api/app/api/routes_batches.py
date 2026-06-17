"""Endpoints des lots de traitement : création (upload + enqueue), liste, détail."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.db import get_db
from ..core.security import get_current_user
from ..models.user import User
from ..schemas.batch import BatchOut, BatchProgress
from ..services.jobs import enqueue_batch
from common.models import Batch

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/batches", tags=["batches"], dependencies=[Depends(get_current_user)])

_ALLOWED_SUFFIX = ".xlsx"


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

    # Crée d'abord le lot pour obtenir un id, puis range les fichiers sous cet id.
    batch = Batch(label=label or "lot", status="pending", seuil_revue=seuil_revue, created_by=current_user.id)
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
