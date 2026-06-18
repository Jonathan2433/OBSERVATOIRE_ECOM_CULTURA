"""Administration : journal d'audit, configuration applicative, purge RGPD."""
from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core import runtime_config as rc
from ..core.audit import record_audit
from ..core.config import settings
from ..core.db import get_db
from ..core.security import require_admin
from common.models import AuditLog, Batch
from common.retention import purge_old_batches


def _dir_size(path: str) -> int:
    total = 0
    if not path or not os.path.isdir(path):
        return 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["admin"], dependencies=[Depends(require_admin)])


class ConfigPatch(BaseModel):
    retention_months: Optional[int] = None
    default_seuil_revue: Optional[float] = None


@router.get("/audit")
def list_audit(db: Session = Depends(get_db), limit: int = Query(100, le=1000), offset: int = 0):
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return [{
        "id": r.id, "user": r.username, "action": r.action,
        "entity": r.entity, "entity_id": r.entity_id, "details": r.details,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]


@router.get("/config")
def get_config(db: Session = Depends(get_db)):
    return rc.get_all(db)


@router.patch("/config")
def patch_config(payload: ConfigPatch, db: Session = Depends(get_db), admin=Depends(require_admin)):
    if payload.retention_months is not None:
        if payload.retention_months < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="retention_months >= 0")
        rc.set_value(db, "retention_months", payload.retention_months)
    if payload.default_seuil_revue is not None:
        if not (0.0 <= payload.default_seuil_revue <= 1.0):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="default_seuil_revue entre 0 et 1")
        rc.set_value(db, "default_seuil_revue", payload.default_seuil_revue)
    record_audit(db, action="config.update", user=admin, details=payload.model_dump_json())
    return rc.get_all(db)


@router.get("/admin/ops")
def ops_kpi(db: Session = Depends(get_db)):
    """KPI opérationnels (§6.4) : lots, taux d'échec, durée moyenne, rétention, disque."""
    total = db.query(func.count(Batch.id)).scalar() or 0
    by_status = dict(db.query(Batch.status, func.count(Batch.id)).group_by(Batch.status).all())
    finished = sum(by_status.get(s, 0) for s in ("done", "failed", "canceled"))
    failed = by_status.get("failed", 0)
    avg_duration = db.query(func.avg(Batch.duration_s)).filter(Batch.status == "done").scalar()

    months = rc.retention_months(db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30) if months and months > 0 else None
    purgeable = 0
    if cutoff is not None:
        purgeable = db.query(func.count(Batch.id)).filter(
            Batch.created_at.isnot(None), Batch.created_at < cutoff
        ).scalar() or 0

    up, out = settings.uploads_dir, settings.output_dir
    try:
        du = shutil.disk_usage(up if os.path.isdir(up) else "/")
        disk_free, disk_total = du.free, du.total
    except OSError:
        disk_free = disk_total = 0

    return {
        "batches": {
            "total": total,
            "by_status": by_status,
            "failure_rate": round(failed / finished, 4) if finished else 0.0,
            "avg_duration_s": round(float(avg_duration), 1) if avg_duration is not None else None,
        },
        "retention_months": months,
        "purge_cutoff": cutoff.isoformat() if cutoff else None,
        "purgeable_batches": purgeable,
        "disk": {
            "uploads_bytes": _dir_size(up),
            "output_bytes": _dir_size(out),
            "free_bytes": disk_free,
            "total_bytes": disk_total,
        },
    }


@router.post("/admin/purge")
def purge(db: Session = Depends(get_db), admin=Depends(require_admin)):
    months = rc.retention_months(db)
    result = purge_old_batches(db, months, uploads_dir=settings.uploads_dir)
    record_audit(db, action="data.purge", user=admin,
                 details=f"retention={months}m, supprimés={result['batches']}")
    return result
