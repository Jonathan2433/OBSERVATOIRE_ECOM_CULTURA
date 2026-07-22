"""Modèle ORM Entrée de taxonomie ajoutée en revue humaine.

Le référentiel de base (fichier JSON monté en lecture seule) reste la source
« officielle ». Cette table stocke les couples (niv.1, niv.2) créés à la volée
par les relecteurs quand un verbatim ne rentre dans aucune catégorie existante.
Fusionnés au référentiel de base, ils réapparaissent dans les listes de la revue
pour les verbatims suivants et les futurs lots.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class TaxonomyEntry(Base):
    __tablename__ = "taxonomy_entries"
    __table_args__ = (
        UniqueConstraint("niv1", "niv2", name="uq_taxonomy_entries_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    niv1: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    niv2: Mapped[str] = mapped_column(String(120), nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
