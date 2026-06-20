"""Alembic env.py configured for Speed to Lead v5.

Uses DATABASE_URL from app.config.settings (same as the app at runtime).
SQLModel metadata is auto-discovered via importing app.models.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlmodel import SQLModel

from alembic import context

# Alembic Config object
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import ALL models so SQLModel.metadata discovers them
import app.models  # noqa: F401

# Target metadata for autogenerate
target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generate SQL without a DB connection)."""
    from app.config import settings as app_settings
    from app.db import _normalize_db_url

    url = _normalize_db_url(app_settings.database_url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database using the app's DATABASE_URL."""
    from app.config import settings as app_settings
    from app.db import _normalize_db_url

    url = _normalize_db_url(app_settings.database_url)
    # Override the ini-file URL with the app's runtime URL
    config.set_main_option("sqlalchemy.url", url)

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
