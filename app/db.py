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

    Render may give postgres:// or postgresql:// — SQLAlchemy needs the
    psycopg3 driver prefix.  Force psycopg3 so we don't need the psycopg2 package.
    """
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    if "render.com" in url and "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url = url + sep + "sslmode=require"
    return url


def _is_sqlite(url: str) -> bool:
    """SQLite uses StaticPool/SingletonThreadPool — it doesn't accept pool_size,
    max_overflow, pool_recycle, or pool_pre_ping. The app must skip those kwargs
    when running against an in-memory or file SQLite (i.e. tests)."""
    return url.startswith("sqlite")


def _pool_kwargs(url: str) -> dict:
    """Postgres pool tuning for Render free tier. SQLite opts out — see _is_sqlite."""
    if _is_sqlite(url):
        return {}
    return {
        "pool_size": 2,
        "max_overflow": 2,
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }


def get_engine(url: str | None = None):
    """Get or create the SQLAlchemy engine. Pass a custom URL for testing."""
    global _engine
    target_url = url if url is not None else settings.database_url
    if url is not None:
        # Caller-provided URL (tests): always rebuild the engine so we don't
        # reuse a stale engine bound to a different DB.
        _engine = create_engine(
            _normalize_db_url(url),
            echo=False,
            **_pool_kwargs(url),
        )
        return _engine
    if _engine is None:
        # App-level engine: built once from settings, reused for the process lifetime.
        _engine = create_engine(
            _normalize_db_url(target_url),
            echo=False,
            **_pool_kwargs(target_url),
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

