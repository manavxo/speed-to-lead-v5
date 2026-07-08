"""Phase 5 — AI conversation + business hours + appointment booking."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.engine.conversation import handle_turn, is_business_hours, load_workflow, build_system_prompt
from app.engine.conversation import _call_openrouter_with_retry, MAX_INBOUND_TURNS, _RETRY_BACKOFF
from app.models import Channel, Dealer, Lead, LeadState, Message, Direction, LeadEvent
from tools.book_appointment import book_appointment


DEMO_CONFIG = {
    "dealer": {
        "name": "Demo Auto Sales",
        "timezone": "America/Vancouver",
        "hours": {
            "mon": "09:00-18:00",
            "tue": "09:00-18:00",
            "wed": "09:00-18:00",
            "thu": "09:00-18:00",
            "fri": "09:00-18:00",
            "sat": "10:00-16:00",
            "sun": "closed",
        },
    },
    "ai": {
        "persona": "friendly, concise, no-pressure local sales rep",
        "goal": "book_appointment",
        "guardrails": {"no_price_negotiation": True, "no_financing_promises": True},
    },
}


def test_is_business_hours_during_open():
    # Thu 2026-06-04 17:00 UTC = 10:00 PDT (open)
    now = datetime(2026, 6, 4, 17, 0, tzinfo=timezone.utc)
    assert is_business_hours(DEMO_CONFIG, now) is True


def test_is_business_hours_after_close():
    # Thu 2026-06-04 04:00 UTC = 21:00 PDT (closed)
    now = datetime(2026, 6, 4, 4, 0, tzinfo=timezone.utc)
    assert is_business_hours(DEMO_CONFIG, now) is False


def test_is_business_hours_sunday_closed():
    # Sun 2026-06-07 17:00 UTC = 10:00 PDT (but Sunday = closed)
    now = datetime(2026, 6, 7, 17, 0, tzinfo=timezone.utc)
    assert is_business_hours(DEMO_CONFIG, now) is False


def test_is_business_hours_saturday_open():
    # Sat 2026-06-06 18:00 UTC = 11:00 PDT (open 10-16)
    now = datetime(2026, 6, 6, 18, 0, tzinfo=timezone.utc)
    assert is_business_hours(DEMO_CONFIG, now) is True


def test_is_business_hours_saturday_after_close():
    # Sat 2026-06-07 00:00 UTC = 17:00 PDT (closed at 16:00)
    now = datetime(2026, 6, 7, 0, 0, tzinfo=timezone.utc)
    assert is_business_hours(DEMO_CONFIG, now) is False


def test_is_business_hours_no_hours_config():
    config = {"dealer": {"timezone": "America/Vancouver"}}
    now = datetime(2026, 6, 4, 17, 0, tzinfo=timezone.utc)
    assert is_business_hours(config, now) is False


def test_load_workflow():
    content = load_workflow("qualify_and_book.md")
    assert len(content) > 0
    assert isinstance(content, str)


def test_build_system_prompt_contains_guardrails():
    prompt = build_system_prompt(DEMO_CONFIG)
    assert "negotiate on price" in prompt.lower() or "Do NOT negotiate on price" in prompt
    assert "financing promises" in prompt.lower() or "Do NOT make specific financing promises" in prompt
    assert "Demo Auto Sales" in prompt


def test_handle_turn_business_hours_draft_mode():
    # Thu 10:00 PDT = business hours -> draft mode
    now = datetime(2026, 6, 4, 17, 0, tzinfo=timezone.utc)
    from tests.conftest import FakeLLM
    fake_llm = FakeLLM(script=[{"type": "text", "text": "Thanks for reaching out!"}])

    result = handle_turn(
        session=None,
        lead=None,
        inbound_text="Is the Civic available?",
        dealer_config=DEMO_CONFIG,
        fake_llm=fake_llm,
        now=now,
    )
    assert result["mode"] == "draft"  # business hours = draft mode
    assert result["is_business_hours"] is True


def test_handle_turn_after_hours_send_mode():
    # Thu 04:00 UTC = 21:00 PDT = after hours -> send mode
    now = datetime(2026, 6, 4, 4, 0, tzinfo=timezone.utc)
    from tests.conftest import FakeLLM
    fake_llm = FakeLLM(script=[{"type": "text", "text": "Thanks! We'll reach out tomorrow."}])

    result = handle_turn(
        session=None,
        lead=None,
        inbound_text="Is the Civic available?",
        dealer_config=DEMO_CONFIG,
        fake_llm=fake_llm,
        now=now,
    )
    assert result["mode"] == "send"
    assert result["is_business_hours"] is False


def test_book_appointment(db_session):
    dealer = Dealer(slug="test-dealer", name="Test", config={})
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.WEBFORM,
        name="Test Customer",
        phone="+16045551234",
        state=LeadState.ENGAGED,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    from datetime import timedelta
    appt_time = datetime.now(timezone.utc) + timedelta(days=1)

    appt = book_appointment(db_session, lead, appt_time, notes="Test drive")
    assert appt.status == "set"
    assert lead.state == LeadState.APPT_SET


def test_book_appointment_rejected_for_wrong_state(db_session):
    dealer = Dealer(slug="test-dealer", name="Test", config={})
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.WEBFORM,
        name="Test Customer",
        state=LeadState.OPTED_OUT,  # terminal state — not bookable
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    with pytest.raises(ValueError, match="Cannot book appointment"):
        book_appointment(db_session, lead, datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Retry logic tests
# ---------------------------------------------------------------------------

def test_retry_succeeds_on_first_attempt():
    """No retries needed when the call succeeds."""
    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return "ok"
    # Should not raise
    result = _call_openrouter_with_retry(FakeClient(), model="test")
    assert result == "ok"


def test_retry_retries_on_500_then_succeeds(monkeypatch):
    """Should retry on 500 and succeed on the second attempt."""
    attempts = []
    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    attempts.append(1)
                    if len(attempts) < 2:
                        exc = Exception("server error")
                        exc.status_code = 500
                        raise exc
                    return "ok"

    # Patch time.sleep so we don't actually wait
    monkeypatch.setattr("app.engine.conversation.time.sleep", lambda s: None)
    result = _call_openrouter_with_retry(FakeClient(), model="test")
    assert result == "ok"
    assert len(attempts) == 2


def test_retry_raises_after_exhausted_attempts(monkeypatch):
    """Should raise after all retries are exhausted on persistent 500."""
    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    exc = Exception("server error")
                    exc.status_code = 500
                    raise exc

    monkeypatch.setattr("app.engine.conversation.time.sleep", lambda s: None)
    with pytest.raises(Exception, match="server error"):
        _call_openrouter_with_retry(FakeClient(), model="test")


def test_retry_does_not_retry_on_4xx(monkeypatch):
    """4xx errors (e.g. 400) should NOT be retried — they're permanent."""
    attempts = []
    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    attempts.append(1)
                    exc = Exception("bad request")
                    exc.status_code = 400
                    raise exc

    monkeypatch.setattr("app.engine.conversation.time.sleep", lambda s: None)
    with pytest.raises(Exception, match="bad request"):
        _call_openrouter_with_retry(FakeClient(), model="test")
    assert len(attempts) == 1  # No retry


