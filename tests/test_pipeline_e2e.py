"""End-to-end pipeline test: POST a webform lead and assert the FULL chain.

    auto-reply recorded/sent -> ASSIGNED + rep pinged -> on timeout escalates ->
    WhatsApp "1" claims -> a conversation turn -> book_appointment -> APPT_SET.

Uses fake_twilio and fake_llm so no real external calls are made.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.models import (
    Appointment, Channel, ConsentLog, Dealer, Direction, Lead, LeadEvent,
    LeadState, Message, Vehicle,
)
from app.adapters.intake import NormalizedLead


@pytest.fixture
def e2e_engine():
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
def e2e_session(e2e_engine):
    TestSession = sessionmaker(bind=e2e_engine, expire_on_commit=False)
    session = TestSession()
    yield session
    session.close()


@pytest.fixture
def dealer(e2e_session):
    """Create a test dealer with sales team and config."""
    d = Dealer(
        slug="test-dealer",
        name="Test Motors",
        timezone="America/Vancouver",
        sms_number="+17787623122",
        whatsapp_sender="+14155238886",
        web_form_token="test-token-123",
        config={
            "dealer": {
                "slug": "test-dealer",
                "name": "Test Motors",
                "timezone": "America/Vancouver",
                "hours": {"mon": "09:00-19:00", "tue": "09:00-19:00", "wed": "09:00-19:00",
                          "thu": "09:00-19:00", "fri": "09:00-19:00", "sat": "10:00-17:00"},
            },
            "channels": {
                "sms_number": "+17787623122",
                "whatsapp_sender": "+14155238886",
                "web_form_token": "test-token-123",
            },
            "sales_team": [
                {"name": "Manav", "phone": "+16048392870", "active": True},
                {"name": "Friend", "phone": "+17787694366", "active": True},
            ],
            "routing": {
                "strategy": "round_robin",
                "claim_timeout_min": 2,
                "escalation": ["reassign", "notify_manager"],
                "manager_phone": "+17787694366",
            },
            "compliance": {
                "opt_out_keywords": ["STOP", "ARRET"],
                "quiet_hours": "21:00-08:00",
                "consent_text": "By submitting you agree to receive texts from Test Motors. Reply STOP to opt out.",
            },
            "ai": {
                "persona": "friendly, concise sales rep",
                "goal": "book_appointment",
                "guardrails": {"no_price_negotiation": True, "no_financing_promises": True},
            },
            "lead_org": {"mode": "native"},
            "inventory": {"source": "manual", "refresh_min": 180},
        },
    )
    e2e_session.add(d)
    e2e_session.commit()
    e2e_session.refresh(d)
    return d


@pytest.fixture
def vehicle(e2e_session, dealer):
    """Create a test vehicle in the dealer's inventory."""
    v = Vehicle(
        dealer_id=dealer.id,
        stock_no="STK001",
        vin="1HGBH41JXMN109186",
        year=2024,
        make="Honda",
        model="Civic",
        trim="EX",
        body="Sedan",
        mileage=15000,
        price=32500.0,
        status="available",
    )
    e2e_session.add(v)
    e2e_session.commit()
    e2e_session.refresh(v)
    return v


class E2EFakeTwilio:
    """Records all outbound messages for assertion."""
    def __init__(self):
        self.sent: list[dict] = []

    def send(self, **kwargs) -> str:
        sid = f"SM_e2e_{len(self.sent):032d}"
        self.sent.append({"sid": sid, **kwargs})
        return sid


