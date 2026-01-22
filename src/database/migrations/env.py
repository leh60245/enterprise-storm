"""Alembic environment configuration for database migrations.

This module is invoked by the Alembic command line script, and controls
the behavior of the migration environment. It provides configuration for
- setting SQLAlchemy logging
- connecting to the database
- running migrations online or offline

Alembic auto-detection of model metadata requires:
1. Base and all model classes imported here
2. target_metadata = Base.metadata set
"""

from __future__ import annotations

import logging
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.database.models.analysis_report import AnalysisReport
# ============================================================================
# CRITICAL: Import SQLAlchemy Base and ALL Models
# ============================================================================
# Without these imports, Alembic cannot detect the model metadata
# and will create migrations with missing tables/columns.
from src.database.models.base import Base
from src.database.models.company import Company
from src.database.models.generated_report import GeneratedReport
from src.database.models.source_material import SourceMaterial

# this is the Alembic Config object, which provides
# the values of the [alembic] section of the .ini file
# as Python dictionary for use within the config callbacks
# provided by the .sqlalchemy.migration Migrator.env.py template
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = (
        Path.cwd() / "src/database/migrations/alembic.ini"
    )

    context.configure(
        url=configuration.get("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Execute migrations against a database connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate
    a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section)

    # Get database URL from environment or config
    database_url = (
        configuration.get("sqlalchemy.url")
        or "postgresql+asyncpg://user:password@localhost/dbname"
    )

    configuration["sqlalchemy.url"] = database_url

    connectable: AsyncEngine = create_async_engine(
        database_url,
        poolclass=pool.NullPool,
        echo=False,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio

    asyncio.run(run_migrations_online())
