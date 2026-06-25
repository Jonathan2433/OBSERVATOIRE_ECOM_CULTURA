"""Accès base de données partagé (SQLAlchemy 2.0).

L'URL de connexion vient de l'environnement (DATABASE_URL), fournie par
docker-compose. Utilisé identiquement par l'API et le worker.
"""
from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://oes:oes@db:5432/oes")

if DATABASE_URL.startswith("sqlite"):
    # check_same_thread=False utile uniquement pour SQLite (tests/recettes).
    _connect_args = {"check_same_thread": False}
else:
    # psycopg3 : désactiver les *prepared statements* côté serveur.
    # Le worker RQ fork un process par job ; une connexion héritée du parent peut
    # déjà porter un statement « _pg3_N » préparé par un job précédent, d'où
    # « DuplicatePreparedStatement "_pg3_0" already exists » au job suivant
    # (observé au 2e run de comparaison). prepare_threshold=None les désactive.
    _connect_args = {"prepare_threshold": None}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Base déclarative commune à tous les modèles ORM."""


def get_db() -> Iterator[Session]:
    """Dépendance FastAPI : une session DB par requête."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
