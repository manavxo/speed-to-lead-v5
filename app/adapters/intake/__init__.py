"""AXIS 3 — intake adapters: normalize any lead channel into a canonical Lead.

Each adapter takes a raw provider payload (a webhook body, a parsed email, etc.) and returns a
`NormalizedLead`. `tools/route_lead.py` / the engine persists it as a `Lead` and starts the
speed-to-lead flow. Adding a channel = one adapter here + one webhook route in `app/main.py`.
"""

from __future__ import annotations

import abc
from typing import Optional

from pydantic import BaseModel

from app.models import Channel


class NormalizedLead(BaseModel):
    """Canonical inbound-lead shape produced by every Axis-3 adapter (pre-persistence)."""
    source: Channel
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    vehicle_ref: Optional[str] = None     # stock#, VIN, listing URL, or "2019 Honda Civic"
    message: Optional[str] = None         # the lead's first message/inquiry text, if any
    consent: bool = False                 # explicit consent captured at submission (CASL)
    raw: dict = {}


class IntakeAdapter(abc.ABC):
    """Implement one per channel (webform, email_lead, twilio_sms, messenger, phone)."""

    source: Channel

    @abc.abstractmethod
    def parse(self, payload: dict) -> NormalizedLead:  # pragma: no cover - interface
        """Map a raw provider payload to a NormalizedLead."""
        raise NotImplementedError


def mask_phone(raw: str | None) -> str | None:
    """Mask a phone number for PIPA-BC compliance: +1XXXXXXXXXX -> +1XX****XXXX.

    If the number is already masked (contains '*'), return as-is.
    """
    if not raw:
        return raw
    if "*" in raw:
        return raw
    import re
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return f"+1{digits[:2]}****{digits[-4:]}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits[:3]}****{digits[-4:]}"
    return raw


__all__ = ["NormalizedLead", "IntakeAdapter", "mask_phone"]
