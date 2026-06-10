"""Database session management.

Provides an engine and session factory. For production: Postgres. For tests: SQLite.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlmodel import SQLModel

from app.config import settings

_engine = None
_SessionLocal = None


def _normalize_db_url(url: str) -> str:
    """Ensure psycopg3 driver prefix and SSL for Render.

    Render gives postgresql:// but SQLAlchemy needs the psycopg3 driver prefix.
    Force psycopg3 so we don't need the psycopg2 package.
    """
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    if "render.com" in url and "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url = url + sep + "sslmode=require"
    return url


def get_engine(url: str | None = None):
    """Get or create the SQLAlchemy engine. Pass a custom URL for testing."""
    global _engine
    if url is not None:
        # Connection pool settings for Render free tier (single Postgres connection).
        # Increase pool_size and max_overflow when upgrading to a paid Render plan.
        _engine = create_engine(
            _normalize_db_url(url),
            echo=False,
            pool_size=2,
            max_overflow=2,
            pool_recycle=300,
            pool_pre_ping=True,
        )
        return _engine
    if _engine is None:
        # Connection pool settings for Render free tier (single Postgres connection).
        # Increase pool_size and max_overflow when upgrading to a paid Render plan.
        _engine = create_engine(
            _normalize_db_url(settings.database_url),
            echo=False,
            pool_size=2,
            max_overflow=2,
            pool_recycle=300,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory(url: str | None = None) -> sessionmaker[Session]:
    """Get or create the session factory."""
    global _SessionLocal
    if url is not None:
        engine = get_engine(url)
        _SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
        return _SessionLocal
    if _SessionLocal is None:
        engine = get_engine()
        _SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    return _SessionLocal


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency for DB sessions."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def init_db(url: str | None = None) -> None:
    """Create all tables. Used for tests and initial setup."""
    import app.models  # noqa: F401  — register models with SQLModel.metadata
    engine = get_engine(url)
    SQLModel.metadata.create_all(engine)

