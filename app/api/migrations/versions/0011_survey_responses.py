"""réponses de questionnaire et rattachement des verbatims

Revision ID: 0011_survey_responses
Revises: 0010_result_satisfaction
Create Date: 2026-09-16

La migration ne rétro-déduit aucune donnée. Les anciens ``results`` conservent
un ``survey_response_id`` NULL : leur note native, leur répondant et leur statut
client sont indisponibles jusqu'à un retraitement explicite des fichiers source.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_survey_responses"
down_revision = "0010_result_satisfaction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "survey_responses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_file", sa.String(length=255), nullable=False),
        sa.Column("respondent_key", sa.String(length=64), nullable=False),
        sa.Column("satisfaction_native", sa.Integer(), nullable=True),
        sa.Column("satisfaction_scale_max", sa.Integer(), nullable=False),
        sa.Column("satisfaction_normalized", sa.Integer(), nullable=True),
        sa.Column("rating_invalid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("client_status", sa.String(length=20), nullable=False,
                  server_default="non_renseigne"),
        sa.CheckConstraint(
            "client_status IN ('ancien', 'nouveau', 'non_renseigne')",
            name="ck_survey_responses_client_status"),
        sa.CheckConstraint(
            "satisfaction_scale_max IN (4, 5)",
            name="ck_survey_responses_scale_max"),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "source_type", "source_file", "respondent_key",
                            name="uq_survey_response_scope"),
    )
    op.create_index("ix_survey_responses_batch_id", "survey_responses", ["batch_id"])
    op.create_index("ix_survey_responses_source_type", "survey_responses", ["source_type"])
    op.create_index("ix_survey_responses_client_status", "survey_responses", ["client_status"])
    op.add_column("results", sa.Column("survey_response_id", sa.Integer(), nullable=True))
    op.create_index("ix_results_survey_response_id", "results", ["survey_response_id"])
    op.create_foreign_key(
        "fk_results_survey_response_id", "results", "survey_responses",
        ["survey_response_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    op.drop_constraint("fk_results_survey_response_id", "results", type_="foreignkey")
    op.drop_index("ix_results_survey_response_id", table_name="results")
    op.drop_column("results", "survey_response_id")
    op.drop_index("ix_survey_responses_client_status", table_name="survey_responses")
    op.drop_index("ix_survey_responses_source_type", table_name="survey_responses")
    op.drop_index("ix_survey_responses_batch_id", table_name="survey_responses")
    op.drop_table("survey_responses")
