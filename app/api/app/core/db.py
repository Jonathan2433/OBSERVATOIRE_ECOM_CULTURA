"""Accès base de données (SQLAlchemy 2.0).

Définit l'``engine``, la fabrique de sessions et la ``Base`` déclarative dont
hériteront les modèles ORM (ajoutés au fil des lots : users, batches, ...).
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Base déclarative commune à tous les modèles ORM."""


def get_db() -> Iterator[Session]:
    """Dépendance FastAPI : fournit une session DB par requête."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
