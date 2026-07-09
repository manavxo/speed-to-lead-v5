"""Cars.com email lead parser.

Cars.com lead notification emails typically follow:
  Name: John Smith
  Phone: +1 604-555-1234
  Email: john@example.com
  Vehicle: 2023 Honda Civic LX
  Message: Is this still available?
"""

from __future__ import annotations

import re

from app.adapters.intake import NormalizedLead
from app.models import Channel


def parse_cars_com(raw: str, subject: str = "", from_addr: str = "") -> NormalizedLead | None:
    """Parse a Cars.com lead email into a NormalizedLead.

    Args:
        raw: Raw email body text.
        subject: Email subject line.
        from_addr: Sender email (unused).

    Returns:
        NormalizedLead if parsing succeeded, else None.
    """
    if not raw:
        return None

    # Require "cars.com" in the body or subject explicitly — "cars" alone is too generic.
    if "cars.com" not in raw.lower() and "cars.com" not in subject.lower():
        return None

    name = None
    phone = None
    email_addr = None
    vehicle_ref = None
    message = None

    name_match = re.search(r"(?:Full\s+)?Name:\s*(.+)", raw, re.IGNORECASE)
    if name_match:
        name = name_match.group(1).strip()

    phone_match = re.search(r"Phone(?:\s+Number)?:\s*([+\d\s().-]+)", raw, re.IGNORECASE)
    if phone_match:
        from app.adapters.intake import normalize_phone
        raw_phone = phone_match.group(1).strip()
        digits_only = re.sub(r"[^\d+]", "", raw_phone)
        phone = normalize_phone(digits_only)

    email_match = re.search(r"Email(?:\s+Address)?:\s*(\S+@\S+)", raw, re.IGNORECASE)
    if email_match:
        email_addr = email_match.group(1).strip()

    # Vehicle reference
    vehicle_match = re.search(r"(?:Vehicle|Listing):\s*(.+)", raw, re.IGNORECASE)
    if vehicle_match:
        vehicle_ref = vehicle_match.group(1).strip()

    # Message
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
        raw={"raw": raw, "subject": subject, "from": from_addr, "parser": "cars_com"},
    )
