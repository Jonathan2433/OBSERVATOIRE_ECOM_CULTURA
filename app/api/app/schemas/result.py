"""Schémas des résultats de classification et du test à la volée."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    row_index: int
    source: Optional[str] = None
    verbatim_analyse: str = ""
    nb_themes: int = 0
    theme1_niv1: Optional[str] = None
    theme1_niv2: Optional[str] = None
    theme1_sentiment: Optional[str] = None
    theme1_score: Optional[float] = None
    theme2_niv1: Optional[str] = None
    theme2_niv2: Optional[str] = None
    theme2_sentiment: Optional[str] = None
    theme2_score: Optional[float] = None
    signal_rupture: bool = False
    signal_churn: bool = False
    signal_insatisfaction: bool = False
    confidence_globale: Optional[float] = None
    revue_requise: bool = False
    corrected: bool = False


class ResultsResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ResultOut]


class CorrectionRequest(BaseModel):
    """Revue d'un verbatim : valider tel quel ou corriger des champs."""
    action: Literal["validate", "correct"] = "correct"
    theme1_niv1: Optional[str] = None
    theme1_niv2: Optional[str] = None
    theme1_sentiment: Optional[str] = None
    signal_rupture: Optional[bool] = None
    signal_churn: Optional[bool] = None
    signal_insatisfaction: Optional[bool] = None


class PredictRequest(BaseModel):
    text: str = Field(min_length=1)
    satisfaction: Optional[int] = None


class PredictResponse(BaseModel):
    """Sortie du test à la volée (reflète le format de prédiction)."""
    verbatim_analyse: str = Field(alias="verbatim_analysé", default="")
    nb_themes: int = 0
    theme1_niv1: str = ""
    theme1_niv2: str = ""
    theme1_sentiment: str = ""
    theme1_score_confiance: Any = 0.0
    theme2_niv1: str = ""
    theme2_niv2: str = ""
    theme2_sentiment: str = ""
    theme2_score_confiance: Any = ""
    signal_rupture_client: bool = False
    signal_churn: bool = False
    signal_insatisfaction_forte: bool = False
    confidence_globale: Any = 0.0
    revue_humaine_requise: bool = True
    model_label: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)
