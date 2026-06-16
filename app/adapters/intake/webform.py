"""Intake: dealer website form (the cleanest channel — start here). Floor channel for any dealer."""

from __future__ import annotations

import re

from app.adapters.intake import IntakeAdapter, NormalizedLead, mask_phone
from app.models import Channel


def _normalize_phone(raw: str | None) -> str | None:
    """Deprecated — use app.adapters.intake.normalize_phone instead."""
    from app.adapters.intake import normalize_phone
    return normalize_phone(raw)


class WebFormAdapter(IntakeAdapter):
    source = Channel.WEBFORM

    def parse(self, payload: dict) -> NormalizedLead:
        """Map a dealer website form payload to a NormalizedLead.

        Handles common field names: full_name, phone, email, vehicle_stock, consent_sms, etc.
        """
        name = payload.get("full_name") or payload.get("name") or payload.get("first_name", "")
        if not name and payload.get("first_name"):
            name = f"{payload['first_name']} {payload.get('last_name', '')}".strip()

        phone = mask_phone(_normalize_phone(payload.get("phone") or payload.get("phone_number")))
        email = payload.get("email") or payload.get("email_address")

        # Vehicle reference: prefer stock#, fall back to VIN, then title
        vehicle_ref = (
            payload.get("vehicle_stock")
            or payload.get("vehicle_stock_no")
            or payload.get("vin")
            or payload.get("vehicle_vin")
        )

        consent = bool(
            payload.get("consent_sms")
            or payload.get("consent")
            or payload.get("opt_in")
        )

        message = payload.get("message") or payload.get("comments") or payload.get("notes")

        return NormalizedLead(
            source=Channel.WEBFORM,
            name=name.strip() if name else None,
            phone=phone,
            email=email,
            vehicle_ref=vehicle_ref,
            message=message,
            consent=consent,
            raw=dict(payload),
        )