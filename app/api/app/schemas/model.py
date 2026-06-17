"""Schémas du registre de modèles."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ModelVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str               # stub | real
    label: str
    is_active: bool
    available: bool
    metrics: Optional[dict[str, Any]] = None
    registered_at: Optional[datetime] = None
