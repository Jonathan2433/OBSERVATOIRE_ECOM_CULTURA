"""index transversal des analyses par date et source

Revision ID: 0013_analysis_source_date_index
Revises: 0012_survey_response_date
Create Date: 2026-09-17
"""
from __future__ import annotations

from alembic import op

revision = "0013_analysis_source_date_index"
down_revision = "0012_survey_response_date"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_survey_responses_date_source_batch",
        "survey_responses",
        ["response_date", "source_type", "batch_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_survey_responses_date_source_batch",
        table_name="survey_responses",
    )
