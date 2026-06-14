"""Transports — thin wrappers that bridge app-layer calls to tool-layer senders.

The main.py webhook handlers call `send_whatsapp(to_number, from_number, body, ...)`
but the real implementation lives in `tools.send_sms.send_whatsapp(to, body, from_number, ...)`.
This module adapts the call signatures so the webhook code stays clean.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models import Lead

logger = logging.getLogger("speed-to-lead.transports")


def send_whatsapp(
    *,
    to_number: str,
    from_number: str,
    body: str,
    dealer_id: int | None = None,
    lead_id: int | None = None,
    session: "Session | None" = None,
    lead: "Lead | None" = None,
) -> str | None:
    """Send a WhatsApp message via the tools.send_sms chokepoint.

    Bridges the app-layer call signature (keyword-only, to_number/from_number)
    to the tool-layer signature (positional to, keyword body/from_number).
    """
    from tools.send_sms import send_whatsapp as _tool_send_whatsapp

    # Strip whatsapp: prefix if present — the tool adds it
    clean_to = to_number.replace("whatsapp:", "")
    clean_from = from_number.replace("whatsapp:", "")

    logger.info("Transport send_whatsapp: to=%s from=%s body=%s", clean_to, clean_from, body[:80])

    return _tool_send_whatsapp(
        to=clean_to,
        body=body,
        from_number=clean_from,
        lead=lead,
        session=session,
    )
