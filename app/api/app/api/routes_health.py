"""Endpoints de santé (health checks) — utilisés par Docker et le front."""
from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text

from .. import APP_NAME, __version__
from ..core.config import settings
from ..core.db import engine

logger = logging.getLogger(__name__)
router = APIRouter()


def _check_db() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # pragma: no cover
        logger.warning("DB indisponible : %s", exc)
        return False


def _check_redis() -> bool:
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        return bool(client.ping())
    except Exception as exc:  # pragma: no cover
        logger.warning("Redis indisponible : %s", exc)
        return False


@router.get("/health", tags=["health"])
def health() -> dict:
    """Santé globale (utilisée par le healthcheck Docker). 200 si l'API répond."""
    return {"status": "ok", "app": APP_NAME, "version": __version__}


@router.get("/api/health", tags=["health"])
def health_detailed() -> dict:
    """Santé détaillée des dépendances (DB, Redis) pour le front et le diagnostic."""
    db_ok = _check_db()
    redis_ok = _check_redis()
    return {
        "status": "ok" if (db_ok and redis_ok) else "degraded",
        "app": APP_NAME,
        "version": __version__,
        "env": settings.app_env,
        "components": {"database": db_ok, "redis": redis_ok},
    }
