"""Telegram Bot API transport for dealer-side notifications.

Architecture decision (Jun 19): Telegram is the ONLY dealer notification
channel. No WhatsApp fallback for dealers. Twilio is customer-facing ONLY.

Requires TELEGRAM_BOT_TOKEN env var and telegram_chat_id in the rep's
dealer YAML config entry.
"""

from __future__ import annotations

import logging
import uuid

from app.config import settings
from app.transports.base import Transport, TransportResult

logger = logging.getLogger("speed-to-lead.transports.telegram")


class TelegramTransport(Transport):
    """Send messages via Telegram Bot API."""

    @property
    def name(self) -> str:
        return "telegram"

    def send(self, *, to: str, body: str, **kwargs) -> TransportResult:
        """Send a Telegram message to a chat_id.

        Args:
            to: Telegram chat_id (numeric string, e.g. "123456789").
            body: Message text.
            **kwargs: Accepts inline_keyboard for inline button markup.

        Returns:
            TransportResult.
        """
        bot_token = settings.telegram_bot_token
        if not bot_token:
            return TransportResult(
                success=False,
                backend="telegram",
                message_id=None,
                error="TELEGRAM_BOT_TOKEN not configured",
            )

        if not settings.outbound_enabled:
            sid = f"DRYRUN_{uuid.uuid4().hex[:12]}"
            logger.info(
                "DRY-RUN telegram to chat_id=%s body=%.80s sid=%s",
                to, body, sid,
            )
            return TransportResult(
                success=True, backend="telegram",
                message_id=sid, dry_run=True,
            )

        import httpx
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        payload: dict = {
            "chat_id": to,
            "text": body,
            "parse_mode": "HTML",
        }

        inline_keyboard = kwargs.get("inline_keyboard")
        if inline_keyboard:
            payload["reply_markup"] = {"inline_keyboard": inline_keyboard}

        try:
            resp = httpx.post(url, json=payload, timeout=10.0)
            data = resp.json()
            if resp.status_code == 200 and data.get("ok"):
                message_id = str(data["result"]["message_id"])
                logger.info("Telegram message sent to %s: id=%s", to, message_id)
                return TransportResult(
                    success=True, backend="telegram",
                    message_id=message_id,
                )
            else:
                error = data.get("description", "unknown Telegram error")
                logger.warning("Telegram API error for %s: %s", to, error)
                return TransportResult(
                    success=False, backend="telegram",
                    message_id=None, error=error,
                )
        except httpx.TimeoutException:
            logger.warning("Telegram timeout for %s", to)
            return TransportResult(
                success=False, backend="telegram",
                message_id=None, error="timeout",
            )
        except Exception as exc:
            logger.warning("Telegram send failed for %s: %s", to, exc)
            return TransportResult(
                success=False, backend="telegram",
                message_id=None, error=str(exc),
            )
