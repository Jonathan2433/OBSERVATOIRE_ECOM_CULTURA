"""comparaison V5 : table comparison_runs + FK engine_predictions.comparison_run_id

Revision ID: 0007_comparison_runs
Revises: 0006_cascade_engine_predictions
Create Date: 2026-06-24

Additif. La colonne ``engine_predictions.comparison_run_id`` (créée nullable sans
contrainte en 0006) reçoit ici sa clé étrangère vers ``comparison_runs``.
cf. docs/SPEC_V5_MULTI_MOTEUR §4.3 / §7.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_comparison_runs"
down_revision = "0006_cascade_engine_predictions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "comparison_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(),
                  sa.ForeignKey("batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("engine_labels", sa.JSON(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("seed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("judge_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_comparison_runs_batch_id", "comparison_runs", ["batch_id"])
    op.create_index("ix_comparison_runs_status", "comparison_runs", ["status"])

    # La colonne existe déjà (0006) ; on ajoute la contrainte FK maintenant que la table existe.
    op.create_foreign_key(
        "fk_engine_predictions_comparison_run", "engine_predictions",
        "comparison_runs", ["comparison_run_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    op.drop_constraint("fk_engine_predictions_comparison_run", "engine_predictions", type_="foreignkey")
    op.drop_index("ix_comparison_runs_status", table_name="comparison_runs")
    op.drop_index("ix_comparison_runs_batch_id", table_name="comparison_runs")
    op.drop_table("comparison_runs")
