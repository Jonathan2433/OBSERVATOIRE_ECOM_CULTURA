"""Point d'entrée de l'API FastAPI — Observatoire Ecom Studio."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import APP_NAME, __version__
from .api.routes_health import router as health_router
from .core.config import settings
from .core.logging import setup_logging

setup_logging()

app = FastAPI(
    title=APP_NAME,
    version=__version__,
    description="API interne de classification et de pilotage des verbatims clients Cultura.",
)

# CORS verrouillé sur les origines locales (mono-poste, localhost uniquement).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)

# Les routers fonctionnels (auth, batches, results, review, kpi, admin)
# seront ajoutés au fil des lots L1 -> L7.
