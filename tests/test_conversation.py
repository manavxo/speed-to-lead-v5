"""Phase 5 — AI conversation + business hours + appointment booking."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


def test_book_appointment_rejects_past_date(db_session):
    """Booking an appointment in the past should raise ValueError."""
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

    # 1 hour in the past
    past_time = datetime.now(timezone.utc) - timedelta(hours=1)

    with pytest.raises(ValueError, match="Cannot book appointment in the past"):
        book_appointment(db_session, lead, past_time)


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

    # Should have logged a LeadEvent via transition()
    event = db_session.query(LeadEvent).filter(
        LeadEvent.lead_id == lead.id,
        LeadEvent.type == "state_change",
    ).first()
    assert event is not None, "max-turns handoff should create a state_change LeadEvent"
    assert event.payload.get("reason") == "max_turns_reached"
    assert event.payload.get("inbound_count") == MAX_INBOUND_TURNS


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

# =========================================================================
# P0-11 REGRESSION TEST: conversation history loads the last 10 messages
# =========================================================================
# Bug history: v4's code review (docs/11-CODE-REVIEW.md) flagged this as a
# critical issue — the AI was single-turn only, sending only the latest
# customer message. The actual v4 code already had the fix (loads last 10
# messages in `_call_openrouter` around lines 786-799), but the v5 build
# must keep the fix. This test pins the behavior so a future refactor
# can't silently regress it.

def test_p0_11_conversation_history_loads_last_10_messages(db_session, monkeypatch):
    """The AI must see the last 10 messages, not just the latest one."""
    from app.engine import conversation as conv
    from tests.conftest import FakeLLM

    # Create a dealer + lead
    dealer = _make_dealer(db_session, "p0-11-dealer")
    lead = _make_lead(db_session, dealer, "p0-11-customer")
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    # Add 12 messages (alternating in/out, with the last being outbound) with
    # DISTINCT created_at timestamps. Without explicit timestamps, the default
    # factory gives all 12 messages the same created_at (microsecond precision,
    # loop is sub-microsecond), making ORDER BY DESC LIMIT 10 non-deterministic.
    for i in range(12):
        msg = Message(
            lead_id=lead.id,
            direction=Direction.INBOUND if i % 2 == 0 else Direction.OUTBOUND,
            channel=Channel.SMS,
            body=f"Message number {i}",
            created_at=datetime(2026, 6, 1, 12, 0, i, tzinfo=timezone.utc),
        )
        db_session.add(msg)
    db_session.commit()

    # Capture the messages passed to the LLM
    captured = {}
    real_call = conv._call_openrouter_with_retry

    def spy(client, **kwargs):
        captured["messages"] = kwargs.get("messages", [])
        return {"choices": [{"message": {"content": "OK"}}]}

    monkeypatch.setattr(conv, "_call_openrouter_with_retry", spy)
    monkeypatch.setattr(conv, "_get_openai_client", lambda: object())

    # Call _call_openrouter directly (current signature: system_prompt, user_message, *, session, lead, ...)
    conv._call_openrouter(
        system_prompt="You are a sales rep.",
        user_message="Final question?",
        session=db_session,
        lead=lead,
        dealer_config=DEMO_CONFIG,
    )

    # The AI should have received exactly 10 history messages (the most recent 10 from DB),
    # PLUS the current user message appended at the end. So total user/assistant = 11.
    # Filter out the current user message to verify just the history loaded from DB.
    sent_messages = captured["messages"]
    history = [m for m in sent_messages if m.get("role") in ("user", "assistant")]
    # The current user message ("Final question?") is the LAST item. Drop it to inspect
    # just the 10 history messages loaded from the DB.
    db_history = history[:-1]
    assert len(db_history) == 10, (
        f"P0-11 REGRESSION: expected exactly 10 history messages from DB, got {len(db_history)}. "
        f"The AI is single-turn again — this is the v4 bug we fixed."
    )
    # And the most recent message (Message number 11) must be in the history
    bodies = [m.get("content", "") for m in db_history]
    assert any("Message number 11" in b for b in bodies), (
        f"P0-11 REGRESSION: the most recent message must be in history. "
        f"Got bodies: {bodies}"
    )


# =========================================================================
# Helpers used by the P0-11 regression test
# =========================================================================
def _make_dealer(session, slug: str) -> Dealer:
    from app.models import Dealer
    dealer = Dealer(
        slug=slug,
        name=f"Test Dealer {slug}",
        config=DEMO_CONFIG,
    )
    session.add(dealer)
    session.commit()
    session.refresh(dealer)
    return dealer


def _make_lead(session, dealer: Dealer, name: str) -> Lead:
    from app.models import Lead
    return Lead(
        dealer_id=dealer.id,
        name=name,
        phone="+160****1234",
        source=Channel.SMS,
        state=LeadState.ENGAGED,
    )


# =========================================================================
# F0 — Model router: tool-critical intent detection + model routing
# =========================================================================

TOOL_CRITICAL_MESSAGES = [
    # Booking confirmations
    "yes, book it for Thursday at 2pm",
    "yeah sure, let's do Thursday",
    "okay, lock it in",
    "sounds great, schedule me for Monday",
    "sounds good — book me for tomorrow",
    "put me down for Wednesday 10am",
    "yes please, I'll take the 3pm slot",
    # Specific dates/times
    "Can I come in on Monday?",
    "how about next Saturday morning?",
    "is 2pm available on Thursday?",
    "I can do tomorrow around 3pm",
    # Availability inquiries
    "when can I come in for a test drive?",
    "what times are available this week?",
    "do you have any slots on Friday?",
    "what's available for test drives?",
    "any availability for a visit?",
    "I want to come see the car — when works?",
    # Inventory / spec questions
    "what engine does the Kona have?",
    "tell me about the Honda Civic",
    "what do you have in stock?",
    "what's in your inventory?",
    "what SUVs do you have?",
    "do you have any BMWs?",
    "show me what you've got under 30k",
    # Booking-qualified
    "can you book me a test drive?",
    "I'd like to schedule an appointment",
    "let's set something up for this week",
    "can you set up a test drive for me?",
]

NON_TOOL_MESSAGES = [
    "Hi there!",
    "thanks",
    "I'm just looking",
    "what's your name?",
    "cool, thanks for the info",
    "that sounds good, I'll think about it",
    "not right now, maybe later",
    "can you tell me more?",
    "how does this work?",
    "what's the process?",
    "I'm not sure yet",
    "that's interesting",
    "thanks but I'm going to shop around",
]


def test_f0_is_tool_critical_positive():
    """All booking/inventory intent messages should be detected as tool-critical."""
    from app.engine.conversation import _is_tool_critical_turn
    for msg in TOOL_CRITICAL_MESSAGES:
        assert _is_tool_critical_turn(msg), f"Expected tool-critical: {msg!r}"


def test_f0_is_tool_critical_negative():
    """Small talk and non-intent messages should NOT be tool-critical."""
    from app.engine.conversation import _is_tool_critical_turn
    for msg in NON_TOOL_MESSAGES:
        assert not _is_tool_critical_turn(msg), f"Expected NOT tool-critical: {msg!r}"


def test_f0_is_tool_critical_empty():
    """Empty/None input should be safe."""
    from app.engine.conversation import _is_tool_critical_turn
    assert not _is_tool_critical_turn("")
    assert not _is_tool_critical_turn(None)


def test_f0_router_selects_tool_model_for_booking_intent(db_session, monkeypatch):
    """When a tool-critical message is sent, _call_openrouter routes to TOOL_MODEL."""
    from app.engine import conversation as conv
    from app.config import settings

    # Capture the model passed to the API
    captured_model = []
    captured_tool_choice = []

    def fake_create(timeout=None, **kwargs):
        captured_model.append(kwargs.get("model"))
        captured_tool_choice.append(kwargs.get("tool_choice"))
        raise RuntimeError("stop after capturing params")

    monkeypatch.setattr(conv, "_call_openrouter_with_retry", fake_create)

    dealer = _make_dealer(db_session, "f0-router-tool")
    lead = _make_lead(db_session, dealer, "f0-customer")
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    try:
        conv._call_openrouter(
            system_prompt="You are a car dealer.",
            user_message="yes, book me for Thursday at 2pm",
            session=db_session, lead=lead,
            dealer_id=dealer.id, dealer_config=DEMO_CONFIG,
        )
    except RuntimeError:
        pass  # Expected — we raised to stop after capturing

    assert len(captured_model) > 0, "Model router did not call the API"
    assert captured_model[0] == settings.tool_model, (
        f"Expected TOOL_MODEL ({settings.tool_model}), got {captured_model[0]}"
    )
    assert captured_tool_choice[0] == "required", (
        f"Expected tool_choice='required', got {captured_tool_choice[0]!r}"
    )


def test_f0_router_uses_default_model_for_small_talk(db_session, monkeypatch):
    """Small talk messages should use the default DeepSeek model."""
    from app.engine import conversation as conv

    captured_model = []
    captured_tool_choice = []

    def fake_create(timeout=None, **kwargs):
        captured_model.append(kwargs.get("model"))
        captured_tool_choice.append(kwargs.get("tool_choice"))
        raise RuntimeError("stop after capturing params")

    monkeypatch.setattr(conv, "_call_openrouter_with_retry", fake_create)

    dealer = _make_dealer(db_session, "f0-router-default")
    lead = _make_lead(db_session, dealer, "f0-customer2")
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    try:
        conv._call_openrouter(
            system_prompt="You are a car dealer.",
            user_message="Hi there, just browsing!",
            session=db_session, lead=lead,
            dealer_id=dealer.id, dealer_config=DEMO_CONFIG,
        )
    except RuntimeError:
        pass

    assert len(captured_model) > 0, "Model router did not call the API"
    assert captured_tool_choice[0] == "auto", (
        f"Expected tool_choice='auto' for small talk, got {captured_tool_choice[0]!r}"
    )
