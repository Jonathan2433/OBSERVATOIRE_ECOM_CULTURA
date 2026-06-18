"""Modèle ORM Journal d'audit (traçabilité des actions sensibles)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
