"""Email transport for outbound follow-ups and rep replies.

Uses SendGrid (primary) with a Mailgun-style fallback pattern.
Configure via env vars:
  SENDGRID_API_KEY — SendGrid API key
  EMAIL_FROM_ADDRESS — default sender (e.g. sales@premierautogroup.com)
  EMAIL_FROM_NAME — display name (e.g. "Premier Auto Group")

Every send is fire-and-forget: failures are logged but never raised.
The lead pipeline continues regardless of email delivery status.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.config import settings

logger = logging.getLogger("speed-to-lead.transports.email")


@dataclass
class EmailResult:
    """Outcome of an email send attempt."""
    success: bool
    message_id: Optional[str]
    error: Optional[str] = None


def send_email(
    to: str,
    subject: str,
    body_text: str,
    *,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> EmailResult:
    """Send an email via SendGrid. Returns EmailResult — never raises.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body_text: Plain-text body.
        from_email: Sender address (defaults to settings.email_from_address).
        from_name: Sender display name (defaults to settings.email_from_name).
        reply_to: Optional reply-to address.

    Returns:
        EmailResult with success status and message_id.
    """
    api_key = settings.sendgrid_api_key
    if not api_key:
        logger.warning("SENDGRID_API_KEY not configured — skipping email to %s", to)
        return EmailResult(success=False, message_id=None, error="SENDGRID_API_KEY not configured")

    if not settings.outbound_enabled:
        import uuid
        sid = f"DRYRUN_{uuid.uuid4().hex[:12]}"
        logger.info("DRY-RUN email to=%s subject=%s sid=%s", to, subject, sid)
        return EmailResult(success=True, message_id=sid)

    sender = from_email or settings.email_from_address or "noreply@speedtolead.com"
    sender_name = from_name or settings.email_from_name or "Speed to Lead"

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, Email, To, Content

        message = Mail(
            from_email=Email(sender, sender_name),
            to_emails=To(to),
            subject=subject,
            plain_text_content=Content("text/plain", body_text),
        )
        if reply_to:
            message.reply_to = Email(reply_to)

        sg = SendGridAPIClient(api_key)
        response = sg.send(message)

        if response.status_code in (200, 201, 202):
            message_id = response.headers.get("X-Message-Id", "")
            logger.info("Email sent to %s: id=%s (status=%s)", to, message_id, response.status_code)
            return EmailResult(success=True, message_id=message_id)
        else:
            logger.warning("SendGrid returned %s for email to %s", response.status_code, to)
            return EmailResult(success=False, message_id=None, error=f"HTTP {response.status_code}")

    except ImportError:
        logger.warning("sendgrid package not installed — install with: pip install sendgrid")
        return EmailResult(success=False, message_id=None, error="sendgrid package not installed")
    except Exception as exc:
        logger.warning("Failed to send email to %s: %s", to, exc)
        return EmailResult(success=False, message_id=None, error=str(exc))
