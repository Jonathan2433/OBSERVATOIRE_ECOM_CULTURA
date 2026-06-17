"""Point d'entrée de l'API FastAPI — Observatoire Ecom Studio."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import APP_NAME, __version__
from .api.routes_auth import router as auth_router
from .api.routes_batches import router as batches_router
from .api.routes_health import router as health_router
from .api.routes_models import router as models_router
from .api.routes_users import router as users_router
from .core.config import settings
from .core.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Amorçage de l'admin initial (si aucun compte). Les tables sont créées par
    # Alembic (lancé avant uvicorn dans l'entrypoint du conteneur).
    try:
        from .seed import ensure_stub_model, seed_admin

        seed_admin()
        ensure_stub_model()
    except Exception as exc:  # pragma: no cover - ne bloque pas le démarrage
        logger.warning("Amorçage ignoré (%s)", exc)
    yield


app = FastAPI(
    title=APP_NAME,
    version=__version__,
    description="API interne de classification et de pilotage des verbatims clients Cultura.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(batches_router)
app.include_router(models_router)

# Routers fonctionnels suivants (results, review, kpi détaillés) : lots L4 -> L7.
