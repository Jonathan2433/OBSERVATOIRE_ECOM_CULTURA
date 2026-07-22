"""thèmes/sous-thèmes ajoutés en revue humaine (taxonomy_entries)

Revision ID: 0009_taxonomy_entries
Revises: 0008_judge_verdicts
Create Date: 2026-07-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_taxonomy_entries"
down_revision = "0008_judge_verdicts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "taxonomy_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("niv1", sa.String(length=120), nullable=False),
        sa.Column("niv2", sa.String(length=120), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("niv1", "niv2", name="uq_taxonomy_entries_pair"),
    )
    op.create_index("ix_taxonomy_entries_niv1", "taxonomy_entries", ["niv1"])


def downgrade() -> None:
    op.drop_index("ix_taxonomy_entries_niv1", table_name="taxonomy_entries")
    op.drop_table("taxonomy_entries")
