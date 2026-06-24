"""Modèle ORM Prédiction d'un moteur (V5).

Une ligne = la prédiction d'UN moteur pour UN verbatim. Sert à la fois :
  - à la **cascade** (rôles ``proposer`` / ``refiner`` ; deux lignes par verbatim,
    rattachées au ``result`` final qui fait foi) — lot C3 ;
  - à la **comparaison** (rôle ``compare`` ; rattachée à un ``comparison_run``) — lot C4.

RGPD : ne contient aucune donnée brute (uniquement des libellés de classification).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# Rôle de la prédiction dans son contexte.
ENGINE_ROLE_PROPOSER = "proposer"   # moteur 1 d'une cascade
ENGINE_ROLE_REFINER = "refiner"     # moteur 2 d'une cascade (sa sortie fait foi)
ENGINE_ROLE_COMPARE = "compare"     # replay d'un run de comparaison (C4)
ENGINE_ROLES = (ENGINE_ROLE_PROPOSER, ENGINE_ROLE_REFINER, ENGINE_ROLE_COMPARE)


class EnginePrediction(Base):
    __tablename__ = "engine_predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("batches.id", ondelete="CASCADE"), index=True, nullable=True)
    # FK ajoutée en C4 avec la table comparison_runs ; colonne nullable dès maintenant.
    comparison_run_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    result_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("results.id", ondelete="CASCADE"), index=True, nullable=True)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)

    engine_label: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(12), nullable=False)   # proposer | refiner | compare

    theme1_niv1: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    theme1_niv2: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    theme1_sentiment: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    confidence_globale: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    signal_rupture: Mapped[bool] = mapped_column(Boolean, default=False)
    signal_churn: Mapped[bool] = mapped_column(Boolean, default=False)
    signal_insatisfaction: Mapped[bool] = mapped_column(Boolean, default=False)

    latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
