"""Lead lifecycle state machine (deterministic).

NEW -> AUTO_REPLIED -> ASSIGNED -> CLAIMED -> ENGAGED -> APPT_SET -> SHOWED -> SOLD | LOST
plus ESCALATED and OPTED_OUT. Every lead is always in exactly one state; routing, escalation,
and follow-ups are all transitions. Each transition appends a LeadEvent (which Axis-2 sinks mirror).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Lead, LeadEvent, LeadState

# Allowed transitions. Keep this the single source of truth for what can follow what.
TRANSITIONS: dict[LeadState, set[LeadState]] = {
    LeadState.NEW: {LeadState.AUTO_REPLIED, LeadState.OPTED_OUT},
    LeadState.AUTO_REPLIED: {LeadState.ASSIGNED, LeadState.ENGAGED, LeadState.OPTED_OUT},
    LeadState.ASSIGNED: {LeadState.CLAIMED, LeadState.ESCALATED, LeadState.ENGAGED, LeadState.OPTED_OUT},
    LeadState.ESCALATED: {LeadState.ASSIGNED, LeadState.CLAIMED, LeadState.ENGAGED, LeadState.OPTED_OUT},
    LeadState.CLAIMED: {LeadState.ENGAGED, LeadState.APPT_SET, LeadState.LOST, LeadState.OPTED_OUT},
    LeadState.ENGAGED: {LeadState.APPT_SET, LeadState.LOST, LeadState.OPTED_OUT},
    LeadState.APPT_SET: {LeadState.SHOWED, LeadState.LOST, LeadState.OPTED_OUT},
    LeadState.SHOWED: {LeadState.SOLD, LeadState.LOST},
    LeadState.SOLD: set(),
    LeadState.LOST: set(),
    LeadState.OPTED_OUT: {LeadState.NEW},  # resubscribe via START keyword
}


def can_transition(current: LeadState, target: LeadState) -> bool:
    return target in TRANSITIONS.get(current, set())


def transition(
    session: Session,
    lead: Lead,
    target: LeadState,
    *,
    reason: str | None = None,
    meta: dict | None = None,
) -> LeadEvent:
    """Move a Lead to `target`, validating the edge. Persists the change and appends a LeadEvent.

    Args:
        session: SQLAlchemy session.
        lead: The lead to transition.
        target: The desired new state.
        reason: Human-readable reason for the transition.
        meta: Extra data to store in the event payload.

    Returns:
        The created LeadEvent.

    Raises:
        ValueError: If the transition is illegal.
    """
    if not can_transition(lead.state, target):
        raise ValueError(f"Illegal transition {lead.state} -> {target}")

    old_state = lead.state
    lead.state = target
    lead.updated_at = datetime.now(timezone.utc)

    event = LeadEvent(
        lead_id=lead.id,
        dealer_id=lead.dealer_id,
        type="state_change",
        payload={
            "from": old_state.value,
            "to": target.value,
            "reason": reason,
            **(meta or {}),
        },
        synced=False,
    )
    session.add(event)
    session.commit()
    session.refresh(lead)
    session.refresh(event)
    return event