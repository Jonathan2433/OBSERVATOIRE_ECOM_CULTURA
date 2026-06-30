"""Modèle ORM Run de comparaison (V5, lot C4).

Un run rejoue un **échantillon d'un lot déjà traité** à travers 2-3 moteurs et mesure
leurs écarts (accord inter-moteurs, confiance, latence). Les prédictions rejouées
sont stockées dans ``engine_predictions`` (rôle ``compare``, ``comparison_run_id``).
Le **juge Claude** (win-rate sur divergences) est ajouté au lot C5.

RGPD : ne stocke que des métriques agrégées + des libellés de moteurs. Le replay
n'utilise que ``results.verbatim_analyse`` (déjà anonymisé + nettoyé).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# Cycle de vie d'un run de comparaison (calqué sur les lots).
COMPARISON_STATUSES = ("pending", "running", "done", "failed", "canceled")


class ComparisonRun(Base):
    __tablename__ = "comparison_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("batches.id", ondelete="CASCADE"), index=True, nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # users.id
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)

    engine_labels: Mapped[list] = mapped_column(JSON, nullable=False)   # moteurs comparés (2-3 libellés)
    sample_size: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    judge_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # juge Claude (C5)

    metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)    # accord/confiance/latence agrégés
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
