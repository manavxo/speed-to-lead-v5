"""Email transport for outbound follow-ups and rep replies.

Uses SendGrid (primary) with a Mailgun-style fallback pattern.
Configure via env vars:
  SENDGRID_API_KEY — SendGrid API key
  EMAIL_FROM_ADDRESS — global fallback sender (e.g. noreply@speedtolead.com)
  EMAIL_FROM_NAME — global fallback display name

Each dealer can override the sender via their YAML config's channels.email_from_address
and channels.email_from_name — this is the preferred path for production so every
dealership sends from their own domain.

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


def _resolve_sender(dealer_config: dict | None = None) -> tuple[str, str]:
    """Resolve the From address and name, preferring per-dealer config over global env vars.

    Priority:
      1. dealer_config.channels.email_from_address (per-dealer YAML)
      2. settings.email_from_address (global env var)
      3. "noreply@speedtolead.com" (built-in fallback)

    Returns (from_email, from_name).
    """
    # Per-dealer config wins
    if dealer_config:
        channels = dealer_config.get("channels", {})
        dealer_from = channels.get("email_from_address")
        dealer_name = channels.get("email_from_name")
        if dealer_from:
            return dealer_from, dealer_name or ""

    # Global env var fallback
    global_from = settings.email_from_address
    global_name = settings.email_from_name
    if global_from:
        return global_from, global_name or ""

    # Ultimate fallback
    return "noreply@speedtolead.com", "Speed to Lead"


def send_email(
    to: str,
    subject: str,
    body_text: str,
    *,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None,
    reply_to: Optional[str] = None,
    dealer_config: dict | None = None,
) -> EmailResult:
    """Send an email via SendGrid. Returns EmailResult — never raises.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body_text: Plain-text body.
        from_email: Explicit sender override (highest priority).
        from_name: Explicit sender display name override.
        reply_to: Optional reply-to address.
        dealer_config: Dealer config dict — used to resolve per-dealer email_from_address
                       when from_email is not explicitly provided.

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

    # Resolve sender: explicit param > dealer_config > env var > built-in fallback
    if from_email:
        sender = from_email
        sender_name = from_name or ""
    else:
        sender, sender_name = _resolve_sender(dealer_config)

    if not sender_name:
        sender_name = settings.email_from_name or "Speed to Lead"

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
            logger.info("Email sent to %s from=%s: id=%s (status=%s)", to, sender, message_id, response.status_code)
            return EmailResult(success=True, message_id=message_id)
        else:
            logger.warning("SendGrid returned %s for email to %s from=%s", response.status_code, to, sender)
            return EmailResult(success=False, message_id=None, error=f"HTTP {response.status_code}")

    except ImportError:
        logger.warning("sendgrid package not installed — install with: pip install sendgrid")
        return EmailResult(success=False, message_id=None, error="sendgrid package not installed")
    except Exception as exc:
        logger.warning("Failed to send email to %s from=%s: %s", to, sender, exc)
        return EmailResult(success=False, message_id=None, error=str(exc))
