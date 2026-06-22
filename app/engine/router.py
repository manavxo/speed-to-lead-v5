"""Round-robin lead assignment.

Picks the next active rep using a per-dealer pointer (Dealer.round_robin_pointer), pings them
via SMS to claim, and schedules an escalation timer. See workflows/escalation.md.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.lifecycle import transition
from app.models import Dealer, Lead, LeadEvent, LeadState

logger = logging.getLogger("speed-to-lead.router")


def next_rep(dealer: Dealer, sales_team: list[dict]) -> dict | None:
    """Return the next active rep in rotation and advance the dealer's pointer.

    Args:
        dealer: The dealer model instance (uses round_robin_pointer).
        sales_team: List of rep dicts with at least 'name', 'phone', 'active' keys.

    Returns:
        The next active rep dict, or None if no active reps.
    """
    active = [r for r in sales_team if r.get("active", True)]
    if not active:
        return None
    idx = dealer.round_robin_pointer % len(active)
    dealer.round_robin_pointer = (dealer.round_robin_pointer + 1) % len(active)
    return active[idx]


def assign_lead(
    session: Session,
    lead: Lead,
    dealer: Dealer,
    sales_team: list[dict],
    *,
    fake_twilio=None,
    sms_number: str | None = None,
    notify: bool = True,
    dealer_config: dict | None = None,
) -> Lead | None:
    """Assign `lead` to the next rep. Optionally ping them via notify_rep.

    When notify=False (used by book_appointment), the rep is assigned but
    NOT pinged with a claim message — the appointment notification handles that.

    If no active reps, the lead stays in current state (AI-only / after-hours path).
    """
    # Lock the dealer row so two leads ingested at the same moment can't read the
    # same round-robin pointer and both land on the same rep (fair distribution is
    # the core promise). with_for_update serializes this in Postgres; on SQLite it
    # is a harmless no-op (tests run single-threaded).
    locked_dealer = session.execute(
        select(Dealer).where(Dealer.id == dealer.id).with_for_update()
    ).scalar_one_or_none()
    if locked_dealer is not None:
        dealer = locked_dealer

    rep = next_rep(dealer, sales_team)
    if rep is None:
        logger.info("No active reps for lead#%s", lead.id)
        return None

    # Persist the pointer advancement (releases the row lock)
    session.commit()

    # Update the lead with the assigned rep
    lead.assigned_rep = rep["name"]
    session.commit()
    session.refresh(lead)

    if not notify:
        # Silent assignment — used by book_appointment. No state transition,
        # no claim ping. The appointment notification handles the rep alert.
        logger.info("Lead#%s silently assigned to %s (no notification)", lead.id, rep["name"])
        return rep

    # Transition to ASSIGNED and send claim ping
    if lead.state != LeadState.ASSIGNED:
        transition(
            session, lead, LeadState.ASSIGNED,
            reason="round_robin_assign",
            meta={"assigned_rep": rep["name"]},
        )
    else:
        # Reassignment (the lead was passed): it's already ASSIGNED, so a normal
        # transition is a no-op and the escalation timer would keep ticking from
        # the FIRST rep's assignment — yanking the lead from the new rep almost
        # immediately. Emit a fresh state_change event to reset that timer.
        session.add(LeadEvent(
            lead_id=lead.id,
            dealer_id=lead.dealer_id,
            type="state_change",
            payload={"from": "ASSIGNED", "to": "ASSIGNED",
                     "reason": "reassigned", "assigned_rep": rep["name"]},
            synced=False,
        ))
        lead.updated_at = datetime.now(timezone.utc)
        session.commit()

    # Ping the rep via the notify_rep chokepoint (default = Twilio WhatsApp).
    config = dealer_config or dealer.config or {}
    from tools.notify_rep import notify_rep
    result = notify_rep(
        session=session,
        rep_config=rep,
        lead=lead,
        message_type="claim",
        payload={
            "customer_name": lead.name or "Customer",
            "vehicle": lead.vehicle_ref or "",
        },
        dealer_config=config,
    )
    if not result.success:
        logger.warning(
            "Lead#%s assigned to %s but claim ping FAILED: %s (backend=%s)",
            lead.id, rep["name"], result.error, result.backend,
        )
    else:
        logger.info(
            "Lead#%s claim ping sent to %s via %s (sid=%s, dry_run=%s)",
            lead.id, rep["name"], result.backend, result.message_sid, result.dry_run,
        )

    logger.info("Lead#%s assigned to %s", lead.id, rep["name"])
    return rep


def handle_claim(
    session: Session,
    lead: Lead,
    rep_name: str,
) -> Lead:
    """Handle a rep's claim response (reply '1' to claim).

    Transitions ASSIGNED -> CLAIMED.
    Verifies the claiming rep matches lead.assigned_rep (if assigned).
    """
    if lead.assigned_rep and lead.assigned_rep != rep_name:
        raise ValueError(
            f"Lead is assigned to {lead.assigned_rep}, not {rep_name}. "
            f"Only {lead.assigned_rep} can claim this lead."
        )
    transition(
        session, lead, LeadState.CLAIMED,
        reason="rep_claimed",
        meta={"claimed_by": rep_name},
    )
    return lead


def handle_pass(
    session: Session,
    lead: Lead,
    dealer: Dealer,
    sales_team: list[dict],
    rep_name: str,
    *,
    fake_twilio=None,
    sms_number: str | None = None,
    max_pass_count: int = 3,
) -> Lead | None:
    """Handle a rep's pass response (reply '2' to pass).

    Tracks how many times the lead has been passed. After max_pass_count
    consecutive passes, escalates to the manager instead of looping.
    """
    lead.pass_count = (lead.pass_count or 0) + 1
    session.flush()

    if lead.pass_count >= max_pass_count:
        # Too many passes — escalate to manager instead of reassigning
        logger.warning(
            "Lead#%s passed %d times — escalating to manager", lead.id, lead.pass_count,
        )
        _escalate_to_manager(
            session, lead, dealer,
            reason=f"passed {lead.pass_count} times by reps",
            fake_twilio=fake_twilio,
            sms_number=sms_number,
        )
        return None

    return assign_lead(
        session, lead, dealer, sales_team,
        fake_twilio=fake_twilio,
        sms_number=sms_number,
    )


def _escalate_to_manager(
    session: Session,
    lead: Lead,
    dealer: Dealer,
    *,
    reason: str = "max_pass_count exceeded",
    fake_twilio=None,
    sms_number: str | None = None,
) -> None:
    """Escalate a lead to the dealer's manager after too many passes."""
    from app.engine.lifecycle import transition

    dealer_config = dealer.config or {}
    manager_phone = dealer_config.get("routing", {}).get("manager_phone")

    transition(
        session, lead, LeadState.ESCALATED,
        reason="max_pass_exceeded",
        meta={"pass_count": lead.pass_count, "reason": reason},
    )
    session.flush()

    if manager_phone:
        manager_msg = (
            f"Lead {lead.name or 'Customer'} ({lead.phone or lead.email or 'unknown'}) "
            f"has been passed {lead.pass_count} times. "
            f"Please review and assign manually."
        )
        try:
            # Per directive H.2.2: dealer-side notifications go through the
            # notify_rep chokepoint, not send_sms() directly. The manager is
            # modeled as a special "rep" with a phone and a default WhatsApp
            # backend; the abstraction is the bypass.
            from tools.notify_rep import notify_rep
            dealer_config = dealer.config or {}
            notify_rep(
                session=session,
                rep_config={
                    "name": "Manager",
                    "phone": manager_phone,
                    "active": True,
                    "notify_backend": "twilio_whatsapp",
                },
                lead=lead,
                message_type="escalation",
                payload={
                    "customer_name": lead.name or "Customer",
                    "reason": reason,
                },
                dealer_config=dealer_config,
            )
        except Exception:
            logger.exception("Failed to notify manager for lead#%s escalation", lead.id)
    else:
        logger.warning("No manager_phone configured for dealer %s — lead#%s escalated silently", dealer.slug, lead.id)
