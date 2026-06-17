"""Réexport des modèles ORM partagés (``common.models``).

Conservé pour compatibilité (``from app.models import ...``, autogenerate Alembic).
"""
from common.models import *  # noqa: F401,F403
from common.models import ROLE_ADMIN, ROLE_ANALYSTE, ROLES, User  # noqa: F401
