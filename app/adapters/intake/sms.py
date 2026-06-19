"""Intake: inbound SMS (lead-facing). Also the path where STOP/opt-out keywords arrive."""

from __future__ import annotations

import re

from app.adapters.intake import IntakeAdapter, NormalizedLead
from app.models import Channel


def _normalize_phone(raw: str | None) -> str | None:
    """Deprecated — use app.adapters.intake.normalize_phone instead."""
    from app.adapters.intake import normalize_phone
    return normalize_phone(raw)


class TwilioSmsAdapter(IntakeAdapter):
    source = Channel.SMS

    def parse(self, payload: dict) -> NormalizedLead:
        """Map Twilio inbound SMS form fields to a NormalizedLead.

        Twilio sends: From, Body, To, MessageSid, etc.
        """
        phone = _normalize_phone(payload.get("From") or payload.get("from"))
        body = payload.get("Body") or payload.get("body", "")
        to_number = payload.get("To") or payload.get("to")

        return NormalizedLead(
            source=Channel.SMS,
            name=None,  # SMS leads don't include name
            phone=phone,
            email=None,
            vehicle_ref=None,
            message=body,
            consent=True,  # CASL implied consent: customer texted us first
            raw={
                "from": phone,
                "body": body,
                "to": to_number,
                "message_sid": payload.get("MessageSid") or payload.get("message_sid"),
            },
        )
