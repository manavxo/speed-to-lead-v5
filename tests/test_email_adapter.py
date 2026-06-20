"""1.4/1.5: Email adapter phone masking + consent regression tests.

Bug 1.4: email_lead.py masks phone at parse time (line 49) instead of storing
unmasked. Same bug fixed in route_lead.py but missed here.

Bug 1.5: email_lead.py sets consent=False (line 79). Listing site inquiries
have implied consent — customer submitted their info voluntarily.
"""

from __future__ import annotations

from app.adapters.intake.email_lead import EmailLeadAdapter
from app.models import Channel


def test_email_adapter_phone_stored_unmasked():
    """Phone should be stored unmasked, NOT passed through mask_phone()."""
    raw_email = (
        "Customer Name: John Smith\n"
        "Phone: +16045551234\n"
        "Email: john@example.com\n"
        "Vehicle: 2022 Honda Civic\n"
        "Message: I'm interested in this vehicle.\n"
        "Stock: PAG001\n"
    )
    payload = {"raw": raw_email}
    adapter = EmailLeadAdapter()
    result = adapter.parse(payload)

    # Phone should be stored unmasked — the full E.164 form
    assert result.phone is not None
    assert "***" not in result.phone, (
        f"Phone should NOT be masked at parse time. Got: {result.phone}"
    )
    assert result.phone == "+16045551234", (
        f"Expected unmasked +16045551234, got: {result.phone}"
    )


def test_email_adapter_consent_is_true():
    """Email leads from listing sites have implied consent — should be True."""
    raw_email = (
        "Customer Name: Jane Doe\n"
        "Phone: +16045559999\n"
        "Email: jane@example.com\n"
        "Vehicle: 2022 Toyota RAV4\n"
    )
    payload = {"raw": raw_email}
    adapter = EmailLeadAdapter()
    result = adapter.parse(payload)

    assert result.consent is True, (
        f"Expected consent=True for listing site leads, got: {result.consent}"
    )


def test_email_adapter_parse_full_lead():
    """Full parse should extract all fields correctly with unmasked phone."""
    raw_email = (
        "Customer Name: Bob Wilson\n"
        "Phone: 604-555-6789\n"
        "Email: bob@test.com\n"
        "Vehicle: 2023 Ford F-150\n"
        "Message: I'd like to schedule a test drive.\n"
        "Stock: FORD001\n"
    )
    payload = {"raw": raw_email}
    adapter = EmailLeadAdapter()
    result = adapter.parse(payload)

    assert result.name == "Bob Wilson"
    assert result.phone is not None
    assert "***" not in result.phone
    assert result.email == "bob@test.com"
    assert result.vehicle_ref == "FORD001"
    assert result.message is not None
    assert result.source == Channel.EMAIL
    assert result.consent is True
