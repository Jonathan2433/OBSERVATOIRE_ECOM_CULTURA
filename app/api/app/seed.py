"""Amorçage : crée un administrateur initial si la base ne contient aucun compte."""
from __future__ import annotations

import logging

from .core.config import settings
from .core.db import SessionLocal
from .core.security import hash_password
from .models.user import ROLE_ADMIN, User

logger = logging.getLogger(__name__)

_DEFAULT_PASSWORD = "admin-changeme-12+"


def seed_admin() -> None:
    with SessionLocal() as db:
        if db.query(User).count() > 0:
            return
        password = settings.admin_password or _DEFAULT_PASSWORD
        db.add(User(
            username=settings.admin_username,
            password_hash=hash_password(password),
            role=ROLE_ADMIN,
            is_active=True,
        ))
        db.commit()
        if not settings.admin_password:
            logger.warning(
                "Admin initial '%s' créé avec un mot de passe PAR DÉFAUT. "
                "Définissez ADMIN_PASSWORD dans .env et changez-le immédiatement.",
                settings.admin_username,
            )
        else:
            logger.info("Admin initial '%s' créé.", settings.admin_username)
