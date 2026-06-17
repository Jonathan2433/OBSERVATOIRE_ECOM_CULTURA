"""Modèle ORM Résultat de classification (un par verbatim).

RGPD : ``verbatim_analyse`` ne contient QUE le texte anonymisé. Le texte brut
n'est jamais stocké en base.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Result(Base):
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id", ondelete="CASCADE"), index=True, nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    verbatim_analyse: Mapped[str] = mapped_column(Text, default="")
    nb_themes: Mapped[int] = mapped_column(Integer, default=0)

    theme1_niv1: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    theme1_niv2: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    theme1_sentiment: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    theme1_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    theme2_niv1: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    theme2_niv2: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    theme2_sentiment: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    theme2_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    signal_rupture: Mapped[bool] = mapped_column(Boolean, default=False)
    signal_churn: Mapped[bool] = mapped_column(Boolean, default=False)
    signal_insatisfaction: Mapped[bool] = mapped_column(Boolean, default=False)

    confidence_globale: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    revue_requise: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    corrected: Mapped[bool] = mapped_column(Boolean, default=False)  # utilisé au lot L5

    # Colonnes d'origine du fichier source (pour le CSV enrichi).
    original_columns: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
