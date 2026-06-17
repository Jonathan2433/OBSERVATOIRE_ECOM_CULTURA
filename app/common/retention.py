"""Purge des données au-delà de la durée de rétention (RGPD).

Supprime les lots (et leurs résultats/corrections) plus anciens que la rétention,
ainsi que les fichiers sources déposés. Utilisé par l'API (purge manuelle) et le
worker (purge au démarrage).
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from .models import Batch, Correction, Result

logger = logging.getLogger("retention")


def purge_old_batches(db: Session, retention_months: int, uploads_dir: Optional[str] = None) -> dict:
    """Purge les lots créés il y a plus de ``retention_months`` mois.

    Renvoie {'batches': n, 'cutoff': iso}. Si retention_months <= 0 : aucune purge.
    """
    if not retention_months or retention_months <= 0:
        return {"batches": 0, "cutoff": None}

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_months * 30)
    old = db.query(Batch).filter(Batch.created_at.isnot(None), Batch.created_at < cutoff).all()
    n = 0
    for b in old:
        db.query(Correction).filter(Correction.batch_id == b.id).delete(synchronize_session=False)
        db.query(Result).filter(Result.batch_id == b.id).delete(synchronize_session=False)
        db.delete(b)
        if uploads_dir:
            shutil.rmtree(Path(uploads_dir) / str(b.id), ignore_errors=True)
        n += 1
    db.commit()
    if n:
        logger.info("Purge rétention : %d lot(s) supprimé(s) (antérieurs au %s).", n, cutoff.date())
    return {"batches": n, "cutoff": cutoff.isoformat()}
