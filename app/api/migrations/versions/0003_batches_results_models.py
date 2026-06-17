"""tables batches, results, model_versions

Revision ID: 0003_batches_results_models
Revises: 0002_users
Create Date: 2026-06-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_batches_results_models"
down_revision = "0002_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("label", name="uq_model_versions_label"),
    )
    op.create_index("ix_model_versions_is_active", "model_versions", ["is_active"])

    op.create_table(
        "batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_label", sa.String(length=100), nullable=True),
        sa.Column("seuil_revue", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("n_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_review", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_files", sa.JSON(), nullable=True),
        sa.Column("pii_masked", sa.JSON(), nullable=True),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_batches_status", "batches", ["status"])

    op.create_table(
        "results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=True),
        sa.Column("verbatim_analyse", sa.Text(), nullable=True),
        sa.Column("nb_themes", sa.Integer(), nullable=True),
        sa.Column("theme1_niv1", sa.String(length=120), nullable=True),
        sa.Column("theme1_niv2", sa.String(length=120), nullable=True),
        sa.Column("theme1_sentiment", sa.String(length=20), nullable=True),
        sa.Column("theme1_score", sa.Float(), nullable=True),
        sa.Column("theme2_niv1", sa.String(length=120), nullable=True),
        sa.Column("theme2_niv2", sa.String(length=120), nullable=True),
        sa.Column("theme2_sentiment", sa.String(length=20), nullable=True),
        sa.Column("theme2_score", sa.Float(), nullable=True),
        sa.Column("signal_rupture", sa.Boolean(), server_default=sa.false()),
        sa.Column("signal_churn", sa.Boolean(), server_default=sa.false()),
        sa.Column("signal_insatisfaction", sa.Boolean(), server_default=sa.false()),
        sa.Column("confidence_globale", sa.Float(), nullable=True),
        sa.Column("revue_requise", sa.Boolean(), server_default=sa.false()),
        sa.Column("corrected", sa.Boolean(), server_default=sa.false()),
        sa.Column("original_columns", sa.JSON(), nullable=True),
    )
    op.create_index("ix_results_batch_id", "results", ["batch_id"])
    op.create_index("ix_results_revue_requise", "results", ["revue_requise"])


def downgrade() -> None:
    op.drop_table("results")
    op.drop_table("batches")
    op.drop_index("ix_model_versions_is_active", table_name="model_versions")
    op.drop_table("model_versions")
