"""juge Claude V5 : table judge_verdicts

Revision ID: 0008_judge_verdicts
Revises: 0007_comparison_runs
Create Date: 2026-06-25

Additif. Stocke l'arbitrage des désaccords par le juge Claude (lot C5).
engine_a/engine_b = vrais libellés (l'aveuglement n'est appliqué qu'à l'appel).
cf. docs/SPEC_V5_MULTI_MOTEUR §4.3 / §7.2.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_judge_verdicts"
down_revision = "0007_comparison_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "judge_verdicts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("comparison_run_id", sa.Integer(),
                  sa.ForeignKey("comparison_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("result_id", sa.Integer(),
                  sa.ForeignKey("results.id", ondelete="CASCADE"), nullable=True),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("engine_a", sa.String(length=100), nullable=False),
        sa.Column("engine_b", sa.String(length=100), nullable=False),
        sa.Column("classif_a", sa.String(length=200), nullable=True),
        sa.Column("classif_b", sa.String(length=200), nullable=True),
        sa.Column("winner", sa.String(length=4), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_judge_verdicts_comparison_run_id", "judge_verdicts", ["comparison_run_id"])


def downgrade() -> None:
    op.drop_index("ix_judge_verdicts_comparison_run_id", table_name="judge_verdicts")
    op.drop_table("judge_verdicts")
