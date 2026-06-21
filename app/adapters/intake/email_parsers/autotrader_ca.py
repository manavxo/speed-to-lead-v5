"""AutoTrader.ca email lead parser.

AutoTrader lead notification emails typically follow a template:
  Customer Name: John Smith
  Phone: +1 604-555-1234
  Email: john@example.com
  Vehicle: 2022 Honda Civic LX
  Message: Is this still available?
  Ref #: ABC123
"""

from __future__ import annotations

import re

from app.adapters.intake import NormalizedLead
from app.models import Channel


def parse_autotrader(raw: str, subject: str = "", from_addr: str = "") -> NormalizedLead | None:
    """Parse an AutoTrader.ca lead email into a NormalizedLead.

    Args:
        raw: Raw email body text.
        subject: Email subject (unused for AutoTrader).
        from_addr: Sender email (unused).

    Returns:
        NormalizedLead if parsing succeeded, else None.
    """
    if not raw:
        return None

    # AutoTrader emails usually contain "Customer Name:" — use this as a signature
    if "Customer Name:" not in raw and "Customer:" not in raw:
        return None

    name = None
    phone = None
    email_addr = None
    vehicle_ref = None
    message = None

    # Customer name
    name_match = re.search(r"Customer\s*(?:Name)?:\s*(.+)", raw, re.IGNORECASE)
    if name_match:
        name = name_match.group(1).strip()

    # Phone
    phone_match = re.search(r"Phone:\s*([+\d\s().-]+)", raw, re.IGNORECASE)
    if phone_match:
        from app.adapters.intake import normalize_phone
        raw_phone = phone_match.group(1).strip()
        digits_only = re.sub(r"[^\d+]", "", raw_phone)
        phone = normalize_phone(digits_only)

    # Email
    email_match = re.search(r"Email:\s*(\S+@\S+)", raw, re.IGNORECASE)
    if email_match:
        email_addr = email_match.group(1).strip()

    # Vehicle — usually the most detailed line
    vehicle_match = re.search(r"Vehicle:\s*(.+)", raw, re.IGNORECASE)
    if vehicle_match:
        vehicle_ref = vehicle_match.group(1).strip()

    # Reference number (stock-like)
    if not vehicle_ref:
        ref_match = re.search(r"Ref\s*#:\s*(\S+)", raw, re.IGNORECASE)
        if ref_match:
            vehicle_ref = ref_match.group(1).strip()

    # Message
    msg_match = re.search(r"Message:\s*(.+?)(?:\n\n|\Z)", raw, re.IGNORECASE | re.DOTALL)
    if msg_match:
        message = msg_match.group(1).strip()

    if not phone and not email_addr:
        return None  # Nothing usable

    return NormalizedLead(
        source=Channel.EMAIL,
        name=name,
        phone=phone,
        email=email_addr,
        vehicle_ref=vehicle_ref,
        message=message,
        consent=True,
        raw={"raw": raw, "subject": subject, "from": from_addr, "parser": "autotrader"},
    )
