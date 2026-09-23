"""note de satisfaction persistée sur le résultat (results.satisfaction)

Revision ID: 0010_result_satisfaction
Revises: 0009_taxonomy_entries
Create Date: 2026-09-15

La note de satisfaction alimentait déjà le modèle (préfixe [SATISFACTION x/4])
mais n'était conservée nulle part : les lots au format Cultura 2026 ne gardent
que les colonnes de la liste blanche, toutes techniques (``__*__``), et celle-ci
étaient écartées de ``original_columns``. Sans colonne dédiée, aucun indicateur
de satisfaction n'est calculable — seul le signal d'insatisfaction forte
l'était, ce qui ne dit rien des clients satisfaits.

Colonne NULLABLE et non rétro-remplie : les lots déjà traités n'ont pas
conservé la note, elle y reste ``NULL`` (« non renseignée », jamais « zéro »).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_result_satisfaction"
down_revision = "0009_taxonomy_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("results", sa.Column("satisfaction", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("results", "satisfaction")
