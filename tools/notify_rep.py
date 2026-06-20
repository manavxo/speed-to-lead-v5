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

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.config import settings
from app.models import Channel, Direction, Message

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models import Lead

logger = logging.getLogger("speed-to-lead.notify_rep")


def _log_rep_send_failure(rep_name: str, rep_phone: str, channel: str, exc: Exception) -> None:
    """Log a failed rep ping as a clean one-line warning, not a crash dump.

    A rep being unreachable (wrong/fake number, not joined to the WhatsApp
    sandbox, etc.) must NOT look like a pipeline crash: the lead flow already
    swallows this and carries on. We log a readable warning and keep the full
    traceback only at debug level for when someone is actually digging in.
    """
    logger.warning(
        "Could not notify rep %s at %s via %s: %s "
        "(lead pipeline continues; check the number is valid and, for WhatsApp, "
        "that the rep joined the Twilio sandbox)",
        rep_name, rep_phone, channel, exc,
    )
    logger.debug("Full rep-notify error for %s", rep_name, exc_info=True)


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


# --- Twilio client factory (mockable in tests) -------------------------------

def _get_twilio_client():
    """Return a Twilio client. Mockable via monkeypatch in tests.

    Returns None when TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN aren't set, so
    the transport functions can fail clearly with a configuration error
    rather than crashing deep in the Twilio SDK.
    """
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        return None
    from twilio.rest import Client
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


# --- Transport implementations ----------------------------------------------

def send_via_twilio_whatsapp(
    *,
    to_phone: str,
    from_phone: str,
    body: str,
    template_sid: str | None = None,
    variables: dict | None = None,
) -> str:
    """Send a message via Twilio WhatsApp. Real implementation (Task 1.2).

    Per Twilio's WhatsApp Business API rules: business-initiated messages MUST
    use a pre-approved template (the 24h session-window exception only applies
    after a customer-initiated message). So when notify_rep() pings a rep about
    a new lead, we send a template via content_sid + content_variables.

    When the rep's config has no notify_template_sid, we fall back to a
    free-form body — only valid in a 24h session, but it lets us still send
    during development before templates are provisioned.
    """
    if not settings.outbound_enabled:
        return f"DRYRUN_{uuid.uuid4().hex[:12]}"

    client = _get_twilio_client()
    if client is None:
        raise RuntimeError(
            "Twilio not configured: set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN"
        )

    kwargs: dict = {
        "to": f"whatsapp:{to_phone}",
        "from_": f"whatsapp:{from_phone}",
    }
    if template_sid:
        # Business-initiated: use a pre-approved template.
        kwargs["content_sid"] = template_sid
        if variables:
            # Twilio expects content_variables as a JSON-encoded string.
            kwargs["content_variables"] = json.dumps(variables)
    else:
        # No template configured: free-form body. Use only when in a 24h
        # session or when the dealer has explicitly opted out of templates
        # for this rep.
        kwargs["body"] = body

    message = client.messages.create(**kwargs)
    return message.sid


def send_via_sms(*, to_phone: str, from_phone: str, body: str) -> str:
    """Send a message via SMS (fallback backend). Real implementation (Task 1.2).

    SMS doesn't use templates — straight body. Used when a rep's
    notify_backend is configured as 'sms' instead of 'twilio_whatsapp'.
    """
    if not settings.outbound_enabled:
        return f"DRYRUN_{uuid.uuid4().hex[:12]}"

    client = _get_twilio_client()
    if client is None:
        raise RuntimeError(
            "Twilio not configured: set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN"
        )

    message = client.messages.create(
        to=to_phone,
        from_=from_phone,
        body=body,
    )
    return message.sid


def _is_placeholder_phone(phone: str) -> bool:
    """True for NANP 555-line placeholder numbers (e.g. +16045550121).

    The 555-01xx exchange is reserved for fiction/demos; Twilio cannot deliver
    to it. Demo dealer YAMLs use these for reps, so a real send would always
    400. Matched on the 3-digit exchange == '555' of the 10-digit national part.
    """
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return len(digits) == 10 and digits[3:6] == "555"


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
    if message_type == "sale":
        # State machine SOLD notification. Rep needs to know fast — they're
        # tracking the commission. Keep it punchy: just the close + customer.
        return f"{rep_name} — sold: {customer}{vehicle_str}. Congrats 🎉"
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
            'missed_call', 'sale'. Determines the body template.
        payload: Free-form data the body template uses (customer_name, vehicle,
            scheduled_for, reason, etc.).
        dealer_config: The dealer's full config (for whatsapp_sender fallback).

    Returns:
        NotificationResult — see the dataclass docstring.
    """
    backend = rep_config.get("notify_backend", "telegram")
    rep_name = rep_config.get("name", "rep")
    rep_phone = rep_config.get("phone", "")

    if not rep_phone and backend != "telegram":
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

    if backend not in ("telegram", "twilio_whatsapp", "sms"):
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

    # Real send paths (gated on OUTBOUND_ENABLED above).
    # Demo dealers carry placeholder 555-01xx rep numbers that Twilio cannot
    # deliver to. Skip them best-effort (still log the Message row for the lead
    # timeline) instead of letting a Twilio 400/63015 bubble up as noise — and,
    # importantly, never crash the ingest pipeline over a fake rep number.
    if _is_placeholder_phone(rep_phone):
        sid = f"SKIPPED_FAKE_{uuid.uuid4().hex[:12]}"
        logger.info(
            "notify_rep: skipping placeholder rep phone %s for lead#%s (sid=%s)",
            rep_phone, lead.id, sid,
        )
        log_channel = Channel.WHATSAPP if backend == "twilio_whatsapp" else Channel.SMS
        _log_rep_message(session, lead, log_channel, body, sid)
        return NotificationResult(
            success=True, backend=backend, message_sid=sid, dry_run=True,
        )

    if backend == "telegram":
        from app.transports.telegram import TelegramTransport
        chat_id = rep_config.get("telegram_chat_id", "")
        if not chat_id:
            return NotificationResult(
                success=False, backend=backend, message_sid=None,
                error=f"rep {rep_name!r} has no telegram_chat_id; cannot notify via Telegram",
            )
        transport = TelegramTransport()
        result = transport.send(to=chat_id, body=body)
        if result.success:
            _log_rep_message(session, lead, Channel.WHATSAPP, body, result.message_id or "")
        return NotificationResult(
            success=result.success,
            backend=backend,
            message_sid=result.message_id,
            dry_run=result.dry_run,
            error=result.error,
        )

    if backend == "twilio_whatsapp":
        from_phone = dealer_config.get("channels", {}).get("whatsapp_sender", "")
        if not from_phone:
            # Fallback: some configs may lag the dedicated column (e.g. auto-provision
            # before whatsapp_sender existed). Match the customer auto-reply pattern
            # in route_lead.py which has a three-level fallback.
            from_phone = dealer_config.get("channels", {}).get("whatsapp_sender") or ""
        if not from_phone:
            logger.warning(
                "notify_rep: no whatsapp_sender in dealer config for rep %s — "
                "check dealer YAML channels.whatsapp_sender",
                rep_name,
            )
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
            _log_rep_send_failure(rep_name, rep_phone, "WhatsApp", exc)
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
        _log_rep_send_failure(rep_name, rep_phone, "SMS", exc)
        return NotificationResult(False, backend, None, error=str(exc))
