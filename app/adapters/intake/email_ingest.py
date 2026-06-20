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
from email.header import decode_header
from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger("speed-to-lead.email_ingest")


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

                # Parse via EmailLeadAdapter
                from app.adapters.intake.email_lead import EmailLeadAdapter

                adapter = EmailLeadAdapter()
                payload = {
                    "raw": body or "",
                    "subject": subject,
                    "from": sender,
                }
                lead_data = adapter.parse(payload)

                if lead_data:
                    # Ingest via the standard pipeline
                    from tools.route_lead import ingest_lead

                    lead = ingest_lead(session, dealer, lead_data)
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
