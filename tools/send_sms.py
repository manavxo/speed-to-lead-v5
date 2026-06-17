"""Tool: outbound messaging via Twilio (SMS lead-facing, WhatsApp rep-facing).

The ONLY module that sends messages. Enforces compliance before sending: skip if the lead is
OPTED_OUT, skip during quiet_hours, and log to ConsentLog/Message. Idempotent on provider SID.

When OUTBOUND_ENABLED is false (the default), no real provider call is made.  A synthetic
"DRYRUN_*" SID is returned and the Message row is still persisted so the pipeline can be
exercised end-to-end without Twilio creds.  This is what makes deploying safe before creds exist.
"""

from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models import Lead

logger = logging.getLogger("speed-to-lead.send_sms")

import uuid
import re


def _sanitize_message(body: str, dealer_name: str = "", is_first_message: bool = False) -> str:
    """Sanitize SMS message for best deliverability.

    - Trims to 1600 chars max (SMS limit)
    - Warns if > 160 chars (multi-segment)
    - Removes excessive punctuation (!!! -> !, ??? -> ?)
    - Converts ALL CAPS words to title case
    - Flags and removes URL shorteners (bit.ly, tinyurl)
    - Adds sender identity to first message if not present
    """
    if not body:
        return body

    # Remove URL shorteners
    url_shortener_pattern = r'https?://(?:bit\.ly|tinyurl\.com|t\.co|goo\.gl|ow\.ly|is\.gd|buff\.ly|bl\.ink|short\.to)/\S+'
    if re.search(url_shortener_pattern, body):
        logger.warning("URL shortener detected in message — removing")
        body = re.sub(url_shortener_pattern, '', body).strip()

    # Remove excessive punctuation (!!! -> !, ??? -> ?)
    body = re.sub(r'!{2,}', '!', body)
    body = re.sub(r'\?{2,}', '?', body)

    # Convert ALL CAPS words to title case (but keep normal sentences)
    # Only convert words that are 3+ chars and ALL uppercase
    def _replace_caps(match):
        word = match.group(0)
        # Don't convert common acronyms
        acronyms = {'SMS', 'URL', 'VIN', 'SUV', 'AWD', 'FWD', 'RWD', 'ABS', 'GPS', 'USB', 'LED', 'AEB'}
        if word in acronyms:
            return word
        return word.title()

    body = re.sub(r'\b[A-Z]{3,}\b', _replace_caps, body)

    # Add sender identity to first message if not present
    if is_first_message and dealer_name and dealer_name.lower() not in body.lower():
        body = f"Hi! This is {dealer_name}. {body}"

    # Trim to 1600 chars max
    if len(body) > 1600:
        logger.warning("Message truncated from %d to 1600 chars", len(body))
        body = body[:1597] + "..."

    # Warn if multi-segment
    if len(body) > 160:
        logger.info("Message is %d chars (multi-segment SMS)", len(body))

    return body


def _next_dryrun_sid() -> str:
    return f"DRYRUN_{uuid.uuid4().hex[:32]}"


def _is_opted_out(session: Session, phone: str) -> bool:
    """Check if a phone number has an active (non-revoked) opt-out."""
    from app.models import ConsentLog
    from sqlalchemy import select
    # Check for active opt-out without a subsequent revoke
    opt_out = session.execute(
        select(ConsentLog).where(
            ConsentLog.phone == phone,
            ConsentLog.action == "opted_out",
        ).order_by(ConsentLog.created_at.desc())
    ).scalars().first()

    if not opt_out:
        return False

    # Check if there's a revoke after the latest opt-out
    revoke = session.execute(
        select(ConsentLog).where(
            ConsentLog.phone == phone,
            ConsentLog.action == "re_granted",
            ConsentLog.created_at > opt_out.created_at,
        )
    ).scalars().first()

    return revoke is None


def _is_quiet_hours(dealer_config: dict, now: datetime | None = None) -> bool:
    """Check if current time falls within the dealer's quiet hours (in dealer timezone)."""
    if now is None:
        now = datetime.now(timezone.utc)

    quiet_str = dealer_config.get("compliance", {}).get("quiet_hours", "21:00-08:00")
    tz_name = dealer_config.get("dealer", {}).get("timezone", "America/Vancouver")

    try:
        from zoneinfo import ZoneInfo
        local_now = now.astimezone(ZoneInfo(tz_name))
    except Exception:
        local_now = now

    start_str, end_str = quiet_str.split("-")
    start_h, start_m = map(int, start_str.split(":"))
    end_h, end_m = map(int, end_str.split(":"))

    current_minutes = local_now.hour * 60 + local_now.minute
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m

    if start_minutes > end_minutes:
        # Wraps midnight (e.g. 21:00-08:00)
        return current_minutes >= start_minutes or current_minutes < end_minutes
    else:
        return start_minutes <= current_minutes < end_minutes


