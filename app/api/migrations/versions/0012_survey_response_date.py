"""date métier des réponses pour les comparaisons inter-lots

Revision ID: 0012_survey_response_date
Revises: 0011_survey_responses
Create Date: 2026-09-17

La date de création d'un lot est une date technique d'upload. Elle ne doit pas
servir à comparer deux périodes métier. Les lignes historiques restent NULL :
aucune période n'est inventée lorsque le fichier source n'a pas été retraité.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_survey_response_date"
down_revision = "0011_survey_responses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("survey_responses", sa.Column("response_date", sa.Date(), nullable=True))
    op.create_index(
        "ix_survey_responses_batch_source_date",
        "survey_responses",
        ["batch_id", "source_type", "response_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_survey_responses_batch_source_date", table_name="survey_responses")
    op.drop_column("survey_responses", "response_date")
