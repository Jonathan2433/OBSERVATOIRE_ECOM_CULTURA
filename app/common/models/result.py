"""Modèle ORM Résultat de classification (un par verbatim).

RGPD : ``verbatim_analyse`` ne contient QUE le texte anonymisé. Le texte brut
n'est jamais stocké en base.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

if TYPE_CHECKING:
    from .batch import Batch
    from .survey_response import SurveyResponse


class Result(Base):
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id", ondelete="CASCADE"), index=True, nullable=False)
    survey_response_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("survey_responses.id", ondelete="CASCADE"), index=True, nullable=True)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    verbatim_analyse: Mapped[str] = mapped_column(Text, default="")
    nb_themes: Mapped[int] = mapped_column(Integer, default=0)

    #: Note de satisfaction NORMALISÉE sur l'échelle ML historique 1-4, telle
    #: qu'elle a été donnée au modèle. Ce n'est pas une sortie du modèle mais
    #: une donnée d'entrée : elle est persistée pour que le pilotage puisse
    #: croiser la classification avec la note réellement déposée par le client.
    #: Non personnelle. Elle ne doit jamais servir aux moyennes métier : la note
    #: native et son échelle vivent dans ``survey_responses``.
    #: ``None`` = le client n'a pas noté, JAMAIS « zéro ».
    satisfaction: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

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

    # Revue humaine (L5)
    corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reviewed_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Colonnes d'origine du fichier source (pour le CSV enrichi).
    original_columns: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    survey_response: Mapped[Optional["SurveyResponse"]] = relationship(lazy="joined")
    batch: Mapped["Batch"] = relationship(lazy="joined")

    @property
    def satisfaction_native(self) -> Optional[int]:
        return self.survey_response.satisfaction_native if self.survey_response else None

    @property
    def satisfaction_scale_max(self) -> Optional[int]:
        return self.survey_response.satisfaction_scale_max if self.survey_response else None

    @property
    def client_status(self) -> Optional[str]:
        return self.survey_response.client_status if self.survey_response else None

    @property
    def source_file(self) -> Optional[str]:
        return self.survey_response.source_file if self.survey_response else None

    @property
    def response_reference(self) -> Optional[str]:
        """Référence publique stable, sans exposer l'identifiant source.

        ``respondent_key`` est déjà une empreinte pour les imports récents. On
        la rehache néanmoins avant exposition afin que les lots historiques ou
        les jeux de recette portant une clé technique non hachée ne puissent
        jamais la divulguer par l'API ou un export.
        """
        if not self.survey_response or not self.survey_response.respondent_key:
            return None
        digest = hashlib.sha256(
            self.survey_response.respondent_key.encode("utf-8")
        ).hexdigest()[:16].upper()
        return f"REP-{digest}"

    @property
    def response_date(self) -> Optional[date]:
        return self.survey_response.response_date if self.survey_response else None

    @property
    def batch_processed_at(self) -> Optional[datetime]:
        return self.batch.finished_at if self.batch else None
