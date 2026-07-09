"""Dealer website form email lead parser.

Most dealer websites send form-submission emails with labelled fields:
  Name: John Smith
  Phone: +1 604-555-1234
  Email: john@example.com
  Vehicle of Interest: 2023 Honda Civic
  Message: I'm interested in this vehicle.

This parser sits ahead of the generic fallback but after site-specific parsers.
It relies on the presence of labelled fields — if no labels are found it
returns None so generic gets a chance.
"""

from __future__ import annotations

import re

from app.adapters.intake import NormalizedLead
from app.models import Channel


def parse_dealer_website_form(raw: str, subject: str = "", from_addr: str = "") -> NormalizedLead | None:
    """Parse a dealer website form notification email into a NormalizedLead.

    Args:
        raw: Raw email body text.
        subject: Email subject (unused).
        from_addr: Sender email (unused).

    Returns:
        NormalizedLead if labelled fields were found, else None.
    """
    if not raw:
        return None

    name = None
    phone = None
    email_addr = None
    vehicle_ref = None
    message = None

    # Must have at least one labelled field to be a webform
    has_any_label = any(
        label in raw
        for label in ("Name:", "Full Name:", "First Name:", "Phone:", "Email:", "E-mail:")
    )
    if not has_any_label:
        return None

    name_match = re.search(r"(?:Full\s+)?(?:First\s+)?Name:\s*(.+)", raw, re.IGNORECASE)
    if name_match:
        name = name_match.group(1).strip()

    phone_match = re.search(r"(?:Phone|Mobile|Cell)(?:\s+Number)?:\s*([+\d\s().-]+)", raw, re.IGNORECASE)
    if phone_match:
        from app.adapters.intake import normalize_phone
        raw_phone = phone_match.group(1).strip()
        digits_only = re.sub(r"[^\d+]", "", raw_phone)
        phone = normalize_phone(digits_only)

    # Loose phone extraction if no labelled phone field
    if not phone:
        loose = re.search(r"\b(\+?1[-.\s]?)?\(?(\d{3})\)?[-.\s]?(\d{3})[-.\s]?(\d{4})\b", raw)
        if loose:
            groups = loose.groups()
            raw_phone = f"+1{groups[1]}{groups[2]}{groups[3]}"
            from app.adapters.intake import normalize_phone
            phone = normalize_phone(raw_phone)

    email_match = re.search(r"(?:Email|E-mail)(?:\s+Address)?:\s*(\S+@\S+)", raw, re.IGNORECASE)
    if email_match:
        email_addr = email_match.group(1).strip()

    vehicle_match = re.search(
        r"(?:Vehicle\s+of\s+Interest|Vehicle|Car\s+of\s+Interest|Model\s+of\s+Interest|Model|Stock\s+#):\s*(.+)",
        raw, re.IGNORECASE,
    )
    if vehicle_match:
        vehicle_ref = vehicle_match.group(1).strip()

    msg_match = re.search(r"(?:Message|Comments|Question|Notes):\s*(.+?)(?:\n\n|\Z)", raw, re.IGNORECASE | re.DOTALL)
    if msg_match:
        message = msg_match.group(1).strip()

    if not name and not email_addr and not phone:
        return None

    return NormalizedLead(
        source=Channel.EMAIL,
        name=name,
        phone=phone,
        email=email_addr,
        vehicle_ref=vehicle_ref,
        message=message,
        consent=True,
        raw={"raw": raw, "subject": subject, "from": from_addr, "parser": "dealer_website_form"},
    )
