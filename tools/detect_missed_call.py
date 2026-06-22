"""Missed-call detection and SMS follow-up trigger.

This tool handles the logic for detecting missed calls and triggering
SMS follow-up conversations. Supports three detection modes:

- always_on: All calls forwarded to Twilio 24/7
- time_based: Forwarding only during off-hours
- voicemail_notify: Carrier voicemail notification parsing

Usage:
    from tools.detect_missed_call import handle_missed_call

    result = handle_missed_call(
        session=session,
        dealer=dealer,
        caller_phone="+160****2870",
        call_sid="CA1234567890",
        call_status="no-answer",
    )
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Channel, Direction, Lead, LeadState, Message

logger = logging.getLogger(__name__)


class MissedCallResult:
    """Result of handling a missed call."""

    def __init__(
        self,
        success: bool,
        lead_id: Optional[int] = None,
        message_sid: Optional[str] = None,
        error: Optional[str] = None,
    ):
        self.success = success
        self.lead_id = lead_id
        self.message_sid = message_sid
        self.error = error

    def __repr__(self):
        if self.success:
            return f"MissedCallResult(success=True, lead_id={self.lead_id}, sid={self.message_sid})"
        return f"MissedCallResult(success=False, error={self.error})"


def handle_missed_call(
    *,
    session: Session,
    dealer,  # Dealer model instance
    caller_phone: str,
    call_sid: str,
    call_status: str,
    call_duration: int = 0,
    sms_sender=None,  # Injectable for testing: sms_sender(to, from_, body) -> sid
) -> MissedCallResult:
    """Handle a missed call by creating a lead and sending SMS follow-up.

    Args:
        session: Database session
        dealer: Dealer model instance
        caller_phone: Customer's phone number (From)
        call_sid: Twilio CallSid for dedup
        call_status: Twilio CallStatus (no-answer, busy, failed, completed)
        call_duration: Call duration in seconds (0 for no-answer)
        sms_sender: Injectable SMS sender function (for testing)

    Returns:
        MissedCallResult with success status and lead_id or error
    """
    # Only handle missed calls
    if call_status not in ("no-answer", "busy", "failed"):
        return MissedCallResult(
            success=False,
            error=f"Call status '{call_status}' is not a missed call",
        )

    # Dedup: skip if a missed-call Lead exists for this number within the last
    # 24 hours (catches both duplicate Twilio webhook deliveries AND repeat
    # callers on the same day). Beyond 24h, allow a fresh lead so repeat callers
    # on different days get a new text-back.
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    existing = session.query(Lead).filter(
        Lead.dealer_id == dealer.id,
        Lead.phone == caller_phone,
        Lead.source == Channel.PHONE,
        Lead.created_at >= cutoff,
    ).first()

    if existing:
        logger.info(
            "Missed call from %s: lead#%s exists within 24h (created %s) — skipping",
            caller_phone, existing.id, existing.created_at,
        )
        return MissedCallResult(
            success=False,
            error=f"Lead already exists for {caller_phone} within 24h window",
        )

    # Create lead
    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.PHONE,
        name="",  # Unknown from call alone
        phone=caller_phone,
        state=LeadState.NEW,
    )
    session.add(lead)
    session.flush()  # Get lead.id

    # Build text-back message
    dealer_config = dealer.config or {}
    dealer_name = dealer_config.get("dealer", {}).get("name", "us")
    main_phone = dealer_config.get("dealer", {}).get("main_phone", "")

    text_body = (
        f"Hi! We missed your call to {dealer_name}. "
        f"Text us here and we'll get back to you ASAP!"
    )
    if main_phone:
        text_body += f" Or call us back at {main_phone}."

    # After-hours: don't text back in the middle of the night (quiet hours would
    # drop it silently). Queue the text-back for the morning sweep instead so the
    # caller still gets a follow-up first thing — just not at 2am.
    from tools.route_lead import is_after_hours, queue_morning_followup
    if is_after_hours(dealer_config):
        lead.state = LeadState.AUTO_REPLIED
        queue_morning_followup(session, lead, text_body, reason="missed_call_after_hours")
        session.commit()
        session.refresh(lead)
        logger.info("Missed call after-hours: lead %d text-back queued for morning", lead.id)
        return MissedCallResult(success=True, lead_id=lead.id, message_sid=None)

    # Send SMS
    sms_sid = None
    if sms_sender:
        try:
            sms_sid = sms_sender(
                to=caller_phone,
                from_=dealer.sms_number,
                body=text_body,
            )
        except Exception as e:
            logger.error("Failed to send missed-call SMS: %s", e)
            # Don't fail the whole operation — lead is still created

    # Log the outbound message
    msg = Message(
        lead_id=lead.id,
        direction=Direction.OUTBOUND,
        channel=Channel.SMS,
        body=text_body,
        provider_sid=sms_sid,
    )
    session.add(msg)

    # Transition lead
    lead.state = LeadState.AUTO_REPLIED
    session.commit()
    session.refresh(lead)

    logger.info(
        "Missed call handled: lead %d, SMS sent to %s, sid=%s",
        lead.id,
        caller_phone,
        sms_sid,
    )

    return MissedCallResult(
        success=True,
        lead_id=lead.id,
        message_sid=sms_sid,
    )


def handle_missed_call_from_webhook(
    *,
    session: Session,
    payload: dict,
    sms_sender=None,
) -> MissedCallResult:
    """Handle a missed call from Twilio webhook payload.

    This is the entry point for the webhook handler. It parses the
    Twilio payload and calls handle_missed_call.

    Args:
        session: Database session
        payload: Twilio webhook payload dict
        sms_sender: Injectable SMS sender function

    Returns:
        MissedCallResult
    """
    from app.main import _find_dealer_by_sms

    from_number = payload.get("From", "")
    to_number = payload.get("To", "")
    call_status = payload.get("CallStatus", "")
    call_sid = payload.get("CallSid", "")
    call_duration = int(payload.get("CallDuration", 0))

    # Find dealer by the Twilio number that was called
    dealer = _find_dealer_by_sms(session, to_number)
    if not dealer:
        return MissedCallResult(
            success=False,
            error=f"No dealer found for number {to_number}",
        )

    return handle_missed_call(
        session=session,
        dealer=dealer,
        caller_phone=from_number,
        call_sid=call_sid,
        call_status=call_status,
        call_duration=call_duration,
        sms_sender=sms_sender,
    )
