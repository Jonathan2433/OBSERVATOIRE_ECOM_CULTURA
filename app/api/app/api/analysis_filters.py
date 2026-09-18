"""Périmètre source/date commun aux résultats, exports, revue et KPI."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

from fastapi import HTTPException, status

from common.models import Result, SurveyResponse


@dataclass(frozen=True)
class AnalysisScope:
    sources: tuple[str, ...] = ()
    date_from: Optional[date] = None
    date_to: Optional[date] = None

    @property
    def has_dates(self) -> bool:
        return self.date_from is not None or self.date_to is not None

    def without_dates(self) -> "AnalysisScope":
        return AnalysisScope(sources=self.sources)


def build_analysis_scope(
    sources: Optional[Iterable[str]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> AnalysisScope:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="date_from doit être antérieure ou égale à date_to.",
        )
    normalized = []
    for source in sources or ():
        value = str(source).strip()
        if value and value not in normalized:
            normalized.append(value)
    if len(normalized) > 20 or any(len(value) > 40 for value in normalized):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Filtre source invalide.",
        )
    return AnalysisScope(tuple(normalized), date_from, date_to)


def apply_result_scope(query, scope: AnalysisScope):
    """Applique le périmètre à une requête portant sur ``Result``.

    Une restriction de date nécessite une réponse source liée. Les résultats
    historiques sans date restent visibles sans filtre, mais sont exclus d'une
    période explicite plutôt que de recevoir une date inventée.
    """
    if scope.sources:
        query = query.filter(Result.source.in_(scope.sources))
    if scope.has_dates:
        query = query.join(
            SurveyResponse, Result.survey_response_id == SurveyResponse.id)
        if scope.date_from:
            query = query.filter(SurveyResponse.response_date >= scope.date_from)
        if scope.date_to:
            query = query.filter(SurveyResponse.response_date <= scope.date_to)
    return query


def apply_response_scope(query, scope: AnalysisScope):
    """Applique le même périmètre à la maille répondant."""
    if scope.sources:
        query = query.filter(SurveyResponse.source_type.in_(scope.sources))
    if scope.date_from:
        query = query.filter(SurveyResponse.response_date >= scope.date_from)
    if scope.date_to:
        query = query.filter(SurveyResponse.response_date <= scope.date_to)
    return query
