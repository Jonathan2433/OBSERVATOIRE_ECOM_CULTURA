"""Modèles ORM partagés. Importer ce module enregistre tout dans Base.metadata."""

from .user import ROLE_ADMIN, ROLE_ANALYSTE, ROLES, User
from .batch import Batch, BATCH_STATUSES
from .result import Result
from .correction import Correction
from .model_version import (
    ModelVersion, MODEL_KIND_CLAUDE, MODEL_KIND_LMSTUDIO, MODEL_KIND_REAL, MODEL_KIND_STUB,
)
from .audit import AuditLog
from .app_config import AppConfig

__all__ = [
    "User", "ROLE_ADMIN", "ROLE_ANALYSTE", "ROLES",
    "Batch", "BATCH_STATUSES",
    "Result",
    "Correction",
    "ModelVersion", "MODEL_KIND_CLAUDE", "MODEL_KIND_LMSTUDIO", "MODEL_KIND_REAL", "MODEL_KIND_STUB",
    "AuditLog",
    "AppConfig",
]
