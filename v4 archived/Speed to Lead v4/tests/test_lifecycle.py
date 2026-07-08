"""Phase 4 — lead lifecycle state machine. Runs today against the implemented transition table."""

from __future__ import annotations

import pytest

from app.engine.lifecycle import TRANSITIONS, can_transition, transition
from app.models import Channel, Dealer, Lead, LeadState


def test_happy_path_is_legal():
    path = [
        LeadState.NEW, LeadState.AUTO_REPLIED, LeadState.ASSIGNED, LeadState.CLAIMED,
        LeadState.ENGAGED, LeadState.APPT_SET, LeadState.SHOWED, LeadState.SOLD,
    ]
    for a, b in zip(path, path[1:]):
        assert can_transition(a, b), f"{a} -> {b} should be legal"


def test_terminal_states_have_no_exits():
    for terminal in (LeadState.SOLD, LeadState.LOST):
        assert TRANSITIONS[terminal] == set()


def test_opted_out_can_resubscribe():
    """OPTED_OUT -> NEW is the only allowed exit (START keyword resubscribe)."""
    assert TRANSITIONS[LeadState.OPTED_OUT] == {LeadState.NEW}
    assert can_transition(LeadState.OPTED_OUT, LeadState.NEW)


def test_opt_out_reachable_from_every_non_terminal_state():
    for state, nexts in TRANSITIONS.items():
        if state in (LeadState.SOLD, LeadState.LOST, LeadState.OPTED_OUT, LeadState.SHOWED):
            continue
        assert LeadState.OPTED_OUT in nexts, f"OPTED_OUT must be reachable from {state}"


@pytest.mark.parametrize("a,b", [
    (LeadState.NEW, LeadState.SOLD),
    (LeadState.AUTO_REPLIED, LeadState.SHOWED),
    (LeadState.SOLD, LeadState.NEW),
    (LeadState.LOST, LeadState.ENGAGED),
])
def test_illegal_transitions_are_rejected(a, b):
    assert not can_transition(a, b)


def test_unclaimed_lead_can_escalate():
    assert can_transition(LeadState.ASSIGNED, LeadState.ESCALATED)
    assert can_transition(LeadState.ESCALATED, LeadState.ASSIGNED)  # reassign to next rep


def test_transition_persists_and_creates_event(db_session):
    """transition() should update the lead state and create a LeadEvent."""
    dealer = Dealer(slug="test-dealer", name="Test", config={})
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.WEBFORM,
        name="Test Lead",
        phone="+16045551234",
        state=LeadState.NEW,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    event = transition(db_session, lead, LeadState.AUTO_REPLIED, reason="test_transition")

    assert lead.state == LeadState.AUTO_REPLIED
    assert event.type == "state_change"
    assert event.payload["from"] == "NEW"
    assert event.payload["to"] == "AUTO_REPLIED"
    assert event.lead_id == lead.id


def test_illegal_transition_raises(db_session):
    """Illegal transition should raise ValueError without modifying state."""
    dealer = Dealer(slug="test-dealer", name="Test", config={})
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.WEBFORM,
        name="Test Lead",
        state=LeadState.SOLD,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    with pytest.raises(ValueError, match="Illegal transition"):
        transition(db_session, lead, LeadState.NEW)

    assert lead.state == LeadState.SOLD  # unchanged