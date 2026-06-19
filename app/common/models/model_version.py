"""Modèle ORM Version de modèle (registre des modèles disponibles)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

MODEL_KIND_STUB = "stub"       # classifieur heuristique (démonstration / avant entraînement)
MODEL_KIND_REAL = "real"       # modèle CamemBERT entraîné, déposé dans /data/models
MODEL_KIND_OLLAMA = "ollama"   # moteur LLM local servi par Ollama (V4)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)        # stub | real
    label: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True) # extrait de eval_report.json
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
