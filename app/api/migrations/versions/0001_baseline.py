"""baseline (schéma vide)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-17

Migration initiale : ne crée aucune table. Les tables (users, batches,
results, corrections, model_versions, audit_log, app_config) seront ajoutées
par les lots L1 -> L7.
"""
from __future__ import annotations

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
