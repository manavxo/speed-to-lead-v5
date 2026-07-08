"""Tool (AI-callable): book a test-drive/visit appointment for a lead.

Creates an Appointment, transitions the lead to APPT_SET, schedules reminder texts, and notifies
the assigned rep. The conversation's primary goal.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.engine.lifecycle import transition
from app.models import Appointment, Lead, LeadEvent, LeadState

logger = logging.getLogger("speed-to-lead.book_appointment")


def _notify_rep_of_appointment(
    lead: Lead,
    scheduled_for: datetime,
    *,
    notes: str | None = None,
    dealer_config: dict | None = None,
) -> None:
    """Send an SMS notification to the assigned rep (or dealership main phone) about a new appointment.

    This is a fire-and-forget notification — if it fails, the appointment is still booked.
    """
    if not dealer_config:
        logger.info("No dealer config — skipping appointment notification")
        return

    # Find the notification target: assigned rep's phone, or dealership main phone
    sales_team = dealer_config.get("sales_team", [])
    main_phone = dealer_config.get("dealer", {}).get("main_phone", "")
    sms_number = dealer_config.get("channels", {}).get("sms_number", "")
    dealer_name = dealer_config.get("dealer", {}).get("name", "Dealership")

    # Try to find the assigned rep's phone from the sales team
    rep_phone = None
    rep_name = lead.assigned_rep
    if rep_name and sales_team:
        for rep in sales_team:
            if rep.get("name", "").lower() == rep_name.lower():
                rep_phone = rep.get("phone") or rep.get("whatsapp") or ""
                break

    # Fall back to dealership main phone
    notify_to = rep_phone or main_phone or sms_number
    if not notify_to:
        logger.warning("No notification phone available for appointment on lead#%s", lead.id)
        return

    # Build the notification message
    appt_time = scheduled_for.strftime("%A, %B %d at %I:%M %p")
    customer_name = lead.name or "A customer"
    customer_phone = lead.phone or "no phone on file"

    msg_parts = [
        f"📅 NEW APPOINTMENT — {dealer_name}",
        "",
        f"Customer: {customer_name}",
        f"Phone: {customer_phone}",
        f"When: {appt_time}",
    ]
    if lead.assigned_rep:
        msg_parts.append(f"Rep: {lead.assigned_rep}")
    if notes:
        msg_parts.append(f"Notes: {notes}")
    if lead.vehicle_ref:
        msg_parts.append(f"Vehicle: {lead.vehicle_ref}")

    msg_parts.extend([
        "",
        "This appointment was booked by the AI assistant.",
        "Please confirm with the customer if needed.",
    ])

    body = "\n".join(msg_parts)

    # Send via Twilio directly — this is an internal notification to the dealership,
    # not a customer-facing message, so we bypass opt-out/consent/quiet-hours checks.
    try:
        from app.config import settings

        if not settings.outbound_enabled:
            logger.info("DRY-RUN appointment notification to %s: %s", notify_to, body[:80])
            return

        from_number = sms_number or main_phone
        if not from_number:
            logger.warning("No from_number for appointment notification")
            return

        from twilio.rest import Client as TwilioClient
        client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
        msg = client.messages.create(to=notify_to, from_=from_number, body=body)
        logger.info("Appointment notification sent to %s (SID=%s) for lead#%s", notify_to, msg.sid, lead.id)
    except Exception:
        logger.exception("Failed to send appointment notification for lead#%s", lead.id)


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
        lead, scheduled_for,
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
