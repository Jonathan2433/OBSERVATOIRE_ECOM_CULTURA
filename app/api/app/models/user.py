"""Réexport du modèle User partagé (compat. ``from ..models.user import User``)."""
from common.models.user import ROLE_ADMIN, ROLE_ANALYSTE, ROLES, User  # noqa: F401
