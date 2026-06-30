"""Schémas des runs de comparaison de moteurs (V5)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ComparisonCreate(BaseModel):
    """Création d'un run de comparaison (admin)."""
    engines: list[str] = Field(min_length=2, max_length=3)   # 2-3 moteurs à comparer
    sample_size: int = 50
    seed: int = 0
    judge_enabled: bool = False                              # juge Claude (lot C5)


class ComparisonRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    batch_id: int
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    status: str
    engine_labels: list[str]
    sample_size: int
    seed: int
    judge_enabled: bool
    metrics: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
