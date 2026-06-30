"""Modèle ORM Verdict du juge Claude (V5, lot C5).

Une ligne = l'arbitrage d'UN désaccord par le juge Claude, sur une paire de moteurs.
Le juge est **aveuglé** (il voit « A » / « B », jamais les noms de moteurs) et l'ordre
A/B est **permuté aléatoirement** à l'appel (V5-D11) ; ``engine_a``/``engine_b`` stockent
les **vrais** libellés (l'aveuglement n'est appliqué qu'à l'appel, pas au stockage).

RGPD : ``classif_a``/``classif_b`` sont des libellés de classification ; le verbatim
n'est pas dupliqué ici (récupéré via ``result_id`` quand nécessaire).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

JUDGE_WINNERS = ("a", "b", "tie")


class JudgeVerdict(Base):
    __tablename__ = "judge_verdicts"

    id: Mapped[int] = mapped_column(primary_key=True)
    comparison_run_id: Mapped[int] = mapped_column(
        ForeignKey("comparison_runs.id", ondelete="CASCADE"), index=True, nullable=False)
    result_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("results.id", ondelete="CASCADE"), nullable=True)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)

    engine_a: Mapped[str] = mapped_column(String(100), nullable=False)   # vrai libellé (côté A à l'appel)
    engine_b: Mapped[str] = mapped_column(String(100), nullable=False)   # vrai libellé (côté B à l'appel)
    classif_a: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    classif_b: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    winner: Mapped[str] = mapped_column(String(4), nullable=False)       # a | b | tie
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
