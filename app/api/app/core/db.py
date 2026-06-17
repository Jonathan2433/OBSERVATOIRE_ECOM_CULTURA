"""Réexport de la couche DB partagée (``common.db``).

Conservé pour compatibilité des imports existants (``from ..core.db import ...``).
La source de vérité est désormais le package partagé ``common``.
"""
from common.db import Base, SessionLocal, engine, get_db  # noqa: F401

__all__ = ["Base", "SessionLocal", "engine", "get_db"]