def _apply_message_tag(body: str, *, role: str, lead_id: int | None = None,
                       recipient_name: str | None = None) -> str:
    """Prefix a staging-only role tag when MESSAGE_TAGS_ENABLED is true.

    Tags disambiguate messages on reused phones during live-fire testing.
    MUST be OFF in production.
    """
    if not settings.message_tags_enabled:
        return body
    tag_parts = [f"STG {role}"]
    if lead_id is not None:
        tag_parts.append(f"lead#{lead_id}")
    if recipient_name:
        tag_parts.append(f"->{recipient_name}")
    tag = "[" + " ".join(tag_parts) + "]"
    return f"{tag} {body}"


def _log_message(
    session: Session,
    lead_id: int,
    direction: str,
    channel: str,
    body: str,
    provider_sid: str | None = None,
    ai_generated: bool = False,
) -> None:
    """Persist a Message row."""
    from app.models import Message, Direction, Channel
    msg = Message(
        lead_id=lead_id,
        direction=Direction(direction),
        channel=Channel(channel),
        body=body,
        provider_sid=provider_sid,
        ai_generated=ai_generated,
    )
    session.add(msg)
    try:
        session.commit()
        logger.info("Message logged for lead#%s direction=%s sid=%s", lead_id, direction, provider_sid)
    except Exception:
        logger.exception("Failed to commit message for lead#%s", lead_id)
        session.rollback()


def _has_consent(session: Session, lead: Lead | None) -> bool:
    """Check whether a lead has consent for outbound SMS.

    Returns True if:
    - lead.consent is True (web form implied consent), OR
    - a ConsentLog entry with action='granted' exists for the phone, OR
    - no lead is provided (caller is not lead-gated)

    Returns False if the lead exists but has no consent record.
    """
    if lead is None:
        return True  # Not a lead-gated send (e.g. rep notification)
    if lead.consent:
        return True
    # Check ConsentLog for explicit consent
    if lead.phone:
        from app.models import ConsentLog
        from sqlalchemy import select
        result = session.execute(
            select(ConsentLog).where(
                ConsentLog.phone == lead.phone,
                ConsentLog.action.in_(["granted", "re_granted"]),
            )
        ).scalars().first()
        if result:
            return True
    return False


def _log_consent(session: Session, lead: Lead, source: str = "implied") -> None:
    """Log implied consent for a lead (web form = express, SMS inbound = implied)."""
    if not lead.phone:
        return
    # Avoid duplicate consent logs
    from app.models import ConsentLog
    from sqlalchemy import select
    existing = session.execute(
        select(ConsentLog).where(
            ConsentLog.dealer_id == lead.dealer_id,
            ConsentLog.phone == lead.phone,
            ConsentLog.action == "granted",
        )
    ).scalars().first()
    if existing:
        return
    consent_log = ConsentLog(
        dealer_id=lead.dealer_id,
        lead_id=lead.id,
        phone=lead.phone,
        action="granted",
        text=f"Consent via {source}",
    )
    session.add(consent_log)
    session.commit()


