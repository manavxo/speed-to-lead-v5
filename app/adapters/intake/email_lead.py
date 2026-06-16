"""Intake: parse third-party lead emails (Cars.com / CarGurus / AutoTrader.ca / Kijiji).

These arrive at channels.lead_email_inbox. Most use predictable templates; tools/parse_lead_email.py
does the heavy parsing (with an LLM fallback for unknown templates).
"""

from __future__ import annotations

import re

from app.adapters.intake import IntakeAdapter, NormalizedLead, mask_phone
from app.models import Channel


def _normalize_phone(raw: str | None) -> str | None:
    """Deprecated — use app.adapters.intake.normalize_phone instead."""
    from app.adapters.intake import normalize_phone
    return normalize_phone(raw)


class EmailLeadAdapter(IntakeAdapter):
    source = Channel.EMAIL

    def parse(self, payload: dict) -> NormalizedLead:
        """Parse a raw email payload into a NormalizedLead.

        Supports CarGurus-style templates and generic email parsing.
        The `payload` dict should contain at minimum `raw` (the email text).
        """
        raw = payload.get("raw", "")

        # Try to extract common fields from email body using regex patterns
        name = None
        phone = None
        email_addr = None
        vehicle_ref = None

        # Common CarGurus patterns
        name_match = re.search(r"Customer Name:\s*(.+)", raw, re.IGNORECASE)
        if name_match:
            name = name_match.group(1).strip()
        else:
            name_match = re.search(r"Name:\s*(.+)", raw, re.IGNORECASE)
            if name_match:
                name = name_match.group(1).strip()

        phone_match = re.search(r"Phone:\s*([+\d\s()-]+)", raw, re.IGNORECASE)
        if phone_match:
            phone = mask_phone(_normalize_phone(phone_match.group(1).strip()))

        email_match = re.search(r"Email:\s*(\S+@\S+)", raw, re.IGNORECASE)
        if email_match:
            email_addr = email_match.group(1).strip()

        # Vehicle reference: look for stock numbers, VINs, or vehicle descriptions
        stock_match = re.search(r"Stock[:\s#]*([A-Z0-9]+)", raw, re.IGNORECASE)
        if stock_match:
            vehicle_ref = stock_match.group(1).strip()
        else:
            vin_match = re.search(r"\b([A-HJ-NPR-Z0-9]{17})\b", raw)
            if vin_match:
                vehicle_ref = vin_match.group(1).strip()

        # Extract vehicle title/description if present
        vehicle_match = re.search(r"Vehicle:\s*(.+)", raw, re.IGNORECASE)
        if vehicle_match and not vehicle_ref:
            vehicle_ref = vehicle_match.group(1).strip()

        message_match = re.search(r"Message:\s*(.+?)(?:\n\n|\Z)", raw, re.IGNORECASE | re.DOTALL)
        message = message_match.group(1).strip() if message_match else None

        return NormalizedLead(
            source=Channel.EMAIL,
            name=name,
            phone=phone,
            email=email_addr,
            vehicle_ref=vehicle_ref,
            message=message,
            consent=False,  # Email leads don't have explicit SMS consent
            raw={"raw": raw},
        )