def test_retry_retries_on_timeout(monkeypatch):
    """Should retry on TimeoutError."""
    attempts = []
    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    attempts.append(1)
                    if len(attempts) < 2:
                        raise TimeoutError("timed out")
                    return "ok"

    monkeypatch.setattr("app.engine.conversation.time.sleep", lambda s: None)
    result = _call_openrouter_with_retry(FakeClient(), model="test")
    assert result == "ok"
    assert len(attempts) == 2


# ---------------------------------------------------------------------------
# Max conversation turns tests
# ---------------------------------------------------------------------------

def test_max_turns_not_hit_under_limit(db_session):
    """When inbound count < MAX_INBOUND_TURNS, normal conversation proceeds."""
    dealer = Dealer(slug="max-turns-test", name="Test Dealer", config={})
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.SMS,
        name="Customer",
        phone="+1234567890",
        state=LeadState.ENGAGED,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    # Add 5 inbound messages (below the limit of 10)
    for i in range(5):
        msg = Message(
            lead_id=lead.id,
            direction=Direction.INBOUND,
            channel=Channel.SMS,
            body=f"Message {i}",
        )
        db_session.add(msg)
    db_session.commit()

    now = datetime(2026, 6, 4, 4, 0, tzinfo=timezone.utc)  # after hours
    from tests.conftest import FakeLLM
    fake_llm = FakeLLM(script=[{"type": "text", "text": "Normal reply"}])

    result = handle_turn(
        db_session, lead, "Is the Civic available?",
        dealer_config=DEMO_CONFIG, fake_llm=fake_llm, now=now,
    )
    assert result["text"] == "Normal reply"
    assert lead.state == LeadState.ENGAGED  # not changed
    assert result.get("max_turns_reached") is None


