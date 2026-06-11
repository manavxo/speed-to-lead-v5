"""Tool (AI-callable): book a test-drive/visit appointment for a lead.

Creates an Appointment, transitions the lead to APPT_SET, schedules reminder texts, and notifies
the assigned rep. The conversation's primary goal.

State machine notifications (APPT_SET, SOLD) route through tools.notify_rep —
NEVER call twilio.rest.Client directly from this file. Per directive H.2.2.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.engine.lifecycle import transition
from app.models import Appointment, Lead, LeadEvent, LeadState

logger = logging.getLogger("speed-to-lead.book_appointment")


def _notify_rep_via_chokepoint(
    session: Session,
    lead: Lead,
    *,
    message_type: str,
    payload: dict,
    dealer_config: dict | None,
) -> None:
    """Find the assigned rep's config and dispatch via notify_rep().

    Single chokepoint for every rep-targeted notification in this module
    (APPT_SET, SOLD). Per directive H.2.2: never call Twilio directly from
    engine/tool code — always go through notify_rep so backends stay
    swappable and DRYRUN/logging/persistence is consistent.

    Fire-and-forget: any failure inside notify_rep is logged but not
    raised. The appointment / sale is still recorded.
    """
    if not dealer_config:
        logger.info("No dealer config — skipping %s notification for lead#%s",
                    message_type, lead.id)
        return

    sales_team = dealer_config.get("sales_team", [])
    rep_config: dict | None = None
    rep_name = lead.assigned_rep
    if rep_name and sales_team:
        for rep in sales_team:
            if rep.get("name", "").lower() == rep_name.lower():
                # Copy so we don't mutate the dealer's config in place
                rep_config = dict(rep)
                break

    if not rep_config:
        # Fall back to the dealership main phone. SMS backend — main numbers
        # usually can't do WhatsApp unless explicitly provisioned.
        main_phone = (
            dealer_config.get("dealer", {}).get("main_phone", "")
            or dealer_config.get("channels", {}).get("sms_number", "")
        )
        if not main_phone:
            logger.warning(
                "No rep or main phone for %s notification on lead#%s",
                message_type, lead.id,
            )
            return
        rep_config = {
            "name": "Dealership",
            "phone": main_phone,
            "active": True,
            "notify_backend": "sms",
        }

    from tools.notify_rep import notify_rep
    try:
        notify_rep(
            session=session,
            rep_config=rep_config,
            lead=lead,
            message_type=message_type,
            payload=payload,
            dealer_config=dealer_config,
        )
    except Exception:
        # Defence-in-depth — notify_rep already catches transport errors and
        # returns NotificationResult(success=False). If something escapes
        # (e.g. programmer error in the chokepoint itself), we still don't
        # want the booking to fail.
        logger.exception(
            "notify_rep escaped for %s on lead#%s (fire-and-forget swallowed)",
            message_type, lead.id,
        )


def _notify_rep_of_appointment(
    session: Session,
    lead: Lead,
    scheduled_for: datetime,
    *,
    notes: str | None = None,
    dealer_config: dict | None = None,
) -> None:
    """Send an APPT_SET notification to the assigned rep (or dealership main
    phone) about a new appointment. Fire-and-forget — appointment is still
    booked even if notification fails.

    This is now a thin wrapper around _notify_rep_via_chokepoint so the
    chokepoint stays the only caller of Twilio in this module.
    """
    _notify_rep_via_chokepoint(
        session, lead,
        message_type="appointment_set",
        payload={
            "customer_name": lead.name or "A customer",
            "vehicle": lead.vehicle_ref or "",
            "scheduled_for": scheduled_for.isoformat(),
            "notes": notes or "",
        },
        dealer_config=dealer_config,
    )


def book_appointment(
    session: Session,
    lead: Lead,
    scheduled_for: datetime,
    *,
    notes: str | None = None,
    dealer_config: dict | None = None,
) -> Appointment:
    """Create the appointment + transition + reminders + notify rep. Returns the Appointment.

    Args:
        session: SQLAlchemy session.
        lead: The lead to book for (must be in CLAIMED, ENGAGED, AUTO_REPLIED, or NEW state).
        scheduled_for: When the appointment is scheduled.
        notes: Optional notes about the appointment (e.g., vehicle interest, test drive).
        dealer_config: Optional dealer config dict for sending rep notifications.

    Returns:
        The created Appointment.

    Raises:
        ValueError: If the lead is not in a bookable state.
    """
    if lead.state not in (LeadState.CLAIMED, LeadState.ENGAGED, LeadState.AUTO_REPLIED, LeadState.NEW):
        raise ValueError(
            f"Cannot book appointment for lead in state {lead.state}. "
            f"Lead must be CLAIMED, ENGAGED, AUTO_REPLIED, or NEW."
        )

    appt = Appointment(
        lead_id=lead.id,
        dealer_id=lead.dealer_id,
        scheduled_for=scheduled_for,
        status="set",
    )
    session.add(appt)
    session.commit()
    session.refresh(appt)

    transition(
        session, lead, LeadState.APPT_SET,
        reason="appointment_booked",
        meta={
            "appointment_id": appt.id,
            "scheduled_for": scheduled_for.isoformat(),
            "notes": notes,
        },
    )

    event = LeadEvent(
        lead_id=lead.id,
        dealer_id=lead.dealer_id,
        type="appointment",
        payload={
            "appointment_id": appt.id,
            "scheduled_for": scheduled_for.isoformat(),
            "status": "set",
            "notes": notes,
        },
        synced=False,
    )
    session.add(event)
    session.commit()

    # Notify the assigned rep (or dealership) about the new appointment
    _notify_rep_of_appointment(
        session, lead, scheduled_for,
        notes=notes,
        dealer_config=dealer_config,
    )

    return appt


def confirm_appointment(session: Session, appt: Appointment) -> Appointment:
    appt.status = "confirmed"
    session.commit()
    session.refresh(appt)
    return appt


def mark_showed(session: Session, appt: Appointment, lead: Lead) -> Appointment:
    appt.status = "showed"
    session.commit()
    session.refresh(appt)
    if lead.state == LeadState.APPT_SET:
        transition(session, lead, LeadState.SHOWED, reason="showed_up")
    return appt


def mark_no_show(session: Session, appt: Appointment) -> Appointment:
    appt.status = "no_show"
    session.commit()
    session.refresh(appt)
    return appt


def cancel_appointment(session: Session, appt: Appointment) -> Appointment:
    appt.status = "cancelled"
    session.commit()
    session.refresh(appt)
    return appt


def mark_sold(
    session: Session,
    lead: Lead,
    sold_at: datetime,
    *,
    dealer_config: dict | None = None,
) -> Lead:
    """Mark a lead as SOLD. Transitions SHOWED -> SOLD and notifies the
    assigned rep through the notify_rep() chokepoint.

    The state transition is guarded by the lifecycle TRANSITIONS table
    (only legal from SHOWED). On illegal state, raises ValueError.

    Args:
        session: SQLAlchemy session.
        lead: The lead to mark as sold (must be in SHOWED).
        sold_at: When the sale closed.
        dealer_config: Optional dealer config for rep notification.

    Returns:
        The Lead (now in SOLD state).
    """
    # Lifecycle guard — raises ValueError on illegal transition
    transition(
        session, lead, LeadState.SOLD,
        reason="sale_closed",
        meta={"sold_at": sold_at.isoformat()},
    )

    # Notify the rep via the chokepoint (fire-and-forget)
    _notify_rep_via_chokepoint(
        session, lead,
        message_type="sale",
        payload={
            "customer_name": lead.name or "A customer",
            "vehicle": lead.vehicle_ref or "",
        },
        dealer_config=dealer_config,
    )

    return lead