def send_sms(
    session: Session,
    to: str,
    body: str,
    from_number: str,
    *,
    dealer_slug: str = "",
    dealer_config: dict | None = None,
    lead: Lead | None = None,
    fake_twilio=None,
    now: datetime | None = None,
    force_send: bool = False,
    role: str = "CUSTOMER",
    recipient_name: str | None = None,
) -> str | None:
    """Send a lead-facing SMS. Returns the Twilio message SID, or None if suppressed.

    Enforces:
    - Opt-out check: if the recipient has opted out, skip and return None.
    - Quiet hours: if current time is in quiet hours, skip and return None.
      (force_send=True bypasses quiet hours for customer-initiated replies)
    - OUTBOUND_ENABLED gate: when False, record the message but do NOT call Twilio.
    """
    if dealer_config is None:
        dealer_config = {}

    logger.info("send_sms called: to=%s lead=%s quiet_hours_disabled=%s",
                to, lead.id if lead else None, settings.quiet_hours_disabled)

    # Check opt-out
    if _is_opted_out(session, to):
        logger.info("SMS to %s suppressed: opted_out", to)
        if lead:
            _log_message(session, lead.id, "outbound", "sms", body,
                         provider_sid=f"SUPPRESSED_OPTOUT_{uuid.uuid4().hex[:12]}", ai_generated=True)
        return None

    # Check consent — block if lead exists but has no consent record
    if lead and not _has_consent(session, lead):
        logger.warning("SMS to %s suppressed: no consent for lead#%s", to, lead.id)
        try:
            _log_message(session, lead.id, "outbound", "sms", body,
                         provider_sid=f"SUPPRESSED_NO_CONSENT_{uuid.uuid4().hex[:12]}", ai_generated=True)
        except Exception:
            logger.exception("Failed to log suppressed (no consent) message for lead#%s", lead.id)
        return None

    # Check quiet hours
    if not force_send and not settings.quiet_hours_disabled and _is_quiet_hours(dealer_config, now=now):
        logger.info("SMS to %s suppressed: quiet_hours", to)
        if lead:
            try:
                _log_message(session, lead.id, "outbound", "sms", body,
                             provider_sid=f"SUPPRESSED_QUIET_{uuid.uuid4().hex[:12]}", ai_generated=True)
            except Exception:
                logger.exception("Failed to log suppressed (quiet hours) message for lead#%s", lead.id)
        return None

    # Sanitize message for deliverability
    dealer_name = dealer_config.get("dealer", {}).get("name", "") if dealer_config else ""
    body = _sanitize_message(body, dealer_name=dealer_name)

    # Apply staging message tag if enabled
    lead_id = lead.id if lead else None
    tagged_body = _apply_message_tag(body, role=role, lead_id=lead_id, recipient_name=recipient_name)

    # Gate real sends behind OUTBOUND_ENABLED
    if not settings.outbound_enabled and not fake_twilio:
        sid = _next_dryrun_sid()
        logger.info(
            "DRY-RUN SMS to %s (sid=%s): %s", to, sid, tagged_body[:80],
        )
        if lead:
            logger.info("DRY-RUN: about to _log_message for lead#%s", lead.id)
            _log_message(session, lead.id, "outbound", "sms", tagged_body,
                         provider_sid=sid, ai_generated=True)
            logger.info("DRY-RUN: _log_message returned for lead#%s", lead.id)
        return sid

    # Send via Twilio (or fake for testing)
    try:
        if fake_twilio:
            sid = fake_twilio.send(to=to, body=tagged_body, from_=from_number)
        else:
            from twilio.rest import Client
            client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            message = client.messages.create(to=to, body=tagged_body, from_=from_number)
            sid = message.sid
    except Exception:
        logger.exception("Twilio SMS send failed to %s", to)
        return None

    # Log the message
    if lead:
        _log_message(session, lead.id, "outbound", "sms", tagged_body,
                     provider_sid=sid, ai_generated=True)

    return sid


def send_whatsapp(
    to: str,
    *,
    body: str = "",
    template: str | None = None,
    variables: dict | None = None,
    from_number: str = "",
    lead: Lead | None = None,
    session: Session | None = None,
    role: str = "REP",
    recipient_name: str | None = None,
    fake_twilio=None,
) -> str | None:
    """Send a rep-facing WhatsApp message.

    Business-initiated pings must use an approved template (Twilio requirement).
    When OUTBOUND_ENABLED is false, returns a DRYRUN SID and logs instead of sending.
    """
    lead_id = lead.id if lead else None
    # Diagnostic: surface the exact From + gate state before any processing.
    logger.info(
        "send_whatsapp ENTRY: to=%s from_number=%r role=%s outbound_enabled=%s lead=%s",
        to, from_number, role, settings.outbound_enabled, lead_id,
    )
    if not from_number:
        logger.error("send_whatsapp: empty from_number for to=%s — refusing to send", to)
        return None
    # Sanitize message for deliverability
    body = _sanitize_message(body)
    tagged_body = _apply_message_tag(
        body, role=role, lead_id=lead_id, recipient_name=recipient_name,
    )

    # Gate real sends
    if not settings.outbound_enabled and not fake_twilio:
        sid = _next_dryrun_sid()
        logger.info(
            "DRY-RUN WhatsApp to %s (sid=%s): %s", to, sid, tagged_body[:80],
        )
        if lead and session:
            _log_message(session, lead.id, "outbound", "whatsapp", tagged_body,
                         provider_sid=sid, ai_generated=False)
        return sid

    try:
        if fake_twilio:
            sid = fake_twilio.send(
                to=to, body=tagged_body, from_=from_number, channel="whatsapp",
            )
        else:
            logger.info("SEND_WHATSAPP: to=%s from=%s template=%s vars=%s", to, from_number, template, variables)
            from twilio.rest import Client
            client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            kwargs: dict = {
                "to": f"whatsapp:{to}",
                "from_": f"whatsapp:{from_number}",
            }
            if template:
                kwargs["content_sid"] = template
                if variables:
                    kwargs["content_variables"] = json.dumps(variables)
            else:
                kwargs["body"] = tagged_body
            message = client.messages.create(**kwargs)
            sid = message.sid
    except Exception:
        logger.exception("Twilio WhatsApp send failed to %s", to)
        return None

    # Log the message
    if lead and session:
        _log_message(session, lead.id, "outbound", "whatsapp", tagged_body,
                     provider_sid=sid, ai_generated=False)

    return sid