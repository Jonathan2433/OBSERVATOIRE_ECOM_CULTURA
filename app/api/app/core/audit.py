"""Journalisation d'audit — trace les actions sensibles (RGPD / traçabilité)."""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from common.models import AuditLog

logger = logging.getLogger("audit")


def record_audit(db: Session, *, action: str, user=None, username: Optional[str] = None,
                 entity: Optional[str] = None, entity_id: Any = None,
                 details: Optional[str] = None) -> None:
    """Ajoute une entrée d'audit (transaction indépendante)."""
    try:
        db.add(AuditLog(
            user_id=getattr(user, "id", None),
            username=username or getattr(user, "username", None),
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=details,
        ))
        db.commit()
    except Exception as exc:  # l'audit ne doit jamais casser l'action métier
        logger.warning("Échec d'écriture d'audit (%s) : %s", action, exc)
        db.rollback()
