"""Shared pytest fixtures: paths, demo config, DB session, and fakes for Twilio/Claude/clock.

No test may hit a real external service. Use these fakes; assert on recorded calls.
"""

from __future__ import annotations

# IMPORTANT: env vars must be set BEFORE app.* is imported (Settings reads them
# at module-import time). conftest.py is loaded before test_*.py by pytest, so
# these run before any test module imports `from app.main import ...`.
import os
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-twilio-secret")
os.environ.setdefault("OUTBOUND_ENABLED", "false")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("QUIET_HOURS_DISABLED", "true")
os.environ.setdefault("REQUIRE_TWILIO_SIGNATURE", "true")
# P0-11 test needs the conversation engine to actually call the LLM
# (not bail out with the "api key not set" early return).
os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter-key-not-real")

import hashlib
import hmac
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"

# Test-only Twilio auth token (must match the os.environ value above).
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]


def make_signed_twilio_request(
    uri: str,
    body: dict | None = None,
    secret: str = TWILIO_AUTH_TOKEN,
    signature: str | None = None,
) -> dict:
    """Build a properly-signed Twilio webhook request for testing.

    Twilio signs: HMAC-SHA1(secret, uri + sorted-form-params)
    Reference: https://www.twilio.com/docs/usage/webhooks/webhooks-security

    Pass `signature="garbage"` (or any non-matching value) to simulate a
    tampered/unsigned request. Pass `signature=""` to simulate a missing header.
    """
    body = body or {}
    if signature is None:
        # Real signature: HMAC-SHA1 of (uri + sorted form-params)
        body_str = urlencode(sorted(body.items()))
        data = (uri + body_str).encode("utf-8")
        signature = hmac.new(secret.encode("utf-8"), data, hashlib.sha1).hexdigest()
    return {
        "uri": uri,
        "body": body,
        "headers": {"X-Twilio-Signature": signature},
    }


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
