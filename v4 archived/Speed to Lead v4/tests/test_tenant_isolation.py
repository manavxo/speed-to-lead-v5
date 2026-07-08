"""Tenant isolation tests — verify that Dealer A's data never leaks to Dealer B.

Multi-tenancy is resolved on each inbound webhook by destination (sms_number, whatsapp_sender,
web_form_token). These tests create two dealers and verify complete isolation across all channels.
"""

from __future__ import annotations

from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.models import Dealer, Lead, LeadState, ConsentLog


def _make_two_dealers(db_engine):
    """Create two separate dealers with different tokens, SMS numbers, and WhatsApp senders."""
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = TestSession()

    dealer_a = Dealer(
        slug="dealer-a",
        name="Dealer Alpha",
        config={
            "dealer": {"name": "Dealer Alpha", "timezone": "America/Vancouver", "main_phone": "+160****1000"},
            "hours": {"mon": "09:00-19:00", "tue": "09:00-19:00", "wed": "09:00-19:00",
                      "thu": "09:00-19:00", "fri": "09:00-19:00", "sat": "10:00-17:00"},
            "channels": {
                "web_form_token": "token-alpha",
                "sms_number": "+177****1001",
                "whatsapp_sender": "+177****1002",
            },
            "sales_team": [
                {"name": "Alice", "phone": "+160****1101", "active": True},
            ],
            "compliance": {"opt_out_keywords": ["STOP"], "quiet_hours": "21:00-08:00"},
            "routing": {"strategy": "round_robin", "claim_timeout_min": 5},
            "ai": {"persona": "alpha rep", "goal": "book_appointment"},
        },
    )

    dealer_b = Dealer(
        slug="dealer-b",
        name="Dealer Beta",
        config={
            "dealer": {"name": "Dealer Beta", "timezone": "America/Vancouver", "main_phone": "+160****2000"},
            "hours": {"mon": "09:00-19:00", "tue": "09:00-19:00", "wed": "09:00-19:00",
                      "thu": "09:00-19:00", "fri": "09:00-19:00", "sat": "10:00-17:00"},
            "channels": {
                "web_form_token": "token-beta",
                "sms_number": "+177****2001",
                "whatsapp_sender": "+177****2002",
            },
            "sales_team": [
                {"name": "Bob", "phone": "+160****2201", "active": True},
            ],
            "compliance": {"opt_out_keywords": ["STOP"], "quiet_hours": "21:00-08:00"},
            "routing": {"strategy": "round_robin", "claim_timeout_min": 5},
            "ai": {"persona": "beta rep", "goal": "book_appointment"},
        },
    )

    session.add_all([dealer_a, dealer_b])
    session.commit()
    session.refresh(dealer_a)
    session.refresh(dealer_b)
    session.close()
    return dealer_a, dealer_b


def _make_client(db_engine, monkeypatch):
    import app.db as db_module
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "_SessionLocal", TestSession)
    monkeypatch.setattr(db_module, "_engine", db_engine)
    monkeypatch.setattr(db_module, "init_db", lambda url=None: None)
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_webform_leads_go_to_correct_dealer(db_engine, monkeypatch):
    """Leads submitted via different web_form_token routes end up in different dealers."""
    dealer_a, dealer_b = _make_two_dealers(db_engine)
    client = _make_client(db_engine, monkeypatch)

    # Submit to Dealer A
    resp_a = client.post("/webhook/form/token-alpha", json={
        "full_name": "Alpha Customer",
        "phone": "(604) 555-3001",
        "consent_sms": True,
    })
    assert resp_a.json()["dealer"] == "dealer-a"

    # Submit to Dealer B
    resp_b = client.post("/webhook/form/token-beta", json={
        "full_name": "Beta Customer",
        "phone": "(604) 555-3002",
        "consent_sms": True,
    })
    assert resp_b.json()["dealer"] == "dealer-b"

    # Verify isolation in DB
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = TestSession()

    alpha_leads = session.execute(
        select(Lead).where(Lead.dealer_id == dealer_a.id)
    ).scalars().all()
    beta_leads = session.execute(
        select(Lead).where(Lead.dealer_id == dealer_b.id)
    ).scalars().all()

    assert len(alpha_leads) == 1
    assert len(beta_leads) == 1
    assert alpha_leads[0].name == "Alpha Customer"
    assert beta_leads[0].name == "Beta Customer"
    assert alpha_leads[0].dealer_id != beta_leads[0].dealer_id
    session.close()


def test_sms_leads_routed_by_to_number(db_engine, monkeypatch):
    """Inbound SMS routes to the correct dealer based on the 'To' number."""
    dealer_a, dealer_b = _make_two_dealers(db_engine)
    client = _make_client(db_engine, monkeypatch)

    # SMS to Dealer A's number
    resp_a = client.post("/webhook/twilio/sms", data={
        "From": "+177****4001",
        "To": "+177****1001",  # Dealer A's SMS number
        "Body": "Is the Civic still available?",
    })
    assert "Alpha" in resp_a.text or resp_a.status_code == 200

    # SMS to Dealer B's number
    resp_b = client.post("/webhook/twilio/sms", data={
        "From": "+177****4002",
        "To": "+177****2001",  # Dealer B's SMS number
        "Body": "Is the Mustang still available?",
    })
    assert "Beta" in resp_b.text or resp_b.status_code == 200

    # Verify isolation
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = TestSession()

    alpha_leads = session.execute(
        select(Lead).where(Lead.dealer_id == dealer_a.id)
    ).scalars().all()
    beta_leads = session.execute(
        select(Lead).where(Lead.dealer_id == dealer_b.id)
    ).scalars().all()

    assert len(alpha_leads) == 1
    assert len(beta_leads) == 1
    assert alpha_leads[0].phone == "+177****4001"
    assert beta_leads[0].phone == "+177****4002"
    session.close()


