"""Shared pytest fixtures: paths, demo config, DB session, and fakes for Twilio/Claude/clock.

No test may hit a real external service. Use these fakes; assert on recorded calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def make_auth_cookies(dealer_slug: str = "smoke-test") -> dict:
    """Generate a valid session cookie dict for test requests."""
    import time
    from app.dashboard import _get_serializer
    serializer = _get_serializer()
    token = serializer.dumps({"user": "admin", "role": "dealer", "dealer_slug": dealer_slug, "ts": time.time()})
    return {"session": token}


@pytest.fixture
def root() -> Path:
    return ROOT


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def demo_config_path() -> Path:
    return FIXTURES / "demo-dealer.yaml"


@pytest.fixture
def db_engine():
    """In-memory SQLite engine for tests. Each test gets a clean schema."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Session:
    """A SQLAlchemy session bound to the in-memory SQLite engine."""
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = TestSession()
    yield session
    session.close()


class FakeTwilio:
    """Records outbound messages instead of sending. Inject in place of the Twilio client."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send(self, **kwargs) -> str:
        sid = f"SM_fake_{len(self.sent):032d}"
        self.sent.append({"sid": sid, **kwargs})
        return sid


class FakeLLM:
    """Returns scripted turns/tool-calls. Conversation tests assert handling, not wording."""

    def __init__(self, script: list[dict] | None = None) -> None:
        self.script = list(script or [])
        self.calls: list[dict] = []

    def respond(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return self.script.pop(0) if self.script else {"type": "text", "text": "(no script)"}


@pytest.fixture
def fake_twilio() -> FakeTwilio:
    return FakeTwilio()


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def frozen_now():
    """A fixed 'now' for deterministic quiet-hours / business-hours / escalation tests."""
    return datetime(2026, 6, 4, 17, 0, tzinfo=timezone.utc)  # Thu 10:00 America/Vancouver


@pytest.fixture
def auth_cookies() -> dict:
    """Cookie dict that satisfies the dashboard auth dependency."""
    return make_auth_cookies()
