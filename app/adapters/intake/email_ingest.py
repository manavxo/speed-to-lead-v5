"""Email ingestion via IMAP polling.

Polls the configured email inbox every N minutes, fetches unseen emails,
parses them via EmailLeadAdapter, and creates leads in the system.

Configuration (env vars):
  EMAIL_INBOX_USERNAME — email address (e.g. speedtoleadsolutions@gmail.com)
  EMAIL_INBOX_PASSWORD — app password
  EMAIL_IMAP_SERVER   — IMAP server (e.g. imap.gmail.com)
  EMAIL_IMAP_PORT     — IMAP port (default: 993)

Uses Python stdlib imaplib — no extra dependencies.
"""

from __future__ import annotations

import email
import imaplib
import logging
import re
from email.header import decode_header
from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger("speed-to-lead.email_ingest")


def _extract_email_addr(raw_from: str) -> str | None:
    """Extract a clean email address from a From header (e.g. 'John <john@example.com>')."""
    match = re.search(r"(\S+@\S+)", raw_from)
    return match.group(1).strip().lower() if match else None


def _find_existing_lead(session: Session, dealer_id: int, sender_email: str) -> "Lead | None":
    """Look up an existing lead by email address for this dealer."""
    from sqlmodel import select
    from app.models import Lead, LeadState
    return session.execute(
        select(Lead).where(
            Lead.dealer_id == dealer_id,
            Lead.email == sender_email,
            Lead.state.notin_([LeadState.OPTED_OUT, LeadState.LOST, LeadState.SOLD]),
        )
    ).scalars().first()


def _handle_email_reply(
    session: Session,
    lead: "Lead",
    sender: str,
    body: str,
    subject: str,
    mail: imaplib.IMAP4_SSL,
    num_str: str,
) -> bool:
    """Handle an email reply to an existing lead."""
    from app.models import Direction, Message

    # Store the reply as a new customer message in the conversation thread
    msg = Message(
        lead_id=lead.id,
        direction=Direction.INBOUND,
        channel=Channel.EMAIL,
        body=body or "(no content)",
        ai_generated=False,
    )
    session.add(msg)
    session.commit()

    # Mark as seen so we don't reprocess
    mail.store(num_str, "+FLAGS", "\\Seen")

    # Notify the assigned rep via Telegram
    if lead.assigned_rep:
        _notify_rep_of_email_reply(session, lead, body)

    logger.info("Email reply recorded for existing lead#%s from %s", lead.id, sender)
    return True


def _notify_rep_of_email_reply(session: Session, lead: "Lead", reply_body: str | None) -> None:
    """Send a Telegram notification to the assigned rep about an email reply."""
    from tools.notify_rep import notify_rep
    from app.models import Dealer

    dealer = session.execute(
        select(Dealer).where(Dealer.id == lead.dealer_id)
    ).scalars().first()

    if not dealer:
        return

    dealer_config = dealer.config or {}
    sales_team = dealer_config.get("sales_team", [])

    # Find the assigned rep's config
    rep_config = None
    for rep in sales_team:
        if rep.get("name") == lead.assigned_rep:
            rep_config = rep
            break

    if not rep_config:
        return

    vehicle_info = lead.vehicle_ref or "Vehicle inquiry"
    reply_text = (reply_body or "")[:200]

    # Build the email-specific notification framing
    notification_text = (
        f"\U0001f535 EMAIL REPLY \u2014 {lead.name or 'Unknown'}\n"
        f"(no phone available)\n"
        f"\U0001f697 {vehicle_info}\n"
        f"Source: listing site\n\n"
        f"\U0001f4ac Their reply:\n"
        f"{reply_text}\n"
    )

    notify_rep.dealer_pipeline_notifier = lambda *a, **kw: None  # no-op if not available
    from tools.notify_rep import notify_rep_dealer

    notify_rep_dealer(
        dealer, lead, notification_text,
        rep_config=rep_config,
        notify_backend="telegram",
    )

    logger.info(
        "Telegram notification sent for email reply to lead#%s rep=%s",
        lead.id, lead.assigned_rep,
    )