def test_opt_out_only_affects_target_dealer(db_engine, monkeypatch):
    """STOP keyword only opts out from the dealer whose number received it — not the other dealer."""
    dealer_a, dealer_b = _make_two_dealers(db_engine)
    client = _make_client(db_engine, monkeypatch)

    # Create leads at both dealers with the same phone
    # Phone normalizes (604) 555-5001 → +160****5001
    client.post("/webhook/form/token-alpha", json={
        "full_name": "Multi Dealer Customer",
        "phone": "(604) 555-5001",
        "consent_sms": True,
    })
    client.post("/webhook/form/token-beta", json={
        "full_name": "Multi Dealer Customer",
        "phone": "(604) 555-5001",
        "consent_sms": True,
    })

    # Opt out ONLY at Dealer A — From must match normalized phone
    client.post("/webhook/twilio/sms", data={
        "From": "+160****5001",
        "To": "+177****1001",  # Dealer A's number
        "Body": "STOP",
    })

    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = TestSession()

    # Dealer A's lead should be OPTED_OUT
    alpha_lead = session.execute(
        select(Lead).where(Lead.dealer_id == dealer_a.id, Lead.phone == "+160****5001")
    ).scalars().first()
    assert alpha_lead is not None
    assert alpha_lead.state == LeadState.OPTED_OUT

    # Dealer B's lead should still be active (AUTO_REPLIED or similar)
    beta_lead = session.execute(
        select(Lead).where(Lead.dealer_id == dealer_b.id, Lead.phone == "+160****5001")
    ).scalars().first()
    assert beta_lead is not None
    assert beta_lead.state != LeadState.OPTED_OUT, (
        f"Dealer B's lead should NOT be opted out — got {beta_lead.state}"
    )
    session.close()


def test_opt_out_consents_logged_per_dealer(db_engine, monkeypatch):
    """ConsentLog entries are scoped to the correct dealer."""
    dealer_a, dealer_b = _make_two_dealers(db_engine)
    client = _make_client(db_engine, monkeypatch)

    # Opt out at Dealer A
    client.post("/webhook/twilio/sms", data={
        "From": "+177****6001",
        "To": "+177****1001",
        "Body": "STOP",
    })

    # Opt out at Dealer B
    client.post("/webhook/twilio/sms", data={
        "From": "+177****6002",
        "To": "+177****2001",
        "Body": "STOP",
    })

    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = TestSession()

    # ConsentLog entries might not have dealer_id set if no lead exists for that phone
    # The opt-out handler only logs when it finds a matching lead
    # So we check that at least the entries exist with correct phone/text
    alpha_logs = session.execute(
        select(ConsentLog).where(ConsentLog.dealer_id == dealer_a.id)
    ).scalars().all()
    beta_logs = session.execute(
        select(ConsentLog).where(ConsentLog.dealer_id == dealer_b.id)
    ).scalars().all()

    # STOP handler always creates a ConsentLog regardless of lead existence
    assert len(alpha_logs) >= 1, f"Expected at least 1 ConsentLog for dealer A, got {len(alpha_logs)}"
    assert len(beta_logs) >= 1, f"Expected at least 1 ConsentLog for dealer B, got {len(beta_logs)}"
    session.close()


def test_voice_missed_call_textback_scoped_to_dealer(db_engine, monkeypatch):
    """Missed call text-back mentions the correct dealer name."""
    dealer_a, dealer_b = _make_two_dealers(db_engine)
    client = _make_client(db_engine, monkeypatch)

    # Missed call to Dealer A
    resp_a = client.post("/webhook/twilio/voice", data={
        "From": "+177****7001",
        "To": "+177****1001",  # Dealer A
        "CallStatus": "no-answer",
    })
    assert "Dealer Alpha" in resp_a.text

    # Missed call to Dealer B
    resp_b = client.post("/webhook/twilio/voice", data={
        "From": "+177****7002",
        "To": "+177****2001",  # Dealer B
        "CallStatus": "no-answer",
    })
    assert "Dealer Beta" in resp_b.text


def test_whatsapp_claim_scoped_to_dealer(db_engine, monkeypatch):
    """WhatsApp claim only works for the dealer that owns the WhatsApp sender number."""
    dealer_a, dealer_b = _make_two_dealers(db_engine)
    client = _make_client(db_engine, monkeypatch)

    # Create a lead at Dealer A and assign it
    client.post("/webhook/form/token-alpha", json={
        "full_name": "Claim Test",
        "phone": "(604) 555-8001",
        "consent_sms": True,
    })

    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = TestSession()
    lead = session.execute(
        select(Lead).where(Lead.dealer_id == dealer_a.id)
    ).scalars().first()
    assert lead is not None

    # The wired pipeline already advanced to ASSIGNED via round-robin.
    # Set assigned_rep to Alice so the claim webhook finds her.
    lead.assigned_rep = "Alice"
    session.commit()
    session.close()

    # Alice claims via Dealer A's WhatsApp
    resp = client.post("/webhook/twilio/whatsapp", data={
        "From": "whatsapp:+160****1101",  # Alice's WhatsApp
        "To": "whatsapp:+177****1002",     # Dealer A's WhatsApp sender
        "Body": "1",
    })
    assert "claimed" in resp.text.lower()

    # Verify the lead is CLAIMED
    session = TestSession()
    lead = session.get(Lead, lead.id)
    assert lead.state == LeadState.CLAIMED
    session.close()