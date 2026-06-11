"""P1-3: state machine must fire notify_rep() on APPT_SET, ESCALATED, SOLD.

Per directive H.2.2: every dealer-side notification goes through the
notify_rep() chokepoint — NEVER call Twilio directly from engine code.
Task 1.1 + 1.2 wired the chokepoint + transport. This file locks in the
behaviour at the transition call sites:

  APPT_SET    — book_appointment() (was calling Twilio directly — bug)
  SOLD        — new mark_sold() function (didn't exist)
  ESCALATED   — router._escalate_to_manager (wired in Task 1.1, locking in)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.models import Channel, Dealer, Direction, Lead, LeadEvent, LeadState, Message


# --- Fixtures ----------------------------------------------------------------

@pytest.fixture
def sm_engine():
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
def sm_session(sm_engine):
    TestSession = sessionmaker(bind=sm_engine, expire_on_commit=False)
    session = TestSession()
    yield session
    session.close()


@pytest.fixture
def dealer_with_assigned_rep(sm_session):
    """Dealer with one rep ('Mike') configured for twilio_whatsapp notify."""
    dealer = Dealer(
        slug="sm-test",
        name="State Machine Test Dealer",
        sms_number="+177****0099",
        whatsapp_sender="+141****0099",
        config={
            "dealer": {"name": "State Machine Test Dealer", "timezone": "America/Vancouver"},
            "channels": {
                "sms_number": "+177****0099",
                "whatsapp_sender": "+141****0099",
            },
            "sales_team": [
                {
                    "name": "Mike",
                    "phone": "+160****4001",
                    "active": True,
                    "notify_backend": "twilio_whatsapp",
                    "notify_template_sid": "HXxxxxxx",
                },
            ],
        },
    )
    sm_session.add(dealer)
    sm_session.commit()
    sm_session.refresh(dealer)
    return dealer


def _make_lead(session, dealer, *, state=LeadState.CLAIMED, assigned_rep="Mike"):
    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.SMS,
        name="Test Customer",
        phone="+160****4999",
        vehicle_ref="2019 Honda Civic",
        state=state,
        assigned_rep=assigned_rep,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return lead


# --- APPT_SET: book_appointment must call notify_rep -------------------------

def test_book_appointment_calls_notify_rep_for_appointment_set(
    sm_session, dealer_with_assigned_rep, monkeypatch
):
    """book_appointment() must route the rep notification through notify_rep
    (not call twilio.rest.Client directly). This is the directive H.2.2 rule.
    """
    from tools.book_appointment import book_appointment

    lead = _make_lead(sm_session, dealer_with_assigned_rep, state=LeadState.CLAIMED)

    notify_calls: list[dict] = []
    # Spy on the notify_rep chokepoint. The function under test imports
    # `from tools.notify_rep import notify_rep` lazily inside
    # _notify_rep_of_appointment, so patch at the source module.
    def fake_notify_rep(*, session, rep_config, lead, message_type, payload, dealer_config):
        notify_calls.append({
            "rep_config": dict(rep_config),
            "message_type": message_type,
            "payload": dict(payload),
        })
        from tools.notify_rep import NotificationResult
        return NotificationResult(
            success=True, backend="twilio_whatsapp",
            message_sid="FAKE_WA_SID", dry_run=True,
        )

    monkeypatch.setattr("tools.notify_rep.notify_rep", fake_notify_rep)

    appt_time = datetime.now(timezone.utc) + timedelta(days=1)
    book_appointment(
        sm_session, lead, appt_time,
        notes="Test drive",
        dealer_config=dealer_with_assigned_rep.config,
    )

    # Lead transitioned
    assert lead.state == LeadState.APPT_SET

    # notify_rep was called once with the right message_type
    assert len(notify_calls) == 1, f"expected 1 notify_rep call, got {len(notify_calls)}"
    call = notify_calls[0]
    assert call["message_type"] == "appointment_set"
    assert call["rep_config"]["name"] == "Mike"
    assert call["rep_config"]["phone"] == "+160****4001"
    assert call["rep_config"]["notify_backend"] == "twilio_whatsapp"
    # Payload must carry the appointment time + customer context
    assert "scheduled_for" in call["payload"]
    assert call["payload"]["customer_name"] == "Test Customer"
    assert "Honda Civic" in call["payload"]["vehicle"]


# --- SOLD: mark_sold() must transition + notify_rep -------------------------

def test_mark_sold_transitions_showed_to_sold_and_notifies_rep(
    sm_session, dealer_with_assigned_rep, monkeypatch
):
    """mark_sold() transitions SHOWED -> SOLD and fires notify_rep with
    message_type='sale'. The rep gets the commission ping through the
    dealer-side chokepoint (default WhatsApp).
    """
    from tools.book_appointment import mark_sold

    lead = _make_lead(sm_session, dealer_with_assigned_rep, state=LeadState.SHOWED)

    notify_calls: list[dict] = []
    def fake_notify_rep(*, session, rep_config, lead, message_type, payload, dealer_config):
        notify_calls.append({"message_type": message_type, "payload": dict(payload)})
        from tools.notify_rep import NotificationResult
        return NotificationResult(
            success=True, backend="twilio_whatsapp",
            message_sid="FAKE_SALE_SID", dry_run=True,
        )
    monkeypatch.setattr("tools.notify_rep.notify_rep", fake_notify_rep)

    appt_time = datetime.now(timezone.utc)  # the showed appt
    mark_sold(
        sm_session, lead, appt_time,
        dealer_config=dealer_with_assigned_rep.config,
    )

    # State transitioned
    assert lead.state == LeadState.SOLD

    # notify_rep fired with message_type='sale'
    assert len(notify_calls) == 1
    call = notify_calls[0]
    assert call["message_type"] == "sale"
    assert call["payload"]["customer_name"] == "Test Customer"
    assert "Honda Civic" in call["payload"]["vehicle"]


def test_mark_sold_rejects_lead_not_in_showed_state(
    sm_session, dealer_with_assigned_rep
):
    """State machine guard: mark_sold() only valid from SHOWED. Anything
    else must raise ValueError so the lifecycle TRANSITIONS table stays
    the single source of truth.
    """
    from tools.book_appointment import mark_sold

    # CLAIMED -> SOLD is illegal (lifecycle edge doesn't exist)
    lead = _make_lead(sm_session, dealer_with_assigned_rep, state=LeadState.CLAIMED)

    with pytest.raises(ValueError, match="Illegal transition"):
        mark_sold(
            sm_session, lead, datetime.now(timezone.utc),
            dealer_config=dealer_with_assigned_rep.config,
        )

    # State unchanged
    assert lead.state == LeadState.CLAIMED

def test_notify_rep_sale_message_type_body_template():
    """The 'sale' body template mentions the sale (not just the customer).
    The generic fallback is "update on <customer>" — that would pass
    a naive substring test on 'Jane Doe'. Asserting the word "sold"
    (case-insensitive) locks the sale-specific template in.
    """
    from tools.notify_rep import _build_body
    body = _build_body(
        "sale",
        {"customer_name": "Jane Doe", "vehicle": "2021 Toyota RAV4"},
        "Mike",
    )
    assert "Mike" in body
    assert "Jane Doe" in body
    assert "2021 Toyota RAV4" in body
    # Sale-specific marker — generic fallback says "update on X", not "sold X".
    assert "sold" in body.lower(), f"sale body must mention 'sold', got: {body!r}"
    # Must be terse — the rep is reading this on a phone, between other things.
    assert len(body) < 200, f"sale body too long ({len(body)} chars): {body!r}"


# --- ESCALATED: lock in Task 1.1 behaviour ----------------------------------

def test_escalation_calls_notify_rep_with_escalation_message_type(
    sm_session, dealer_with_assigned_rep, monkeypatch
):
    """router._escalate_to_manager must fire notify_rep with
    message_type='escalation'. Locks in the Task 1.1 wiring so it
    can't silently regress to a direct SMS.
    """
    from app.engine.router import handle_pass

    # Need a manager_phone in the dealer config for escalation to fire
    dealer_with_assigned_rep.config["routing"] = {"manager_phone": "+160****9000"}
    sm_session.commit()

    lead = _make_lead(
        sm_session, dealer_with_assigned_rep,
        state=LeadState.ASSIGNED, assigned_rep="Mike",
    )
    # Pre-set pass_count to max_pass_count-1 so the next pass triggers escalation
    lead.pass_count = 2
    sm_session.commit()

    notify_calls: list[dict] = []
    def fake_notify_rep(*, session, rep_config, lead, message_type, payload, dealer_config):
        notify_calls.append({
            "rep_config": dict(rep_config),
            "message_type": message_type,
            "payload": dict(payload),
        })
        from tools.notify_rep import NotificationResult
        return NotificationResult(
            success=True, backend="twilio_whatsapp",
            message_sid="FAKE_ESC_SID", dry_run=True,
        )
    monkeypatch.setattr("tools.notify_rep.notify_rep", fake_notify_rep)

    sales_team = dealer_with_assigned_rep.config["sales_team"]
    handle_pass(
        sm_session, lead, dealer_with_assigned_rep, sales_team,
        rep_name="Mike", max_pass_count=3,
    )

    # Lead escalated
    assert lead.state == LeadState.ESCALATED

    # notify_rep called once with message_type='escalation' to the manager
    assert len(notify_calls) == 1
    call = notify_calls[0]
    assert call["message_type"] == "escalation"
    assert call["rep_config"]["phone"] == "+160****9000"
    assert call["rep_config"]["name"] == "Manager"
