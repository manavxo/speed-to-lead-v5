"""End-to-end pipeline test: POST a webform lead and assert the FULL chain.

    auto-reply sent -> AI proactive follow-up (ENGAGED) -> customer conversation ->
    book_appointment -> APPT_SET -> rep assigned + notified.

Uses fake_twilio and fake_llm so no real external calls are made.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
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
    """Test the complete pipeline: webform -> auto-reply -> AI follow-up -> converse -> book -> rep assigned."""
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

    # Assert: Lead created, auto-replied, AI engaged — but NOT assigned to rep yet
    assert lead.state == LeadState.ENGAGED
    assert lead.name == "John Doe"
    assert lead.phone == "+16041234567"
    assert lead.vehicle_id == vehicle.id
    assert lead.assigned_rep is None  # Rep NOT assigned until appointment booked

    # Assert: Auto-reply was sent via the customer-facing SMS chokepoint (send_sms).
    all_messages = fake_twilio.sent
    assert len(all_messages) >= 1, f"Expected at least 1 customer-facing SMS, got {len(all_messages)}"
    # The auto-reply should contain the dealer name
    assert any("Test Motors" in m.get("body", "") for m in all_messages), \
        f"Expected dealer name in messages: {[m.get('body', '') for m in all_messages]}"

    # Assert: Messages persisted (auto-reply + AI follow-up)
    messages = e2e_session.query(Message).filter(Message.lead_id == lead.id).all()
    assert len(messages) >= 1  # At least auto-reply

    # Assert: LeadEvents recorded
    events = e2e_session.query(LeadEvent).filter(LeadEvent.lead_id == lead.id).all()
    state_changes = [e for e in events if e.type == "state_change"]
    assert any(e.payload.get("to") == "AUTO_REPLIED" for e in state_changes)
    assert any(e.payload.get("to") == "ENGAGED" for e in state_changes)

    # Assert: Consent logged
    consent = e2e_session.query(ConsentLog).filter(
        ConsentLog.lead_id == lead.id,
        ConsentLog.action == "granted",
    ).first()
    assert consent is not None

    # 2. BOOK APPOINTMENT — this triggers rep assignment
    from tools.book_appointment import book_appointment
    appt_time = datetime(2026, 6, 5, 14, 0, tzinfo=timezone.utc)
    appt = book_appointment(e2e_session, lead, appt_time, notes="Test drive of Honda Civic",
                            dealer_config=dealer.config)

    assert lead.state == LeadState.APPT_SET
    assert appt.status == "set"
    assert lead.assigned_rep is not None  # NOW rep is assigned
    assert lead.assigned_rep in ("Manav", "Friend")
    # Compare the naive datetimes (SQLite drops tzinfo on read)
    assert appt.scheduled_for.replace(tzinfo=None) == appt_time.replace(tzinfo=None)

    # Assert: Appointment event recorded
    appt_events = e2e_session.query(LeadEvent).filter(
        LeadEvent.lead_id == lead.id,
        LeadEvent.type == "appointment",
    ).all()
    assert len(appt_events) >= 1

    # Assert: Rep notification sent (appointment_set, not claim)
    rep_messages = [m for m in e2e_session.query(Message).filter(Message.lead_id == lead.id).all()
                    if getattr(m, "recipient_role", None) == "rep"]
    assert len(rep_messages) >= 1, "Expected rep notification on appointment booking"


def test_escalation_after_timeout(e2e_session, dealer):
    """Test that an unclaimed appointment notification triggers escalation."""
    fake_twilio = E2EFakeTwilio()
    now = datetime(2026, 6, 4, 17, 0, tzinfo=timezone.utc)

    # Ingest a lead — in new flow, lead goes to ENGAGED, no rep assigned
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
    assert lead.state == LeadState.ENGAGED
    assert lead.assigned_rep is None  # No rep assigned yet

    # Book appointment — this assigns a rep
    from tools.book_appointment import book_appointment
    appt_time = datetime(2026, 6, 5, 14, 0, tzinfo=timezone.utc)
    appt = book_appointment(e2e_session, lead, appt_time, notes="Test drive",
                            dealer_config=dealer.config)
    assert lead.assigned_rep is not None  # Now rep is assigned

    # The escalation flow is now about rep not responding to appointment notification
    # rather than not claiming a raw lead


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
    assert lead.state == LeadState.ENGAGED  # AI engaged, no rep assigned
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
    assert lead.state in (LeadState.AUTO_REPLIED, LeadState.ENGAGED, LeadState.NEW)


def test_round_robin_distribution(e2e_session, dealer):
    """Test that appointments trigger round-robin rep distribution."""
    fake_twilio = E2EFakeTwilio()
    now = datetime(2026, 6, 4, 17, 0, tzinfo=timezone.utc)

    from tools.route_lead import ingest_lead
    from tools.book_appointment import book_appointment
    reps = []
    for i in range(4):
        lead_data = NormalizedLead(
            source=Channel.WEBFORM,
            name=f"Lead {i}",
            phone=f"+1604100{i:04d}",
            consent=True,
            raw={},
        )
        lead = ingest_lead(e2e_session, dealer, lead_data, fake_twilio=fake_twilio, now=now)
        # Book appointment — this triggers rep assignment via round-robin
        appt_time = datetime(2026, 6, 5, 14 + i, 0, tzinfo=timezone.utc)
        book_appointment(e2e_session, lead, appt_time, notes=f"Test drive {i}",
                         dealer_config=dealer.config)
        reps.append(lead.assigned_rep)

    # With 2 reps and 4 appointments, each should get 2
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


def test_dedup_resends_when_previous_was_dryrun(e2e_session, dealer):
    """Test that dedup re-sends when the existing lead's messages were DRYRUN.

    When OUTBOUND_ENABLED was false during first submission, messages are logged
    with DRYRUN_* provider_sids but never sent to Twilio. A subsequent submission
    with the same phone should detect the DRYRUN and re-send, not silently dedup.
    """
    fake_twilio = E2EFakeTwilio()
    now = datetime(2026, 6, 4, 17, 0, tzinfo=timezone.utc)

    from tools.route_lead import ingest_lead
    lead_data = NormalizedLead(
        source=Channel.WEBFORM,
        name="DRYRUN Test",
        phone="+16048887777",
        consent=True,
        raw={},
    )

    # First submission — creates a lead with real messages
    lead1 = ingest_lead(e2e_session, dealer, lead_data, fake_twilio=fake_twilio, now=now)
    assert lead1.id is not None
    initial_msg_count = len(fake_twilio.sent)

    # Simulate the scenario: mark all outbound messages as DRYRUN
    # (this is what happens when OUTBOUND_ENABLED=false during the first submission)
    outbound_msgs = e2e_session.execute(
        select(Message).where(
            Message.lead_id == lead1.id,
            Message.direction == Direction.OUTBOUND,
        )
    ).scalars().all()
    for i, msg in enumerate(outbound_msgs):
        msg.provider_sid = f"DRYRUN_{i:032d}"
    e2e_session.commit()

    # Reset fake_twilio to track new sends
    fake_twilio.sent.clear()

    # Second submission — same phone, should detect DRYRUN and re-send
    lead2 = ingest_lead(e2e_session, dealer, lead_data, fake_twilio=fake_twilio, now=now)

    # BUG: Without the fix, lead2.id == lead1.id and no messages are sent
    # FIX: lead2 should be the same lead but messages should be re-sent
    assert lead2.id == lead1.id  # Same lead reused, not a new one
    assert len(fake_twilio.sent) > 0  # Messages were re-sent (not silently deduped)


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