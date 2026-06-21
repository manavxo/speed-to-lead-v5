"""Phase 9: Site-specific email parser tests.
"""

from __future__ import annotations

from app.adapters.intake.email_parsers.autotrader_ca import parse_autotrader
from app.adapters.intake.email_parsers.cargurus import parse_cargurus
from app.adapters.intake.email_parsers.generic import parse_generic
from app.adapters.intake.email_parsers import parse_email
from app.models import Channel


# ---------------------------------------------------------------------------
# AutoTrader
# ---------------------------------------------------------------------------

AUTOTRADER_EMAIL = (
    "Customer Name: John Smith\n"
    "Phone: +1 604-555-1234\n"
    "Email: john@example.com\n"
    "Vehicle: 2022 Honda Civic LX\n"
    "Message: Is this still available?\n"
    "Ref #: ABC123\n"
)

AUTOTRADER_NO_PHONE = (
    "Customer Name: Jane Doe\n"
    "Email: jane@example.com\n"
    "Vehicle: 2023 Toyota RAV4\n"
    "Message: Interested in this vehicle.\n"
)


def test_autotrader_parses_full_lead():
    """AutoTrader parser extracts all fields including phone."""
    result = parse_autotrader(AUTOTRADER_EMAIL)
    assert result is not None
    assert result.name == "John Smith"
    assert result.phone == "+16045551234"
    assert result.email == "john@example.com"
    assert "Civic" in (result.vehicle_ref or "")
    assert result.consent is True
    assert result.source == Channel.EMAIL


def test_autotrader_parses_no_phone():
    """AutoTrader parser works even without a phone number."""
    result = parse_autotrader(AUTOTRADER_NO_PHONE)
    assert result is not None
    assert result.name == "Jane Doe"
    assert result.email == "jane@example.com"
    assert result.phone is None


def test_autotrader_rejects_non_autotrader():
    """Parser returns None for non-AutoTrader content."""
    result = parse_autotrader("Random email with no structure")
    assert result is None


# ---------------------------------------------------------------------------
# CarGurus
# ---------------------------------------------------------------------------

CARGURUS_EMAIL = (
    "Customer Name: Bob Wilson\n"
    "Phone: 604.555.6789\n"
    "Email: bob@test.com\n"
    "Stock #: FORD001\n"
    "Listing ID: 87654321\n"
    "Message: I'd like to schedule a test drive.\n"
)


def test_cargurus_parses_full_lead():
    """CarGurus parser extracts all fields."""
    result = parse_cargurus(CARGURUS_EMAIL)
    assert result is not None
    assert result.name == "Bob Wilson"
    assert result.phone == "+16045556789"
    assert result.email == "bob@test.com"
    assert result.vehicle_ref == "FORD001"


def test_cargurus_rejects_non_cargurus():
    """Parser returns None for non-CarGurus content."""
    result = parse_cargurus("Just some text")
    assert result is None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_registry_tries_autotrader_first():
    """Registry routes AutoTrader emails correctly."""
    result = parse_email(AUTOTRADER_EMAIL)
    assert result is not None
    assert result.name == "John Smith"


def test_registry_falls_back_to_generic():
    """Registry falls back to generic for unknown formats."""
    result = parse_email("Some random inquiry about a car\nContact: mike@test.com")
    assert result is not None
    assert result.email == "mike@test.com"