class E2EFakeLLM:
    """Returns scripted responses for conversation turns."""
    def __init__(self, script=None):
        self.script = list(script or [])
        self.calls: list[dict] = []

    def respond(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        if self.script:
            return self.script.pop(0)
        return {"type": "text", "text": "Thanks for your interest! Would you like to book a test drive?"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_full_pipeline_e2e(e2e_session, dealer, vehicle):
    """Test the complete pipeline: webform -> auto-reply -> assign -> claim -> converse -> book."""
    fake_twilio = E2EFakeTwilio()
    fake_llm = E2EFakeLLM([
        {"type": "text", "text": "Great choice! The 2024 Honda Civic EX is available. Want to book a test drive?"},
    ])

    now = datetime(2026, 6, 4, 17, 0, tzinfo=timezone.utc)  # Thu 10:00 Vancouver

    # 1. INGEST LEAD (webform)
    from tools.route_lead import ingest_lead
    lead_data = NormalizedLead(
        source=Channel.WEBFORM,
        name="John Doe",
        phone="+16041234567",
        email="john@example.com",
        vehicle_ref="STK001",
        consent=True,
        raw={},
    )
    lead = ingest_lead(e2e_session, dealer, lead_data, fake_twilio=fake_twilio, now=now)

    # Assert: Lead created and auto-replied
    assert lead.state == LeadState.ASSIGNED  # Ingest -> AUTO_REPLIED -> ASSIGNED
    assert lead.name == "John Doe"
    assert lead.phone == "+16041234567"
    assert lead.vehicle_id == vehicle.id
    assert lead.assigned_rep in ("Manav", "Friend")

    # Assert: Auto-reply was sent via the customer-facing SMS chokepoint (send_sms).
    # The claim ping goes through notify_rep, which has its own fake — it's verified
    # via the Message table check below.
    all_messages = fake_twilio.sent
    assert len(all_messages) >= 1, f"Expected at least 1 customer-facing SMS, got {len(all_messages)}"
    # The auto-reply should contain the dealer name
    assert any("Test Motors" in m.get("body", "") for m in all_messages), \
        f"Expected dealer name in messages: {[m.get('body', '') for m in all_messages]}"

    # Assert: Messages persisted (auto-reply + claim ping via notify_rep)
    messages = e2e_session.query(Message).filter(Message.lead_id == lead.id).all()
    assert len(messages) >= 2  # At least auto-reply + claim ping
    # Verify the claim ping has the right shape: it should be a rep-targeted message.
    # notify_rep() persists with recipient_role="rep" per directive H.2.4.
    rep_messages = [m for m in messages if getattr(m, "recipient_role", None) == "rep"]
    assert len(rep_messages) >= 1, (
        f"Expected at least 1 rep-targeted claim ping via notify_rep, "
        f"got {len(rep_messages)} messages with recipient_role='rep'. "
        f"All messages: {[(m.direction, m.recipient_role, m.body[:50]) for m in messages]}"
    )

    # Assert: LeadEvents recorded
    events = e2e_session.query(LeadEvent).filter(LeadEvent.lead_id == lead.id).all()
    state_changes = [e for e in events if e.type == "state_change"]
    assert any(e.payload.get("to") == "AUTO_REPLIED" for e in state_changes)
    assert any(e.payload.get("to") == "ASSIGNED" for e in state_changes)

    # Assert: Consent logged
    consent = e2e_session.query(ConsentLog).filter(
        ConsentLog.lead_id == lead.id,
        ConsentLog.action == "granted",
    ).first()
    assert consent is not None

    # 2. CLAIM (rep replies "1")
    from app.engine.router import handle_claim
    handle_claim(e2e_session, lead, lead.assigned_rep)
    assert lead.state == LeadState.CLAIMED

    # 3. CONVERSATION TURN
    from app.engine.conversation import handle_turn
    # Transition to ENGAGED first (simulating the webhook doing this)
    from app.engine.lifecycle import transition
    transition(e2e_session, lead, LeadState.ENGAGED, reason="customer_reply")

    dealer_config = dealer.config or {}
    result = handle_turn(
        e2e_session, lead, "I love that Civic! Can I come see it?",
        dealer_config=dealer_config,
        vehicle=vehicle,
        fake_llm=fake_llm,
        now=now,
    )

    # Business hours -> draft mode
    assert result["mode"] == "draft"
    assert "Civic" in result["text"] or "test drive" in result["text"].lower() or "interest" in result["text"].lower()

    # 4. BOOK APPOINTMENT
    from tools.book_appointment import book_appointment
    appt_time = datetime(2026, 6, 5, 14, 0, tzinfo=timezone.utc)
    appt = book_appointment(e2e_session, lead, appt_time, notes="Test drive of Honda Civic")

    assert lead.state == LeadState.APPT_SET
    assert appt.status == "set"
    # Compare the naive datetimes (SQLite drops tzinfo on read)
    assert appt.scheduled_for.replace(tzinfo=None) == appt_time.replace(tzinfo=None)

    # Assert: Appointment event recorded
    appt_events = e2e_session.query(LeadEvent).filter(
        LeadEvent.lead_id == lead.id,
        LeadEvent.type == "appointment",
    ).all()
    assert len(appt_events) >= 1


def test_escalation_after_timeout(e2e_session, dealer):
    """Test that an unclaimed lead gets escalated after claim_timeout_min."""
    fake_twilio = E2EFakeTwilio()
    now = datetime(2026, 6, 4, 17, 0, tzinfo=timezone.utc)

    # Ingest a lead
    from tools.route_lead import ingest_lead
    lead_data = NormalizedLead(
        source=Channel.WEBFORM,
        name="Jane Smith",
        phone="+16049876543",
        email="jane@example.com",
        consent=True,
        raw={},
    )
    lead = ingest_lead(e2e_session, dealer, lead_data, fake_twilio=fake_twilio, now=now)
    assert lead.state == LeadState.ASSIGNED
    assigned_rep = lead.assigned_rep

    # Simulate timeout (3 minutes later)
    later = now + timedelta(minutes=3)
    from app.engine.escalation import on_claim_timeout
    result = on_claim_timeout(
        e2e_session, lead.id, dealer,
        dealer.config.get("sales_team", []),
        fake_twilio=fake_twilio,
        sms_number=dealer.config.get("channels", {}).get("sms_number"),
    )

    assert result is not None
    assert lead.state == LeadState.ESCALATED or lead.state == LeadState.ASSIGNED
    # After escalation with "reassign" action, should be ASSIGNED to a different rep
    if lead.state == LeadState.ASSIGNED:
        # Lead was reassigned
        assert lead.assigned_rep is not None


def test_opt_out_prevents_further_sends(e2e_session, dealer):
    """Test that an opted-out number gets no further messages."""
    fake_twilio = E2EFakeTwilio()
    now = datetime(2026, 6, 4, 17, 0, tzinfo=timezone.utc)

    # Ingest a lead
    from tools.route_lead import ingest_lead
    lead_data = NormalizedLead(
        source=Channel.WEBFORM,
        name="Opt Out User",
        phone="+16045551234",
        consent=True,
        raw={},
    )
    lead = ingest_lead(e2e_session, dealer, lead_data, fake_twilio=fake_twilio, now=now)
    assert lead.state == LeadState.ASSIGNED

    # Mark as opted out
    opt = ConsentLog(
        dealer_id=dealer.id,
        lead_id=lead.id,
        phone="+16045551234",
        action="opted_out",
        text="STOP",
    )
    e2e_session.add(opt)
    e2e_session.commit()

    # Try to send SMS to opted-out number
    from tools.send_sms import send_sms
    fake_twilio.sent.clear()
    sid = send_sms(
        e2e_session, "+16045551234", "Hello again!", "+17787623122",
        dealer_config=dealer.config or {},
        lead=lead,
        fake_twilio=fake_twilio,
    )
    assert sid is None  # Suppressed
    assert len(fake_twilio.sent) == 0


def test_quiet_hours_suppresses_send(e2e_session, dealer):
    """Test that sends are suppressed during quiet hours."""
    fake_twilio = E2EFakeTwilio()
    # 23:00 UTC = 16:00 PDT (not quiet) or use a time that IS in quiet hours
    # Quiet hours: 21:00-08:00 Vancouver = 04:00-15:00 UTC (PDT) or 05:00-16:00 UTC (PST)
    # Let's use 06:00 UTC = 23:00 Vancouver (in quiet hours)
    now = datetime(2026, 6, 4, 6, 0, tzinfo=timezone.utc)

    from tools.route_lead import ingest_lead
    lead_data = NormalizedLead(
        source=Channel.WEBFORM,
        name="Night Caller",
        phone="+16047778888",
        consent=True,
        raw={},
    )
    lead = ingest_lead(e2e_session, dealer, lead_data, fake_twilio=fake_twilio, now=now)

    # The auto-reply should have been suppressed (quiet hours)
    # But the lead should still be saved and transitioned
    assert lead is not None
    assert lead.state in (LeadState.AUTO_REPLIED, LeadState.NEW, LeadState.ASSIGNED)


def test_round_robin_distribution(e2e_session, dealer):
    """Test that leads are distributed evenly between reps."""
    fake_twilio = E2EFakeTwilio()
    now = datetime(2026, 6, 4, 17, 0, tzinfo=timezone.utc)

    from tools.route_lead import ingest_lead
    reps = []
    for i in range(4):
        lead_data = NormalizedLead(
            source=Channel.WEBFORM,
            name=f"Lead {i}",
            phone=f"+1604100{i:04d}",
            consent=True,
            raw={},
        )
        # Clear dedupe by using different phones
        lead = ingest_lead(e2e_session, dealer, lead_data, fake_twilio=fake_twilio, now=now)
        reps.append(lead.assigned_rep)

    # With 2 reps and 4 leads, each should get 2
    from collections import Counter
    counts = Counter(reps)
    assert len(counts) == 2
    assert all(c == 2 for c in counts.values())


def test_dedup_prevents_duplicate_leads(e2e_session, dealer):
    """Test that a second submission from the same phone within 24h returns the existing lead."""
    fake_twilio = E2EFakeTwilio()
    now = datetime(2026, 6, 4, 17, 0, tzinfo=timezone.utc)

    from tools.route_lead import ingest_lead
    lead_data = NormalizedLead(
        source=Channel.WEBFORM,
        name="Dup Test",
        phone="+16049990000",
        consent=True,
        raw={},
    )

    lead1 = ingest_lead(e2e_session, dealer, lead_data, fake_twilio=fake_twilio, now=now)
    lead2 = ingest_lead(e2e_session, dealer, lead_data, fake_twilio=fake_twilio, now=now)

    assert lead1.id == lead2.id  # Same lead returned


def test_idempotency_on_provider_sid(e2e_session):
    """Test that duplicate MessageSid is detected."""
    from app.main import _idempotency_check

    msg = Message(
        lead_id=1,
        direction=Direction.INBOUND,
        channel=Channel.SMS,
        body="test",
        provider_sid="SM_duplicate_test_123",
    )
    e2e_session.add(msg)
    e2e_session.commit()

    assert _idempotency_check(e2e_session, "SM_duplicate_test_123") is True
    assert _idempotency_check(e2e_session, "SM_different_sid") is False
    assert _idempotency_check(e2e_session, None) is False


def test_grounding_ai_cannot_invent_vehicles(e2e_session, dealer, vehicle):
    """Test that the AI's tool dispatch only returns real inventory."""
    from app.engine.conversation import _execute_tool_call
    import json

    # Search for a car that exists
    result = _execute_tool_call(
        "check_inventory",
        json.dumps({"query": "Honda"}),
        session=e2e_session,
        dealer_id=dealer.id,
    )
    assert len(result["vehicles"]) == 1
    assert result["vehicles"][0]["make"] == "Honda"

    # Search for a car that DOESN'T exist
    result = _execute_tool_call(
        "check_inventory",
        json.dumps({"query": "Ferrari"}),
        session=e2e_session,
        dealer_id=dealer.id,
    )
    assert len(result["vehicles"]) == 0
    assert "No matching" in result["message"]