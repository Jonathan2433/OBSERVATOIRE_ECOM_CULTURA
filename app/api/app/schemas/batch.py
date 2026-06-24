"""Schémas des lots de traitement."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    label: str
    status: str
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    model_label: Optional[str] = None
    seuil_revue: float
    refiner_label: Optional[str] = None        # cascade V5 (None = lot mono-moteur)
    chain_disagreements: Optional[int] = None  # nb de désaccords proposeur/raffineur
    n_total: int
    n_processed: int
    n_review: int
    n_errors: int
    duration_s: Optional[float] = None
    error_message: Optional[str] = None

    # Champ calculé (0..1)
    @property
    def progress(self) -> float:
        return (self.n_processed / self.n_total) if self.n_total else 0.0


class BatchProgress(BaseModel):
    """Réponse allégée pour le polling de progression."""
    id: int
    status: str
    n_total: int
    n_processed: int
    progress: float
