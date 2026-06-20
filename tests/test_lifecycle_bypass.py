"""1.2: Greeting-only / qualify-only / max-turns lifecycle bypass tests.

The greeting_only mode in conversation.py sets lead.state = LeadState.ASSIGNED
directly without using transition(). This bypasses LeadEvent logging.

Also fixes qualify_only and max_turns_reached which have the same problem.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.models import Channel, Dealer, Lead, LeadEvent, LeadState


@pytest.fixture
def lifecycle_engine():
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
def lifecycle_session(lifecycle_engine):
    Session = sessionmaker(bind=lifecycle_engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def greeting_dealer(lifecycle_session):
    """Dealer configured for greeting_only engagement."""
    dealer = Dealer(
        slug="greeting-test",
        name="Greeting Test Auto",
        sms_number="+17781234567",
        config={
            "dealer": {"name": "Greeting Test Auto", "timezone": "America/Vancouver"},
            "ai": {"engagement_mode": "greeting_only"},
            "channels": {"sms_number": "+17781234567"},
        },
    )
    lifecycle_session.add(dealer)
    lifecycle_session.commit()
    lifecycle_session.refresh(dealer)
    return dealer


@pytest.fixture
def qualify_dealer(lifecycle_session):
    """Dealer configured for qualify_only engagement."""
    dealer = Dealer(
        slug="qualify-test",
        name="Qualify Test Auto",
        sms_number="+17781234568",
        config={
            "dealer": {"name": "Qualify Test Auto", "timezone": "America/Vancouver"},
            "ai": {"engagement_mode": "qualify_only"},
            "channels": {"sms_number": "+17781234568"},
        },
    )
    lifecycle_session.add(dealer)
    lifecycle_session.commit()
    lifecycle_session.refresh(dealer)
    return dealer


@pytest.fixture
def full_auto_dealer(lifecycle_session):
    """Dealer configured for full_auto engagement (for max-turns tests)."""
    dealer = Dealer(
        slug="full-auto-test",
        name="Full Auto Test",
        sms_number="+17781234569",
        config={
            "dealer": {"name": "Full Auto Test", "timezone": "America/Vancouver"},
            "ai": {"engagement_mode": "full_auto"},
            "channels": {"sms_number": "+17781234569"},
        },
    )
    lifecycle_session.add(dealer)
    lifecycle_session.commit()
    lifecycle_session.refresh(dealer)
    return dealer


def _create_lead(session, dealer, *, state=LeadState.AUTO_REPLIED, phone="+16045550001"):
    """Helper to create a test lead."""
    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.SMS,
        name="Test Customer",
        phone=phone,
        state=state,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return lead


def _add_inbound_count(session, lead, count=1):
    """Add inbound messages to a lead to simulate conversation history."""
    from app.models import Direction, Message
    for i in range(count):
        msg = Message(
            lead_id=lead.id,
            direction=Direction.INBOUND,
            channel=Channel.SMS,
            body=f"Test message {i + 1}",
            provider_sid=f"SM_lifecycle_test_{lead.id}_{i}",
        )
        session.add(msg)
    session.commit()


# ---------------------------------------------------------------------------
# Tests: greeting_only mode
# ---------------------------------------------------------------------------

def test_greeting_only_transitions_via_lifecycle(lifecycle_session, greeting_dealer):
    """greeting_only should use transition() so LeadEvent is created."""
    from app.engine.conversation import handle_turn

    lead = _create_lead(lifecycle_session, greeting_dealer, state=LeadState.AUTO_REPLIED)
    _add_inbound_count(lifecycle_session, lead, count=1)

    result = handle_turn(
        lifecycle_session,
        lead,
        "I'm looking for a car",
        dealer_config=greeting_dealer.config,
    )

    lead = lifecycle_session.get(Lead, lead.id)
    assert lead.state == LeadState.ASSIGNED

    # Verify a LeadEvent was created via transition()
    events = lifecycle_session.query(LeadEvent).filter(
        LeadEvent.lead_id == lead.id,
        LeadEvent.type == "state_change",
    ).all()
    assert len(events) >= 1, "greeting_only should create a LeadEvent via transition()"
    # The payload should contain the from/to/reason breadcrumb
    last_event = events[-1]
    assert last_event.payload.get("to") == "ASSIGNED"


def test_greeting_only_lead_event_reason(lifecycle_session, greeting_dealer):
    """greeting_only transition should include a meaningful reason."""
    from app.engine.conversation import handle_turn

    lead = _create_lead(lifecycle_session, greeting_dealer, state=LeadState.AUTO_REPLIED)
    _add_inbound_count(lifecycle_session, lead, count=1)

    handle_turn(
        lifecycle_session,
        lead,
        "Hi",
        dealer_config=greeting_dealer.config,
    )

    events = lifecycle_session.query(LeadEvent).filter(
        LeadEvent.lead_id == lead.id,
        LeadEvent.type == "state_change",
    ).all()
    reason = events[-1].payload.get("reason", "")
    assert "greeting" in reason.lower(), f"Expected greeting-related reason, got: {reason}"


# ---------------------------------------------------------------------------
# Tests: qualify_only mode (after 3+ turns, handoff)
# ---------------------------------------------------------------------------

def test_qualify_only_handoff_creates_lead_event(lifecycle_session, qualify_dealer):
    """qualify_only handoff (3+ turns) should use transition()."""
    from app.engine.conversation import handle_turn

    lead = _create_lead(lifecycle_session, qualify_dealer, state=LeadState.ENGAGED)
    _add_inbound_count(lifecycle_session, lead, count=3)

    result = handle_turn(
        lifecycle_session,
        lead,
        "I want to know more",
        dealer_config=qualify_dealer.config,
    )

    lifecycle_session.expire_all()
    lead = lifecycle_session.get(Lead, lead.id)
    assert lead.state == LeadState.ASSIGNED, f"Expected ASSIGNED, got {lead.state}"

    events = lifecycle_session.query(LeadEvent).filter(
        LeadEvent.lead_id == lead.id,
        LeadEvent.type == "state_change",
    ).all()
    assert len(events) >= 1, "qualify_only handoff should create a LeadEvent"


# ---------------------------------------------------------------------------
# Tests: max-turns handoff
# ---------------------------------------------------------------------------

def test_max_turns_handoff_creates_lead_event(lifecycle_session, full_auto_dealer):
    """Max-turns handoff (ENGAGED -> ASSIGNED) should use transition()."""
    from app.engine.conversation import handle_turn

    lead = _create_lead(lifecycle_session, full_auto_dealer, state=LeadState.ENGAGED)
    # Add enough messages to exceed MAX_INBOUND_TURNS
    from app.engine.conversation import MAX_INBOUND_TURNS
    _add_inbound_count(lifecycle_session, lead, count=MAX_INBOUND_TURNS + 1)

    result = handle_turn(
        lifecycle_session,
        lead,
        "I'm still interested",
        dealer_config=full_auto_dealer.config,
    )

    lifecycle_session.expire_all()
    lead = lifecycle_session.get(Lead, lead.id)
    assert lead.state == LeadState.ASSIGNED, f"Expected ASSIGNED, got {lead.state}"

    events = lifecycle_session.query(LeadEvent).filter(
        LeadEvent.lead_id == lead.id,
        LeadEvent.type == "state_change",
    ).all()
    assert len(events) >= 1, "max-turns handoff should create a LeadEvent"