def _decode_mime_header(value: str) -> str:
    """Decode a MIME encoded-header (e.g. =?UTF-8?Q?Subject?=) to plain text."""
    if not value:
        return ""
    parts = decode_header(value)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            try:
                result.append(part.decode(charset or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError):
                result.append(part.decode("utf-8", errors="replace"))
        else:
            result.append(str(part))
    return " ".join(result)


def poll_inbox(session: Session, dealer) -> int:
    """Poll the configured email inbox, parse unseen emails, create leads.

    Args:
        session: SQLAlchemy session for persisting leads.
        dealer: The Dealer ORM object (uses dealer.config for routing).

    Returns:
        Number of new leads created.
    """
    username = settings.email_inbox_username
    password = settings.email_inbox_password
    server = settings.email_imap_server
    port = settings.email_imap_port

    if not username or not password:
        logger.warning("EMAIL_INBOX_USERNAME/PASSWORD not configured — skipping IMAP poll")
        return 0

    created_count = 0
    mail = None
    try:
        mail = imaplib.IMAP4_SSL(server, port)
        mail.login(username, password)
        mail.select("INBOX")

        status, messages = mail.search(None, "UNSEEN")
        if status != "OK" or not messages[0]:
            logger.info("No unseen emails found")
            return 0

        seen_uids = []
        for num in messages[0].split():
            num_str = num.decode() if isinstance(num, bytes) else num
            status, data = mail.fetch(num_str, "(RFC822)")
            if status != "OK":
                continue

            raw_email = data[0][1] if isinstance(data[0], tuple) else None
            if not raw_email:
                continue

            try:
                msg = email.message_from_bytes(raw_email)
                subject = _decode_mime_header(msg.get("Subject", ""))
                sender = _decode_mime_header(msg.get("From", ""))
                body = _get_email_body(msg)

                logger.info(
                    "Fetched email: subject=%s from=%s body_len=%d",
                    subject[:80], sender[:80], len(body or ""),
                )

                # Check if this is a reply to an existing lead
                sender_email = _extract_email_addr(sender)
                existing_lead = (
                    _find_existing_lead(session, dealer.id, sender_email)
                    if sender_email
                    else None
                )

                if existing_lead:
                    # This is a reply — store it, notify rep, don't create new lead
                    _handle_email_reply(
                        session, existing_lead, sender,
                        body or "", subject, mail, num_str,
                    )
                    seen_uids.append(num_str)
                    continue

                # Parse via site-specific parser registry
                from app.adapters.intake.email_parsers import parse_email

                lead_data = parse_email(body or "", subject=subject, from_addr=sender)

                if lead_data:
                    # Route based on phone availability
                    if lead_data.phone:
                        from tools.route_lead import ingest_lead
                        lead = ingest_lead(session, dealer, lead_data)
                    else:
                        from tools.route_lead import ingest_lead_email_no_phone
                        lead = ingest_lead_email_no_phone(session, dealer, lead_data)

                    if lead:
                        created_count += 1
                        logger.info(
                            "Lead#%s created from email: %s",
                            lead.id, subject[:60],
                        )
                        # Mark as seen
                        mail.store(num_str, "+FLAGS", "\\Seen")
                        seen_uids.append(num_str)

            except Exception:
                logger.exception("Failed to process email %s", num_str)

        logger.info("IMAP poll complete: %d new leads from %d unseen emails", created_count, len(seen_uids))
        return created_count

    except Exception:
        logger.exception("IMAP poll failed")
        return created_count
    finally:
        if mail:
            try:
                mail.logout()
            except Exception:
                pass


def _get_email_body(msg: email.message.Message) -> str | None:
    """Extract the plain-text body from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        return payload.decode(charset, errors="replace")
                    except (LookupError, UnicodeDecodeError):
                        return payload.decode("utf-8", errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                return payload.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                return payload.decode("utf-8", errors="replace")
    return None
