"""1.4: WhatsApp inbound webhook integration tests.

The handler at POST /webhook/twilio/whatsapp processes inbound WhatsApp
messages from reps (claim "1", pass "2") and customers.

These tests use FastAPI TestClient. The webhook handler calls
_get_session() -> get_session_factory() -> _SessionLocal. We monkeypatch
_SessionLocal to point at the test's in-memory SQLite so all DB reads/writes
go to the test DB.

Signature validation uses real HMAC-SHA1 signing via make_signed_twilio_request
from conftest.py (same approach as test_webhook_security.py).
"""
from __future__ import annotations

import hashlib
import hmac
import os

# MUST set TWILIO_AUTH_TOKEN before importing app modules (Pydantic caches on load).
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token-for-signature-validation")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC_TEST_FAKE")
os.environ.setdefault("REQUIRE_TWILIO_SIGNATURE", "true")

from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from twilio.request_validator import RequestValidator

from app.models import Channel, Dealer, Direction, Lead, LeadState, Message


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def wa_engine():
    """Dedicated in-memory SQLite engine with all tables."""
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
def wa_session(wa_engine):
    Session = sessionmaker(bind=wa_engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def wa_factory(wa_engine, monkeypatch):
    """Patch _SessionLocal so _get_session() returns a session bound to
    the test's in-memory SQLite."""
    import app.db as db_module
    factory = sessionmaker(bind=wa_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "_SessionLocal", factory)
    return factory


@pytest.fixture
def wa_client(wa_factory):
    """TestClient with DB pointing at the test's in-memory SQLite.

    Signature validation uses real HMAC-SHA1 signing.
    """
    from app.main import app
    return TestClient(app)


def _signed_wa_post(client, *, from_number, to_number, body, message_sid=None):
    """POST to /webhook/twilio/whatsapp with a properly signed Twilio request.

    Uses RequestValidator.compute_signature() — the same signing logic the
    handler uses to validate. This avoids the mismatch between raw HMAC
    and Twilio's canonical form encoding.
    """
    payload = {
        "From": from_number,
        "To": to_number,
        "Body": body,
        "MessageSid": message_sid or f"SM_wa_{hash(body + from_number) % 10**8:08d}",
        "NumMedia": "0",
    }
    uri = "http://testserver/webhook/twilio/whatsapp"
    validator = RequestValidator("test-twilio-secret")
    sig = validator.compute_signature(uri, payload)
    headers = {"X-Twilio-Signature": sig}
    return client.post("/webhook/twilio/whatsapp", data=payload, headers=headers)


# ---------------------------------------------------------------------------
# Data setup helpers
# ---------------------------------------------------------------------------

def _seed_dealer(session, *, whatsapp_sender="+141****8886", reps=None):
    """Insert a dealer with WhatsApp config and sales team."""
    if reps is None:
        reps = [
            {
                "name": "Mike",
                "phone": "+160****4001",
                "active": True,
                "notify_backend": "twilio_whatsapp",
            },
            {
                "name": "Dana",
                "phone": "+160****4002",
                "active": True,
                "notify_backend": "sms",
            },
        ]
    config = {
        "dealer": {"name": "WA Test Dealer", "timezone": "America/Vancouver"},
        "channels": {
            "sms_number": "+177****0099",
            "whatsapp_sender": whatsapp_sender,
        },
        "sales_team": reps,
        "claim_timeout_min": 5,
    }
    dealer = Dealer(
        slug="wa-test",
        name="WA Test Dealer",
        sms_number="+177****0099",
        whatsapp_sender=whatsapp_sender,
        config=config,
    )
    session.add(dealer)
    session.commit()
    session.refresh(dealer)
    return dealer


def _seed_lead(session, dealer, *, state=LeadState.ASSIGNED, assigned_rep="Mike",
               name="Test Customer", phone="+160****4999"):
    """Insert a lead in the given state."""
    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.SMS,
        name=name,
        phone=phone,
        state=state,
        assigned_rep=assigned_rep,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return lead


# ---------------------------------------------------------------------------
# Tests: rep claim (reply "1")
# ---------------------------------------------------------------------------

def test_rep_reply_1_claims_lead(wa_session, wa_client, monkeypatch):
    """Rep sends "1" -> lead transitions to CLAIMED."""
    monkeypatch.setattr(
        "tools.notify_rep.notify_rep",
        lambda *a, **kw: type("R", (), {
            "success": True, "backend": "dry_run",
            "message_sid": None, "dry_run": True, "error": None,
        })(),
    )
    dealer = _seed_dealer(wa_session)
    lead = _seed_lead(wa_session, dealer, state=LeadState.ASSIGNED, assigned_rep="Mike")

    resp = _signed_wa_post(
        wa_client,
        from_number="whatsapp:+160****4001",
        to_number="whatsapp:+141****8886",
        body="1",
    )

    assert resp.status_code == 200
    assert "claimed" in resp.text.lower() or "Lead claimed" in resp.text

    wa_session.expire_all()
    lead_after = wa_session.get(Lead, lead.id)
    assert lead_after.state == LeadState.CLAIMED


def test_rep_reply_1_persists_inbound_message(wa_session, wa_client, monkeypatch):
    """The inbound WhatsApp message is logged as a Message row."""
    monkeypatch.setattr(
        "tools.notify_rep.notify_rep",
        lambda *a, **kw: type("R", (), {
            "success": True, "backend": "dry_run",
            "message_sid": None, "dry_run": True, "error": None,
        })(),
    )
    dealer = _seed_dealer(wa_session)
    lead = _seed_lead(wa_session, dealer, state=LeadState.ASSIGNED, assigned_rep="Mike")

    _signed_wa_post(
        wa_client,
        from_number="whatsapp:+160****4001",
        to_number="whatsapp:+141****8886",
        body="1",
        message_sid="SM_wa_unique_001",
    )

    inbound = (
        wa_session.query(Message)
        .filter(Message.lead_id == lead.id, Message.direction == Direction.INBOUND)
        .first()
    )
    assert inbound is not None
    assert inbound.body == "1"
    assert inbound.channel == Channel.WHATSAPP


# ---------------------------------------------------------------------------
# Tests: rep pass (reply "2")
# ---------------------------------------------------------------------------

def test_rep_reply_2_passes_lead(wa_session, wa_client, monkeypatch):
    """Rep sends "2" -> lead is passed to the next rep (Dana)."""
    monkeypatch.setattr(
        "tools.notify_rep.notify_rep",
        lambda *a, **kw: type("R", (), {
            "success": True, "backend": "dry_run",
            "message_sid": None, "dry_run": True, "error": None,
        })(),
    )
    dealer = _seed_dealer(wa_session)
    # Advance round_robin_pointer so next_rep picks Dana (index 1)
    dealer.round_robin_pointer = 1
    wa_session.commit()
    lead = _seed_lead(wa_session, dealer, state=LeadState.ASSIGNED, assigned_rep="Mike")

    resp = _signed_wa_post(
        wa_client,
        from_number="whatsapp:+160****4001",
        to_number="whatsapp:+141****8886",
        body="2",
    )

    assert resp.status_code == 200
    assert "passed" in resp.text.lower()

    # Query via the same session the handler uses (the patched _SessionLocal)
    from app.db import get_session_factory
    factory = get_session_factory()
    with factory() as s:
        lead_after = s.get(Lead, lead.id)
        assert lead_after.assigned_rep != "Mike", (
            f"Lead should have been passed to a different rep, still assigned to Mike"
        )


# ---------------------------------------------------------------------------
# Tests: unknown reply
# ---------------------------------------------------------------------------

def test_rep_unknown_reply_returns_hint(wa_session, wa_client, monkeypatch):
    """Rep sends anything other than "1" or "2" -> instructional response."""
    monkeypatch.setattr(
        "tools.notify_rep.notify_rep",
        lambda *a, **kw: type("R", (), {
            "success": True, "backend": "dry_run",
            "message_sid": None, "dry_run": True, "error": None,
        })(),
    )
    dealer = _seed_dealer(wa_session)
    _seed_lead(wa_session, dealer, state=LeadState.ASSIGNED, assigned_rep="Mike")

    resp = _signed_wa_post(
        wa_client,
        from_number="whatsapp:+160****4001",
        to_number="whatsapp:+141****8886",
        body="yes I want it",
    )

    assert resp.status_code == 200
    assert "Reply 1" in resp.text


# ---------------------------------------------------------------------------
# Tests: unknown rep
# ---------------------------------------------------------------------------

def test_unknown_rep_returns_empty_twiml(wa_session, wa_client):
    """A WhatsApp from an unknown number -> empty TwiML (no-op)."""
    dealer = _seed_dealer(wa_session)
    _seed_lead(wa_session, dealer, state=LeadState.ASSIGNED, assigned_rep="Mike")

    resp = _signed_wa_post(
        wa_client,
        from_number="whatsapp:+199****0000",
        to_number="whatsapp:+141****8886",
        body="1",
    )

    assert resp.status_code == 200
    assert "<Response></Response>" in resp.text


# ---------------------------------------------------------------------------
# Tests: no pending leads
# ---------------------------------------------------------------------------

def test_rep_reply_when_no_pending_leads(wa_session, wa_client):
    """Rep sends "1" but no ASSIGNED/ESCALATED leads -> "No pending leads"."""
    dealer = _seed_dealer(wa_session)
    _seed_lead(wa_session, dealer, state=LeadState.CLAIMED, assigned_rep="Mike")

    resp = _signed_wa_post(
        wa_client,
        from_number="whatsapp:+160****4001",
        to_number="whatsapp:+141****8886",
        body="1",
    )

    assert resp.status_code == 200
    assert "No pending" in resp.text


# ---------------------------------------------------------------------------
# Tests: customer-initiated WhatsApp
# ---------------------------------------------------------------------------

def test_customer_initiated_whatsapp_returns_empty_twiml(wa_session, wa_client):
    """Customer sends a WhatsApp (not a rep number) -> empty TwiML (no rep fallback).
    
    The WhatsApp test mode handler has been removed. Non-rep WhatsApp
    messages should receive empty TwiML — no AI response, no lead creation.
    Customers should use SMS for new conversations.
    """
    dealer = _seed_dealer(wa_session)

    resp = _signed_wa_post(
        wa_client,
        from_number="whatsapp:+199****9999",
        to_number="whatsapp:+141****8886",
        body="Hi, I'm looking for a Honda Civic",
    )

    assert resp.status_code == 200
    assert "<Response></Response>" in resp.text


# ---------------------------------------------------------------------------
# Tests: idempotency
# ---------------------------------------------------------------------------

def test_duplicate_webhook_is_idempotent(wa_session, wa_client, monkeypatch):
    """Sending the same MessageSid twice -> second is a no-op."""
    monkeypatch.setattr(
        "tools.notify_rep.notify_rep",
        lambda *a, **kw: type("R", (), {
            "success": True, "backend": "dry_run",
            "message_sid": None, "dry_run": True, "error": None,
        })(),
    )
    dealer = _seed_dealer(wa_session)
    _seed_lead(wa_session, dealer, state=LeadState.ASSIGNED, assigned_rep="Mike")

    resp1 = _signed_wa_post(
        wa_client,
        from_number="whatsapp:+160****4001",
        to_number="whatsapp:+141****8886",
        body="1",
        message_sid="SM_idempotent_test_001",
    )
    assert resp1.status_code == 200

    resp2 = _signed_wa_post(
        wa_client,
        from_number="whatsapp:+160****4001",
        to_number="whatsapp:+141****8886",
        body="1",
        message_sid="SM_idempotent_test_001",
    )
    assert resp2.status_code == 200
    assert "<Response></Response>" in resp2.text


# ---------------------------------------------------------------------------
# Tests: wrong dealer WhatsApp number
# ---------------------------------------------------------------------------

def test_unknown_whatsapp_sender_returns_empty(wa_session, wa_client):
    """WhatsApp sent to a number not associated with any dealer -> empty TwiML."""
    dealer = _seed_dealer(wa_session, whatsapp_sender="+141****8886")
    _seed_lead(wa_session, dealer)

    resp = _signed_wa_post(
        wa_client,
        from_number="whatsapp:+160****4001",
        to_number="whatsapp:+199****0000",
        body="1",
    )

    assert resp.status_code == 200
    assert "<Response></Response>" in resp.text
