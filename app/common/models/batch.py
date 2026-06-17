"""Modèle ORM Lot de traitement (batch)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# Cycle de vie d'un lot.
BATCH_STATUSES = ("pending", "running", "done", "failed", "canceled")


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # users.id
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    model_label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    seuil_revue: Mapped[float] = mapped_column(Float, default=0.70, nullable=False)

    n_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    n_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    n_review: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    n_errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    source_files: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    pii_masked: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    duration_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    @property
    def progress(self) -> float:
        return (self.n_processed / self.n_total) if self.n_total else 0.0
