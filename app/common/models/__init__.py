"""Modèles ORM partagés. Importer ce module enregistre tout dans Base.metadata."""

from .user import ROLE_ADMIN, ROLE_ANALYSTE, ROLES, User
from .batch import Batch, BATCH_STATUSES
from .result import Result
from .engine_prediction import (
    EnginePrediction, ENGINE_ROLE_COMPARE, ENGINE_ROLE_PROPOSER, ENGINE_ROLE_REFINER, ENGINE_ROLES,
)
from .comparison_run import ComparisonRun, COMPARISON_STATUSES
from .judge_verdict import JudgeVerdict, JUDGE_WINNERS
from .correction import Correction
from .taxonomy_entry import TaxonomyEntry
from .model_version import (
    ModelVersion, MODEL_KIND_CLAUDE, MODEL_KIND_LMSTUDIO, MODEL_KIND_REAL, MODEL_KIND_STUB,
)
from .audit import AuditLog
from .app_config import AppConfig

__all__ = [
    "User", "ROLE_ADMIN", "ROLE_ANALYSTE", "ROLES",
    "Batch", "BATCH_STATUSES",
    "Result",
    "EnginePrediction", "ENGINE_ROLE_COMPARE", "ENGINE_ROLE_PROPOSER", "ENGINE_ROLE_REFINER", "ENGINE_ROLES",
    "ComparisonRun", "COMPARISON_STATUSES",
    "JudgeVerdict", "JUDGE_WINNERS",
    "Correction",
    "TaxonomyEntry",
    "ModelVersion", "MODEL_KIND_CLAUDE", "MODEL_KIND_LMSTUDIO", "MODEL_KIND_REAL", "MODEL_KIND_STUB",
    "AuditLog",
    "AppConfig",
]
