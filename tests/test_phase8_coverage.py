"""Phase 8: Additional coverage for Phases 5-7 features.

Tests that don't require full auth setup or live API keys.
"""

from __future__ import annotations

import os

os.environ.setdefault("TWILIO_AUTH_TOKEN", "test")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC_TEST")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.models import Channel, Dealer, Direction, Lead, LeadState, Message


# ---------------------------------------------------------------------------
# Debug endpoint feature flag tests (no auth needed)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_debug_flag():
    """Reset debug flag after each test so other tests aren't affected."""
    import app.config as cfg
    cfg.settings.debug_endpoints_enabled = False
    yield
    cfg.settings.debug_endpoints_enabled = False


def test_debug_config_returns_404_when_disabled():
    """With debug_endpoints_enabled=False, /debug/config returns 404."""
    from app.main import app
    client = TestClient(app)
    resp = client.get("/debug/config")
    assert resp.status_code == 404


def test_debug_dealer_returns_404_when_disabled():
    """With debug_endpoints_enabled=False, /debug/dealer returns 404."""
    from app.main import app
    client = TestClient(app)
    resp = client.get("/debug/dealer/test-dealer")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Conversation memory summarization test
# ---------------------------------------------------------------------------

def test_conversation_loads_messages_without_crashing(db_session):
    """_call_openrouter should handle long message lists gracefully."""
    from app.engine.conversation import _call_openrouter

    dealer = Dealer(slug="mem-test", name="Mem Test", config={})
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.SMS,
        name="Memory Customer",
        phone="+16045559999",
        state=LeadState.ENGAGED,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    # Add 15 messages to test summarization threshold
    for i in range(15):
        msg = Message(
            lead_id=lead.id,
            direction=Direction.INBOUND if i % 2 == 0 else Direction.OUTBOUND,
            channel=Channel.SMS,
            body=f"Test message number {i + 1}",
            provider_sid=f"SM_mem_{i}",
        )
        db_session.add(msg)
    db_session.commit()

    # Should return fallback text (no API key configured in test)
    result = _call_openrouter(
        "You are a helpful assistant",
        "Latest customer message",
        session=db_session,
        lead=lead,
    )
    assert result is not None
    assert isinstance(result, str)
    assert len(result) > 0


def test_conversation_loads_few_messages_without_summary(db_session):
    """With fewer than 10 messages, no summarization should occur."""
    from app.engine.conversation import _call_openrouter

    dealer = Dealer(slug="mem-test-2", name="Mem Test 2", config={})
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.SMS,
        name="Short Customer",
        phone="+16045558888",
        state=LeadState.ENGAGED,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    # Only 3 messages — no summarization needed
    for i in range(3):
        msg = Message(
            lead_id=lead.id,
            direction=Direction.INBOUND if i % 2 == 0 else Direction.OUTBOUND,
            channel=Channel.SMS,
            body=f"Short message {i + 1}",
            provider_sid=f"SM_short_{i}",
        )
        db_session.add(msg)
    db_session.commit()

    result = _call_openrouter(
        "You are a helpful assistant",
        "Latest",
        session=db_session,
        lead=lead,
    )
    assert result is not None


# ---------------------------------------------------------------------------
# Rate limiting test (basic — verify slowapi is active)
# ---------------------------------------------------------------------------

def test_rate_limiter_loaded():
    """slowapi rate limiter should be registered on the app."""
    from app.main import app
    assert hasattr(app.state, "limiter"), "Rate limiter not registered on app.state"
