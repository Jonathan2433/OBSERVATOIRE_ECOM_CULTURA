"""journal d'audit + configuration applicative

Revision ID: 0005_audit_config
Revises: 0004_review_corrections
Create Date: 2026-06-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_audit_config"
down_revision = "0004_review_corrections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(length=150), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity", sa.String(length=50), nullable=True),
        sa.Column("entity_id", sa.String(length=50), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])

    op.create_table(
        "app_config",
        sa.Column("key", sa.String(length=80), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("app_config")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_table("audit_log")
