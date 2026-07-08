"""Alembic env.py — reads DATABASE_URL from environment (same as app/db.py).

Autogenerate support: imports SQLModel metadata so Alembic can detect schema changes.
Handles SQLite vs Postgres differences (e.g. batch mode for ALTER TABLE on SQLite).
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Import all models so SQLModel.metadata is populated for autogenerate.
import app.models  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _get_database_url() -> str:
    """Resolve database URL from environment, matching app/db.py logic."""
    # 1. Explicit DATABASE_URL env var (Render, Docker, .env)
    url = os.getenv("DATABASE_URL")
    if url:
        return _normalize_db_url(url)
    # 2. Fall back to app settings (reads .env file)
    from app.config import settings
    return _normalize_db_url(settings.database_url)


def _normalize_db_url(url: str) -> str:
    """Ensure psycopg3 driver prefix and SSL for Render (mirrors app/db.py)."""
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    if "render.com" in url and "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url = url + sep + "sslmode=require"
    return url


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine.
    """
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Enable batch mode for SQLite (ALTER TABLE workaround)
        render_as_batch=_is_sqlite(url),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    url = _get_database_url()

    # Override the sqlalchemy.url in the config with our resolved URL.
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
            # Enable batch mode for SQLite (ALTER TABLE workaround)
            render_as_batch=_is_sqlite(url),
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