def test_max_turns_triggers_handoff(db_session):
    """When inbound count >= MAX_INBOUND_TURNS and lead is ENGAGED, hand off."""
    dealer = Dealer(slug="max-turns-handoff", name="Test Dealer", config={})
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.SMS,
        name="Long Customer",
        phone="+1234567890",
        state=LeadState.ENGAGED,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    # Add MAX_INBOUND_TURNS inbound messages
    for i in range(MAX_INBOUND_TURNS):
        msg = Message(
            lead_id=lead.id,
            direction=Direction.INBOUND,
            channel=Channel.SMS,
            body=f"Question {i}",
        )
        db_session.add(msg)
    db_session.commit()

    now = datetime(2026, 6, 4, 4, 0, tzinfo=timezone.utc)  # after hours

    result = handle_turn(
        db_session, lead, "One more question",
        dealer_config=DEMO_CONFIG, now=now,
    )

    # Should get handoff message
    assert "sales rep" in result["text"].lower()
    assert result["mode"] == "send"
    assert result["max_turns_reached"] is True
    assert result["tools_used"] == []

    # Lead should be ASSIGNED
    assert lead.state == LeadState.ASSIGNED

    # Should have logged a LeadEvent
    event = db_session.query(LeadEvent).filter(
        LeadEvent.lead_id == lead.id,
        LeadEvent.type == "max_turns_reached",
    ).first()
    assert event is not None
    assert event.payload["inbound_count"] == MAX_INBOUND_TURNS


def test_max_turns_not_triggered_for_non_engaged_lead(db_session):
    """Max turns guard only fires for ENGAGED leads, not other states."""
    dealer = Dealer(slug="max-turns-other", name="Test Dealer", config={})
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.SMS,
        name="Customer",
        phone="+1234567890",
        state=LeadState.NEW,  # Not ENGAGED
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    # Add MAX_INBOUND_TURNS inbound messages
    for i in range(MAX_INBOUND_TURNS):
        msg = Message(
            lead_id=lead.id,
            direction=Direction.INBOUND,
            channel=Channel.SMS,
            body=f"Message {i}",
        )
        db_session.add(msg)
    db_session.commit()

    now = datetime(2026, 6, 4, 4, 0, tzinfo=timezone.utc)  # after hours
    from tests.conftest import FakeLLM
    fake_llm = FakeLLM(script=[{"type": "text", "text": "Normal reply"}])

    result = handle_turn(
        db_session, lead, "Hello?",
        dealer_config=DEMO_CONFIG, fake_llm=fake_llm, now=now,
    )

    # Should get normal reply, NOT handoff
    assert result["text"] == "Normal reply"
    assert lead.state == LeadState.NEW  # unchanged
    assert result.get("max_turns_reached") is None