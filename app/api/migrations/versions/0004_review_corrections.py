"""revue humaine : champs de revue sur results + table corrections

Revision ID: 0004_review_corrections
Revises: 0003_batches_results_models
Create Date: 2026-06-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_review_corrections"
down_revision = "0003_batches_results_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("results", sa.Column("reviewed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("results", sa.Column("reviewed_by", sa.Integer(), nullable=True))
    op.add_column("results", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_results_reviewed", "results", ["reviewed"])

    op.create_table(
        "corrections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("result_id", sa.Integer(), sa.ForeignKey("results.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("field", sa.String(length=50), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_corrections_result_id", "corrections", ["result_id"])
    op.create_index("ix_corrections_batch_id", "corrections", ["batch_id"])


def downgrade() -> None:
    op.drop_table("corrections")
    op.drop_index("ix_results_reviewed", table_name="results")
    op.drop_column("results", "reviewed_at")
    op.drop_column("results", "reviewed_by")
    op.drop_column("results", "reviewed")
