"""Réponse de questionnaire, unité statistique de la satisfaction.

Une réponse peut produire plusieurs verbatims (donc plusieurs ``Result``), mais
elle ne doit compter qu'une fois dans les KPI de satisfaction.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

CLIENT_STATUSES = ("ancien", "nouveau", "non_renseigne")


class SurveyResponse(Base):
    __tablename__ = "survey_responses"
    __table_args__ = (
        CheckConstraint(
            "client_status IN ('ancien', 'nouveau', 'non_renseigne')",
            name="ck_survey_responses_client_status",
        ),
        CheckConstraint(
            "satisfaction_scale_max IN (4, 5)",
            name="ck_survey_responses_scale_max",
        ),
        UniqueConstraint(
            "batch_id", "source_type", "source_file", "respondent_key",
            name="uq_survey_response_scope",
        ),
        # Les comparaisons portent sur la période métier contenue dans les
        # exports. Cet index évite de parcourir tout l'historique pour calculer
        # les bornes d'une source dans un lot.
        Index("ix_survey_responses_batch_source_date", "batch_id", "source_type", "response_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("batches.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    # Empreinte SHA-256 du contexte source : aucun identifiant source n'est exposé.
    respondent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # Jour de la réponse dans le fichier source. NULL signifie « période métier
    # indisponible » ; created_at du lot ne doit jamais lui être substitué.
    response_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    satisfaction_native: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    satisfaction_scale_max: Mapped[int] = mapped_column(Integer, nullable=False)
    # Valeur 1..4 conservée uniquement pour le modèle ML historique.
    satisfaction_normalized: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rating_invalid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    client_status: Mapped[str] = mapped_column(
        String(20), default="non_renseigne", nullable=False, index=True)
