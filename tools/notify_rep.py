"""Single chokepoint for dealer-side notifications.

Per directive H.2.2 (locked in 2026-06-09): the system contacts the dealer via
WhatsApp (not SMS) for rep claim pings, escalations, appointment confirmations,
and missed-call handoffs. This module is THE chokepoint that all engine modules
call for any rep-targeted message. The backend is configurable per rep:

- twilio_whatsapp (default): pre-approved Twilio WhatsApp template
- sms (fallback):         legacy SMS via the send_sms chokepoint
- email:                  Phase 2 (returns not-implemented)
- dashboard:              Phase 2 (returns not-implemented)

Per directive H.2.3: the abstraction IS the bypass. Swapping backends later
(e.g. Meta Cloud API direct, email, dashboard) doesn't touch any caller. Do not
add Meta Cloud API in Phase 1.

Per directive H.2.4 (Phase 2 provisioning): every send persists a Message row
with recipient_role="rep" so the lead detail page can show rep notifications
(the v4 missing piece).

Per v5 hard rule: OUTBOUND_ENABLED=false default. Real sends only on explicit
"enable live." Twilio credits burned in v4 by automated tests — never again.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.config import settings
from app.models import Channel, Direction, Message

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models import Lead

logger = logging.getLogger("speed-to-lead.notify_rep")


# --- Public types ------------------------------------------------------------

@dataclass
class NotificationResult:
    """Outcome of a notify_rep() call.

    - success: did the call go through (either real send or clean dry-run)?
    - backend: which backend handled it (or was attempted)
    - message_sid: provider SID (or DRYRUN_<hex> in dry-run; None on hard error)
    - dry_run: True when OUTBOUND_ENABLED=false and the call was logged, not sent
    - error: human-readable error if success=False
    """
    success: bool
    backend: str
    message_sid: str | None
    dry_run: bool = False
    error: str | None = None


# --- Transport stubs (Task 1.2 will replace twilio_whatsapp with real call) ---

def send_via_twilio_whatsapp(
    *,
    to_phone: str,
    from_phone: str,
    body: str,
    template_sid: str | None = None,
    variables: dict | None = None,
) -> str:
    """Send a message via Twilio WhatsApp. STUB for Task 1.1.

    Task 1.2 replaces this with the real `twilio.rest.Client.messages.create`
    call using `content_sid=template_sid` and `content_variables=str(variables)`.
    For now: raises NotImplementedError when OUTBOUND_ENABLED is true (so the
    dry-run path stays safe by default; real sends only land via Task 1.2).
    """
    if not settings.outbound_enabled:
        # Defensive: should be caught by the dry-run gate in notify_rep first.
        return f"DRYRUN_{uuid.uuid4().hex[:12]}"
    raise NotImplementedError(
        "Real Twilio WhatsApp send lands in Task 1.2. "
        "Until then, keep OUTBOUND_ENABLED=false."
    )


def send_via_sms(*, to_phone: str, from_phone: str, body: str) -> str:
    """Send a message via SMS. STUB for Task 1.1.

    Task 1.2 can route this through the existing tools.send_sms.send_sms()
    chokepoint if we ever need the SMS fallback path. For now, behave the
    same as WhatsApp: dry-run in dev, raise in prod.
    """
    if not settings.outbound_enabled:
        return f"DRYRUN_{uuid.uuid4().hex[:12]}"
    raise NotImplementedError(
        "Real SMS fallback send lands in Task 1.2. "
        "Until then, keep OUTBOUND_ENABLED=false."
    )


# --- Message body builder ----------------------------------------------------

def _build_body(message_type: str, payload: dict, rep_name: str) -> str:
    """Map (message_type, payload, rep_name) to a human-readable body.

    Each dealer-facing event type has its own short template. Keep these
    terse — the rep is reading this on a phone, between other things.
    """
    customer = payload.get("customer_name", "A customer")
    vehicle = payload.get("vehicle", "")
    vehicle_str = f" re: {vehicle}" if vehicle else ""

    if message_type == "claim":
        return (
            f"Hey {rep_name} — new lead: {customer}{vehicle_str}. "
            f"Reply 1 to claim, 2 to pass."
        )
    if message_type == "appointment_set":
        when = payload.get("scheduled_for", "TBD")
        return (
            f"{rep_name} — appointment booked with {customer}{vehicle_str} for {when}. "
            f"Calendar invite incoming."
        )
    if message_type == "escalation":
        reason = payload.get("reason", "no reason given")
        return (
            f"{rep_name} — {customer}{vehicle_str} needs attention. "
            f"Reason: {reason}. Please review."
        )
    if message_type == "missed_call":
        return (
            f"{rep_name} — missed call from {customer}. "
            f"AI already texted them a follow-up."
        )
    # Fallback: generic
    return f"{rep_name} — update on {customer}{vehicle_str}."


# --- Logging -----------------------------------------------------------------

def _log_rep_message(
    session: "Session",
    lead: "Lead",
    channel: Channel,
    body: str,
    provider_sid: str,
    *,
    ai_generated: bool = False,
) -> None:
    """Persist a Message row for a dealer-side notification.

    Always sets recipient_role='rep' so the lead detail page can show rep
    notifications in the conversation thread (the v4 missing piece).
    """
    msg = Message(
        lead_id=lead.id,
        direction=Direction.OUTBOUND,
        channel=channel,
        body=body,
        provider_sid=provider_sid,
        ai_generated=ai_generated,
        sender_role="system",  # system-initiated dealer notification
        recipient_role="rep",
    )
    session.add(msg)
    try:
        session.commit()
    except Exception:
        logger.exception("Failed to log rep notification for lead#%s", lead.id)
        session.rollback()


# --- Public API --------------------------------------------------------------

def notify_rep(
    *,
    session: "Session",
    rep_config: dict,
    lead: "Lead",
    message_type: str,
    payload: dict,
    dealer_config: dict,
) -> NotificationResult:
    """Single chokepoint for dealer-side notifications.

    The router, escalation engine, and missed-call handoff ALL call this.
    Never call send_sms() / send_whatsapp() directly for rep-targeted messages.

    Args:
        session: SQLAlchemy session (for the Message log).
        rep_config: The rep's config dict. Reads `notify_backend` (default
            'twilio_whatsapp') and `phone`. May also have `notify_template_sid`.
        lead: The lead this notification is about. Used for the Message log
            and for the body text.
        message_type: One of 'claim', 'appointment_set', 'escalation',
            'missed_call'. Determines the body template.
        payload: Free-form data the body template uses (customer_name, vehicle,
            scheduled_for, reason, etc.).
        dealer_config: The dealer's full config (for whatsapp_sender fallback).

    Returns:
        NotificationResult — see the dataclass docstring.
    """
    backend = rep_config.get("notify_backend", "twilio_whatsapp")
    rep_name = rep_config.get("name", "rep")
    rep_phone = rep_config.get("phone", "")

    if not rep_phone:
        return NotificationResult(
            success=False,
            backend=backend,
            message_sid=None,
            error=f"rep {rep_name!r} has no phone number; cannot notify",
        )

    # Phase 2 backends: reject before the dry-run gate so the test for the
    # "not implemented" case actually returns success=False.
    if backend in ("email", "dashboard"):
        return NotificationResult(
            success=False,
            backend=backend,
            message_sid=None,
            error=f"{backend} backend not implemented (Phase 2)",
        )

    if backend not in ("twilio_whatsapp", "sms"):
        return NotificationResult(
            success=False,
            backend=backend,
            message_sid=None,
            error=f"unknown notify_backend: {backend!r}",
        )

    body = _build_body(message_type, payload, rep_name)

    # Dry-run gate — v5 hard rule: OUTBOUND_ENABLED=false default. Real sends
    # only when the user explicitly sets OUTBOUND_ENABLED=true. When dry-run
    # is active, we still persist the Message row (so the lead detail page
    # shows the rep was notified) but no transport call happens.
    if not settings.outbound_enabled:
        sid = f"DRYRUN_{uuid.uuid4().hex[:12]}"
        logger.info(
            "DRY-RUN notify_rep backend=%s rep=%s lead#%s sid=%s body=%.80s",
            backend, rep_name, lead.id, sid, body,
        )
        log_channel = Channel.SMS if backend == "sms" else Channel.WHATSAPP
        _log_rep_message(session, lead, log_channel, body, sid)
        return NotificationResult(
            success=True, backend=backend, message_sid=sid, dry_run=True,
        )

    # Real send paths (gated on OUTBOUND_ENABLED above)
    if backend == "twilio_whatsapp":
        from_phone = dealer_config.get("channels", {}).get("whatsapp_sender", "")
        try:
            sid = send_via_twilio_whatsapp(
                to_phone=rep_phone,
                from_phone=from_phone,
                body=body,
                template_sid=rep_config.get("notify_template_sid"),
                variables=payload,
            )
            _log_rep_message(session, lead, Channel.WHATSAPP, body, sid)
            return NotificationResult(success=True, backend=backend, message_sid=sid)
        except NotImplementedError as exc:
            return NotificationResult(False, backend, None, error=str(exc))
        except Exception as exc:
            logger.exception("notify_rep WhatsApp send failed for rep=%s", rep_name)
            return NotificationResult(False, backend, None, error=str(exc))

    # backend == "sms" (validated above)
    from_phone = dealer_config.get("channels", {}).get("sms_number", "")
    try:
        sid = send_via_sms(
            to_phone=rep_phone, from_phone=from_phone, body=body,
        )
        _log_rep_message(session, lead, Channel.SMS, body, sid)
        return NotificationResult(success=True, backend=backend, message_sid=sid)
    except NotImplementedError as exc:
        return NotificationResult(False, backend, None, error=str(exc))
    except Exception as exc:
        logger.exception("notify_rep SMS send failed for rep=%s", rep_name)
        return NotificationResult(False, backend, None, error=str(exc))
