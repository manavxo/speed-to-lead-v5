"""CarGurus email lead parser.

CarGurus lead notification emails typically follow:
  Customer Name: John Smith
  Phone: +1 604-555-1234
  Email: john@example.com
  Stock #: PAG001
  Listing ID: 12345678
  Message: Is this still available?
"""

from __future__ import annotations

import re

from app.adapters.intake import NormalizedLead
from app.models import Channel


def parse_cargurus(raw: str, subject: str = "", from_addr: str = "") -> NormalizedLead | None:
    """Parse a CarGurus lead email into a NormalizedLead.

    Args:
        raw: Raw email body text.
        subject: Email subject (unused).
        from_addr: Sender email (unused).

    Returns:
        NormalizedLead if parsing succeeded, else None.
    """
    if not raw:
        return None

    # CarGurus emails often mention "CarGurus" in the body
    if "Customer Name:" not in raw:
        return None

    name = None
    phone = None
    email_addr = None
    vehicle_ref = None
    message = None

    name_match = re.search(r"Customer\s*Name:\s*(.+)", raw, re.IGNORECASE)
    if name_match:
        name = name_match.group(1).strip()

    phone_match = re.search(r"Phone:\s*([+\d\s().-]+)", raw, re.IGNORECASE)
    if phone_match:
        from app.adapters.intake import normalize_phone
        raw_phone = phone_match.group(1).strip()
        # Strip non-digit chars for clean normalization
        digits_only = re.sub(r"[^\d+]", "", raw_phone)
        phone = normalize_phone(digits_only)

    email_match = re.search(r"Email:\s*(\S+@\S+)", raw, re.IGNORECASE)
    if email_match:
        email_addr = email_match.group(1).strip()

    # Stock number is the primary vehicle reference for CarGurus
    stock_match = re.search(r"Stock\s*#:\s*(\S+)", raw, re.IGNORECASE)
    if stock_match:
        vehicle_ref = stock_match.group(1).strip()
    else:
        listing_match = re.search(r"Listing\s*ID:\s*(\S+)", raw, re.IGNORECASE)
        if listing_match:
            vehicle_ref = listing_match.group(1).strip()

    msg_match = re.search(r"Message:\s*(.+?)(?:\n\n|\Z)", raw, re.IGNORECASE | re.DOTALL)
    if msg_match:
        message = msg_match.group(1).strip()

    if not phone and not email_addr:
        return None

    return NormalizedLead(
        source=Channel.EMAIL,
        name=name,
        phone=phone,
        email=email_addr,
        vehicle_ref=vehicle_ref,
        message=message,
        consent=True,
        raw={"raw": raw, "subject": subject, "from": from_addr, "parser": "cargurus"},
    )
