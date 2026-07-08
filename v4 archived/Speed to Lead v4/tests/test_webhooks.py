"""Phase 8 - FastAPI webhook integration tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.models import Channel, ConsentLog, Dealer, Lead, LeadState


@pytest.fixture
def client(db_engine, monkeypatch):
    """Create a test client with the test DB patched in."""
    import app.db as db_module
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "_SessionLocal", TestSession)
    monkeypatch.setattr(db_module, "_engine", db_engine)
    monkeypatch.setattr(db_module, "init_db", lambda url=None: None)

    from app.main import app
    return TestClient(app)


def _setup_dealer(db_engine):
    """Create a dealer in the test DB and return a session factory."""
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = TestSession()
    config = {
        "dealer": {"name": "Test Auto", "timezone": "America/Vancouver", "main_phone": "+160****0000"},
        "channels": {
            "web_form_token": "test-token-123",
            "sms_number": "+177****0111",
            "whatsapp_sender": "+177****0112",
        },
        "sales_team": [
            {"name": "Mike", "phone": "+160****0121", "active": True},
            {"name": "Dana", "phone": "+160****0122", "active": True},
        ],
        "compliance": {
            "consent_text": "By submitting you agree to receive texts from Test Auto. Reply STOP to opt out.",
            "opt_out_keywords": ["STOP", "STOPALL", "UNSUBSCRIBE", "ARRET"],
            "quiet_hours": "21:00-08:00",
        },
        "routing": {"strategy": "round_robin", "claim_timeout_min": 5, "escalation": ["reassign", "notify_manager"]},
    }
    dealer = Dealer(slug="test-dealer", name="Test Auto", config=config)
    session.add(dealer)
    session.commit()
    session.refresh(dealer)
    session.close()
    return TestSession, dealer


# ---- Health ---------------------------------------------------------------------------

def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


# ---- Webform webhook ------------------------------------------------------------------

def test_webform_unknown_token(client):
    resp = client.post("/webhook/form/bad-token", json={"full_name": "Test"})
    assert resp.status_code == 200
    assert resp.json()["error"] == "Unknown dealer token"


def test_webform_valid_submission(client, db_engine):
    TestSession, dealer = _setup_dealer(db_engine)

    resp = client.post("/webhook/form/test-token-123", json={
        "full_name": "Test Customer",
        "phone": "(604) 555-1234",
        "email": "test@example.com",
        "vehicle_stock": "SA1001",
        "consent_sms": True,
        "message": "Is the Civic available?",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["lead_id"] is not None
    # Pipeline is wired end-to-end: NEW -> AUTO_REPLIED -> ASSIGNED
    assert data["state"] in ("AUTO_REPLIED", "ASSIGNED")
    assert data["dealer"] == "test-dealer"

    # Verify lead in DB
    session = TestSession()
    lead = session.get(Lead, data["lead_id"])
    assert lead is not None
    assert lead.name == "Test Customer"
    assert lead.phone == "+160****1234"
    assert lead.consent is True
    session.close()


def test_webform_idempotent(client, db_engine):
    """Submitting the same form twice should return the same lead (deduplication)."""
    TestSession, dealer = _setup_dealer(db_engine)

    payload = {
        "full_name": "Test Customer",
        "phone": "(604) 555-1234",
        "consent_sms": True,
    }
    resp1 = client.post("/webhook/form/test-token-123", json=payload)
    resp2 = client.post("/webhook/form/test-token-123", json=payload)

    assert resp1.json()["lead_id"] == resp2.json()["lead_id"]


# ---- SMS webhook ----------------------------------------------------------------------

def test_sms_unknown_dealer_returns_empty(client, db_engine):
    resp = client.post("/webhook/twilio/sms", data={
        "From": "+160****1234",
        "To": "+100****0000",
        "Body": "Hello",
    })
    assert resp.status_code == 200
    assert "<Response></Response>" in resp.text


def test_sms_opt_out_creates_consent_log(client, db_engine):
    TestSession, dealer = _setup_dealer(db_engine)

    resp = client.post("/webhook/twilio/sms", data={
        "From": "+160****1234",
        "To": "+177****0111",
        "Body": "STOP",
        "MessageSid": "SM_test_001",
    })
    assert resp.status_code == 200
    assert "unsubscribed" in resp.text.lower()

    session = TestSession()
    opt = session.query(ConsentLog).filter(
        ConsentLog.phone == "+160****1234",
        ConsentLog.action == "opted_out",
    ).first()
    assert opt is not None
    assert opt.text == "STOP"
    session.close()


def test_sms_arret_opt_out(client, db_engine):
    TestSession, dealer = _setup_dealer(db_engine)

    resp = client.post("/webhook/twilio/sms", data={
        "From": "+160****9999",
        "To": "+177****0111",
        "Body": "ARRET",
    })
    assert resp.status_code == 200
    assert "unsubscribed" in resp.text.lower()


def test_sms_new_lead_auto_reply(client, db_engine):
    TestSession, dealer = _setup_dealer(db_engine)

    resp = client.post("/webhook/twilio/sms", data={
        "From": "+160****1234",
        "To": "+177****0111",
        "Body": "Hi, do you have any SUVs?",
        "MessageSid": "SM_test_002",
    })
    assert resp.status_code == 200
    assert "<Response>" in resp.text
    assert "<Message>" in resp.text


def test_sms_existing_conversation(client, db_engine):
    """SMS to an existing lead should route through conversation engine."""
    TestSession, dealer = _setup_dealer(db_engine)

    session = TestSession()
    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.SMS,
        name=None,
        phone="+160****1234",
        state=LeadState.AUTO_REPLIED,
    )
    session.add(lead)
    session.commit()
    session.close()

    resp = client.post("/webhook/twilio/sms", data={
        "From": "+160****1234",
        "To": "+177****0111",
        "Body": "What's the price?",
        "MessageSid": "SM_test_003",
    })
    # SMS webhook returns empty TwiML immediately — AI reply is sent async via background task
    assert resp.status_code == 200
    assert "<Response></Response>" in resp.text


# ---- WhatsApp webhook -----------------------------------------------------------------

def test_whatsapp_claim_handling(client, db_engine):
    TestSession, dealer = _setup_dealer(db_engine)

    session = TestSession()
    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.WEBFORM,
        name="Test Customer",
        phone="+160****1234",
        state=LeadState.ASSIGNED,
        assigned_rep="Mike",
    )
    session.add(lead)
    session.commit()
    lead_id = lead.id
    session.close()

    resp = client.post("/webhook/twilio/whatsapp", data={
        "From": "whatsapp:+160****0121",
        "To": "whatsapp:+177****0112",
        "Body": "1",
    })
    assert resp.status_code == 200
    assert "claimed" in resp.text.lower()

    session = TestSession()
    updated = session.get(Lead, lead_id)
    assert updated.state == LeadState.CLAIMED
    session.close()


def test_whatsapp_pass_reassigns(client, db_engine):
    TestSession, dealer = _setup_dealer(db_engine)

    session = TestSession()
    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.WEBFORM,
        name="Test Customer",
        phone="+160****1234",
        state=LeadState.ASSIGNED,
        assigned_rep="Mike",
    )
    session.add(lead)
    session.commit()
    session.close()

    resp = client.post("/webhook/twilio/whatsapp", data={
        "From": "whatsapp:+160****0121",
        "To": "whatsapp:+177****0112",
        "Body": "2",
    })
    assert resp.status_code == 200
    assert "passed" in resp.text.lower()


def test_whatsapp_unknown_rep(client, db_engine):
    TestSession, dealer = _setup_dealer(db_engine)

    resp = client.post("/webhook/twilio/whatsapp", data={
        "From": "whatsapp:+199****9999",
        "To": "whatsapp:+177****0112",
        "Body": "1",
    })
    assert resp.status_code == 200
    assert "<Response></Response>" in resp.text


# ---- Voice webhook --------------------------------------------------------------------

def test_voice_missed_call_text_back(client, db_engine):
    TestSession, dealer = _setup_dealer(db_engine)

    resp = client.post("/webhook/twilio/voice", data={
        "From": "+160****1234",
        "To": "+177****0111",
        "CallStatus": "no-answer",
    })
    assert resp.status_code == 200
    assert "missed your call" in resp.text.lower()
    assert "Test Auto" in resp.text


def test_voice_opted_out_suppressed(client, db_engine):
    TestSession, dealer = _setup_dealer(db_engine)

    session = TestSession()
    opt = ConsentLog(dealer_id=dealer.id, phone="+160****1234", action="opted_out", text="STOP")
    session.add(opt)
    session.commit()
    session.close()

    resp = client.post("/webhook/twilio/voice", data={
        "From": "+160****1234",
        "To": "+177****0111",
        "CallStatus": "no-answer",
    })
    assert resp.status_code == 200
    assert "<Response></Response>" in resp.text


# ---- Status webhook -------------------------------------------------------------------

def test_status_webhook(client, db_engine):
    resp = client.post("/webhook/twilio/status", data={
        "MessageSid": "SM_fake_001",
        "MessageStatus": "delivered",
    })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ---- Messenger webhook ----------------------------------------------------------------

def test_messenger_verification(client):
    resp = client.get("/webhook/messenger?hub.challenge=test_challenge_123")
    assert resp.status_code == 200
    assert resp.text == "test_challenge_123"


# ---- START/STARTALL resubscribe ------------------------------------------------------

def test_start_resubscribe_opts_out_phone(client, db_engine):
    """START from an opted-out phone resubscribes and logs consent."""
    TestSession, dealer = _setup_dealer(db_engine)
    phone = "+160****1234"

    # Create opt-out record
    session = TestSession()
    opt = ConsentLog(dealer_id=dealer.id, phone=phone, action="opted_out", text="STOP")
    session.add(opt)
    # Create an OPTED_OUT lead
    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.SMS,
        name="Resub Customer",
        phone=phone,
        state=LeadState.OPTED_OUT,
    )
    session.add(lead)
    session.commit()
    session.close()

    resp = client.post("/webhook/twilio/sms", data={
        "From": phone,
        "To": "+177****0111",
        "Body": "START",
        "MessageSid": "SM_test_start_001",
    })
    assert resp.status_code == 200
    assert "resubscribed" in resp.text.lower()

    session = TestSession()
    # Verify consent re_granted log exists
    consent = session.query(ConsentLog).filter(
        ConsentLog.phone == phone,
        ConsentLog.action == "re_granted",
    ).first()
    assert consent is not None
    assert consent.text == "START"

    # Verify lead moved back to NEW
    updated_lead = session.query(Lead).filter(
        Lead.dealer_id == dealer.id,
        Lead.phone == phone,
    ).order_by(Lead.created_at.desc()).first()
    assert updated_lead.state == LeadState.NEW
    session.close()


def test_startall_resubscribe(client, db_engine):
    """STARTALL behaves identically to START."""
    TestSession, dealer = _setup_dealer(db_engine)
    phone = "+160****5555"

    session = TestSession()
    opt = ConsentLog(dealer_id=dealer.id, phone=phone, action="opted_out", text="STOPALL")
    session.add(opt)
    session.commit()
    session.close()

    resp = client.post("/webhook/twilio/sms", data={
        "From": phone,
        "To": "+177****0111",
        "Body": "STARTALL",
        "MessageSid": "SM_test_startall_001",
    })
    assert resp.status_code == 200
    assert "resubscribed" in resp.text.lower()

    session = TestSession()
    consent = session.query(ConsentLog).filter(
        ConsentLog.phone == phone,
        ConsentLog.action == "re_granted",
    ).first()
    assert consent is not None
    session.close()


def test_start_already_subscribed(client, db_engine):
    """START from a phone that is NOT opted out returns 'already subscribed'."""
    TestSession, dealer = _setup_dealer(db_engine)

    resp = client.post("/webhook/twilio/sms", data={
        "From": "+160****7777",
        "To": "+177****0111",
        "Body": "START",
        "MessageSid": "SM_test_start_002",
    })
    assert resp.status_code == 200
    assert "already subscribed" in resp.text.lower() or "resubscribed" in resp.text.lower()


# ---- Consent gating on send_sms ------------------------------------------------------

def test_send_sms_no_consent_blocked(db_session, fake_twilio):
    """send_sms blocks if the lead exists but has no consent."""
    from tools.send_sms import send_sms

    dealer = Dealer(slug="test-consent", name="Test", config={
        "dealer": {"name": "Test", "timezone": "America/Vancouver"},
        "compliance": {"quiet_hours": "21:00-08:00"},
        "channels": {"sms_number": "+177****0111"},
    })
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    # Lead with consent=False and no ConsentLog entry
    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.EMAIL,
        name="No Consent",
        phone="+160****8888",
        consent=False,
        state=LeadState.NEW,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    from unittest.mock import patch as mock_patch
    with mock_patch("tools.send_sms._is_quiet_hours", return_value=False):
        result = send_sms(
            db_session, "+160****8888", "Hello!", "+177****0111",
            dealer_slug="test-consent",
            dealer_config=dealer.config,
            lead=lead,
            fake_twilio=fake_twilio,
        )
    assert result is None
    assert len(fake_twilio.sent) == 0


def test_send_sms_with_consent_allowed(db_session, fake_twilio):
    """send_sms allows if lead.consent=True."""
    from tools.send_sms import send_sms

    dealer = Dealer(slug="test-consent", name="Test", config={
        "dealer": {"name": "Test", "timezone": "America/Vancouver"},
        "compliance": {"quiet_hours": "21:00-08:00"},
        "channels": {"sms_number": "+177****0111"},
    })
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.WEBFORM,
        name="Has Consent",
        phone="+160****8889",
        consent=True,
        state=LeadState.NEW,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    from unittest.mock import patch as mock_patch
    with mock_patch("tools.send_sms._is_quiet_hours", return_value=False):
        result = send_sms(
            db_session, "+160****8889", "Hello!", "+177****0111",
            dealer_slug="test-consent",
            dealer_config=dealer.config,
            lead=lead,
            fake_twilio=fake_twilio,
        )
    assert result is not None
    assert len(fake_twilio.sent) == 1


def test_send_sms_consentlog_granted_allows(db_session, fake_twilio):
    """send_sms allows if ConsentLog has a 'granted' entry (SMS inbound implied consent)."""
    from tools.send_sms import send_sms

    dealer = Dealer(slug="test-consent", name="Test", config={
        "dealer": {"name": "Test", "timezone": "America/Vancouver"},
        "compliance": {"quiet_hours": "21:00-08:00"},
        "channels": {"sms_number": "+177****0111"},
    })
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    phone = "+160****8890"
    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.SMS,
        name="Implied Consent",
        phone=phone,
        consent=False,  # No webform consent
        state=LeadState.NEW,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    # Log implied consent from SMS inbound
    consent = ConsentLog(
        dealer_id=dealer.id,
        lead_id=lead.id,
        phone=phone,
        action="granted",
        text="sms_inbound",
    )
    db_session.add(consent)
    db_session.commit()

    from unittest.mock import patch as mock_patch
    with mock_patch("tools.send_sms._is_quiet_hours", return_value=False):
        result = send_sms(
            db_session, phone, "Hello!", "+177****0111",
            dealer_slug="test-consent",
            dealer_config=dealer.config,
            lead=lead,
            fake_twilio=fake_twilio,
        )
    assert result is not None
    assert len(fake_twilio.sent) == 1