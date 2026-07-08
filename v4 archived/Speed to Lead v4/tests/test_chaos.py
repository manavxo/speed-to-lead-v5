"""Chaos / resilience tests — verify graceful degradation when external services fail.

The golden rule: "Inside the engine, degrade gracefully. Never crash the reply path."
These tests inject failures at the boundaries (bad payloads, missing data, invalid states)
and verify the app returns sensible responses instead of 500s.
"""

from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from app.models import Dealer
from tests.conftest import make_auth_cookies


def _make_dealer(db_engine, slug="chaos-dealer", token="chaos-token"):
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = TestSession()
    d = Dealer(
        slug=slug,
        name="Chaos Auto",
        config={
            "dealer": {"name": "Chaos Auto", "timezone": "America/Vancouver", "main_phone": "+16045550000"},
            "hours": {"mon": "09:00-19:00", "tue": "09:00-19:00", "wed": "09:00-19:00",
                      "thu": "09:00-19:00", "fri": "09:00-19:00", "sat": "10:00-17:00"},
            "channels": {
                "web_form_token": token,
                "sms_number": "+17785550222",
                "whatsapp_sender": "+17785550223",
            },
            "sales_team": [
                {"name": "Alex", "phone": "+16045550301", "active": True},
                {"name": "Jordan", "phone": "+16045550302", "active": True},
            ],
            "compliance": {"opt_out_keywords": ["STOP", "ARRET"], "quiet_hours": "21:00-08:00"},
            "routing": {"strategy": "round_robin", "claim_timeout_min": 5},
            "ai": {"persona": "friendly local rep", "goal": "book_appointment"},
        },
    )
    session.add(d)
    session.commit()
    session.refresh(d)
    session.close()
    return d


def _make_client(db_engine, monkeypatch):
    import app.db as db_module
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "_SessionLocal", TestSession)
    monkeypatch.setattr(db_module, "_engine", db_engine)
    monkeypatch.setattr(db_module, "init_db", lambda url=None: None)
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


# ---- Boundary: bad / missing payloads ----


def test_empty_webform_body(db_engine, monkeypatch):
    """Empty JSON body should not crash — returns an error gracefully."""
    _make_dealer(db_engine)
    c = _make_client(db_engine, monkeypatch)
    resp = c.post("/webhook/form/chaos-token", json={})
    # Should not 500 — either succeeds with empty fields or returns a clean error
    assert resp.status_code == 200
    data = resp.json()
    # Should indicate some result (ok or error, but not crash)
    assert "status" in data or "error" in data


def test_malformed_json_webform(db_engine, monkeypatch):
    """Completely wrong content-type should not crash."""
    _make_dealer(db_engine)
    c = _make_client(db_engine, monkeypatch)
    resp = c.post(
        "/webhook/form/chaos-token",
        content=b"this is not json",
        headers={"Content-Type": "application/json"},
    )
    # Should return a clean error, not a 500
    assert resp.status_code in (200, 400, 422)


def test_unknown_dealer_token(db_engine, monkeypatch):
    """Webhook with unknown token should return clean error, not crash."""
    _make_dealer(db_engine)
    c = _make_client(db_engine, monkeypatch)
    resp = c.post("/webhook/form/TOTALLY-INVALID-TOKEN", json={
        "full_name": "Ghost Lead",
        "phone": "(604) 555-0000",
        "consent_sms": True,
    })
    assert resp.status_code == 200
    assert "error" in resp.json()


def test_sms_from_unknown_number(db_engine, monkeypatch):
    """SMS from a number not matching any dealer should return empty TwiML, not crash."""
    _make_dealer(db_engine)
    c = _make_client(db_engine, monkeypatch)
    resp = c.post("/webhook/twilio/sms", data={
        "From": "+19999999999",
        "To": "+10000000000",  # No dealer owns this number
        "Body": "Hello?",
    })
    assert resp.status_code == 200
    # Should be empty TwiML (no message sent)
    assert "<Response></Response>" in resp.text


def test_whatsapp_from_unknown_rep(db_engine, monkeypatch):
    """WhatsApp from a number not in sales_team should return empty TwiML."""
    _make_dealer(db_engine)
    c = _make_client(db_engine, monkeypatch)
    resp = c.post("/webhook/twilio/whatsapp", data={
        "From": "whatsapp:+19999999999",
        "To": "whatsapp:+17785550223",
        "Body": "1",
    })
    assert resp.status_code == 200
    assert "<Response></Response>" in resp.text


def test_whatsapp_claim_with_no_assigned_lead(db_engine, monkeypatch):
    """Rep claims when there's no pending lead — should return friendly message."""
    _make_dealer(db_engine)
    c = _make_client(db_engine, monkeypatch)
    resp = c.post("/webhook/twilio/whatsapp", data={
        "From": "whatsapp:+16045550301",
        "To": "whatsapp:+17785550223",
        "Body": "1",
    })
    assert resp.status_code == 200
    assert "no pending" in resp.text.lower()


def test_sms_opt_out_without_lead(db_engine, monkeypatch):
    """STOP keyword when no lead exists — should still confirm unsubscribe."""
    _make_dealer(db_engine)
    c = _make_client(db_engine, monkeypatch)
    resp = c.post("/webhook/twilio/sms", data={
        "From": "+17785559999",
        "To": "+17785550222",
        "Body": "STOP",
    })
    assert resp.status_code == 200
    assert "unsubscribed" in resp.text.lower()


def test_voice_with_invalid_status(db_engine, monkeypatch):
    """Voice webhook with unexpected CallStatus should return empty TwiML."""
    _make_dealer(db_engine)
    c = _make_client(db_engine, monkeypatch)
    resp = c.post("/webhook/twilio/voice", data={
        "From": "+17785557777",
        "To": "+17785550222",
        "CallStatus": "ringing",  # Not handled — should not crash
    })
    assert resp.status_code == 200
    assert "<Response></Response>" in resp.text


# ---- State machine chaos ----


def test_duplicate_opt_out(db_engine, monkeypatch):
    """Opting out twice should not crash — idempotent."""
    _make_dealer(db_engine)
    c = _make_client(db_engine, monkeypatch)

    # Create a lead first
    c.post("/webhook/form/chaos-token", json={
        "full_name": "Double Stop",
        "phone": "(604) 555-7777",
        "consent_sms": True,
    })

    # Opt out twice
    resp1 = c.post("/webhook/twilio/sms", data={
        "From": "+17785557777",
        "To": "+17785550222",
        "Body": "STOP",
    })
    resp2 = c.post("/webhook/twilio/sms", data={
        "From": "+17785557777",
        "To": "+17785550222",
        "Body": "STOP",
    })

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert "unsubscribed" in resp1.text.lower()


# ---- Messenger (not implemented yet) ----


def test_messenger_not_implemented(db_engine, monkeypatch):
    """Messenger webhook should return a clean 'not_implemented' status."""
    _make_dealer(db_engine)
    c = _make_client(db_engine, monkeypatch)
    resp = c.post("/webhook/messenger", json={"event": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "not_implemented"


# ---- Dashboard under edge conditions ----


def test_dashboard_empty_database(db_engine, monkeypatch):
    """Dashboard should render with no dealers/leads — not crash."""
    c = _make_client(db_engine, monkeypatch)
    resp = c.get("/dashboard/leads", cookies=make_auth_cookies())
    assert resp.status_code == 200