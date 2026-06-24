"""cascade V5 : engine_predictions + colonnes batches (refiner_label, chain_disagreements)

Revision ID: 0006_cascade_engine_predictions
Revises: 0005_audit_config
Create Date: 2026-06-24

Additif et rétrocompatible : un lot existant a refiner_label = NULL et se comporte
exactement comme en V4. La table engine_predictions sert la cascade (rôles
proposer/refiner) dès C3 et sera réutilisée par la comparaison (rôle compare) en C4 ;
``comparison_run_id`` est créée nullable sans contrainte FK (la table comparison_runs
arrive au lot C4). cf. docs/SPEC_V5_MULTI_MOTEUR §4.3.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_cascade_engine_predictions"
down_revision = "0005_audit_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("batches", sa.Column("refiner_label", sa.String(length=100), nullable=True))
    op.add_column("batches", sa.Column("chain_disagreements", sa.Integer(), nullable=True))

    op.create_table(
        "engine_predictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(),
                  sa.ForeignKey("batches.id", ondelete="CASCADE"), nullable=True),
        sa.Column("comparison_run_id", sa.Integer(), nullable=True),   # FK ajoutée en C4
        sa.Column("result_id", sa.Integer(),
                  sa.ForeignKey("results.id", ondelete="CASCADE"), nullable=True),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("engine_label", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=12), nullable=False),
        sa.Column("theme1_niv1", sa.String(length=120), nullable=True),
        sa.Column("theme1_niv2", sa.String(length=120), nullable=True),
        sa.Column("theme1_sentiment", sa.String(length=20), nullable=True),
        sa.Column("confidence_globale", sa.Float(), nullable=True),
        sa.Column("signal_rupture", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("signal_churn", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("signal_insatisfaction", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_engine_predictions_batch_id", "engine_predictions", ["batch_id"])
    op.create_index("ix_engine_predictions_comparison_run_id", "engine_predictions", ["comparison_run_id"])
    op.create_index("ix_engine_predictions_result_id", "engine_predictions", ["result_id"])


def downgrade() -> None:
    op.drop_index("ix_engine_predictions_result_id", table_name="engine_predictions")
    op.drop_index("ix_engine_predictions_comparison_run_id", table_name="engine_predictions")
    op.drop_index("ix_engine_predictions_batch_id", table_name="engine_predictions")
    op.drop_table("engine_predictions")
    op.drop_column("batches", "chain_disagreements")
    op.drop_column("batches", "refiner_label")
