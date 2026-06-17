"""Environnement Alembic — migrations de la base Observatoire Ecom Studio.

L'URL de connexion provient de l'environnement (DATABASE_URL), comme le reste
de la configuration. Les modèles ORM (ajoutés au fil des lots) sont importés
ici afin qu'``--autogenerate`` détecte les changements de schéma.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.db import Base  # noqa: E402

# Import des modèles pour peupler Base.metadata (autogenerate).
# À compléter au fil des lots, ex. :  from app.models import user, batch  # noqa
try:  # pragma: no cover - import optionnel tant qu'aucun modèle n'existe
    import app.models  # noqa: F401
except ModuleNotFoundError:
    pass

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Surcharge de l'URL avec la variable d'environnement.
db_url = os.environ.get("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
