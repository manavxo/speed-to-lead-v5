"""Tests for app/config.py — dealer config validation, particularly the E.164 phone guard."""

import pytest
from pydantic import ValidationError

from app.config import (
    DealerConfig,
    Channels,
    SalesRep,
    Routing,
    Dealer,
    load_dealer_config,
)

# ── Valid E.164 numbers (should pass) ────────────────────────────────────────

VALID_PHONES = [
    "+17787623122",
    "+16045551234",
    "+12015550123",
    "+441632960000",
]


@pytest.mark.parametrize("phone", VALID_PHONES)
def test_e164_valid_phones_pass(phone):
    """Known-good E.164 numbers must be accepted."""
    c = Channels(sms_number=phone, whatsapp_sender=phone)
    assert c.sms_number == phone
    assert c.whatsapp_sender == phone


def test_e164_none_is_ok():
    """None/empty is allowed for optional phone fields."""
    c = Channels(sms_number=None, whatsapp_sender=None)
    assert c.sms_number is None
    assert c.whatsapp_sender is None


# ── Invalid / masked numbers (should fail) ───────────────────────────────────

INVALID_PHONES = [
    "+177****3122",       # asterisk-masked (the bug we're guarding against)
    "17787623122",        # missing leading +
    "+1 (778) 762-3122",  # formatted, not pure digits
    "+1778",              # too short (only 5 digits after +)
    "not-a-phone",        # garbage
]


@pytest.mark.parametrize("phone", INVALID_PHONES)
def test_e164_invalid_phones_rejected(phone):
    """Non-E.164 phone numbers must be rejected with a ValueError."""
    with pytest.raises(ValidationError, match="does not match E.164"):
        Channels(sms_number=phone)


# ── Model-level tests ────────────────────────────────────────────────────────

def test_dealer_main_phone_validated():
    """Dealer.main_phone is also guarded."""
    d = Dealer(slug="test", name="Test", main_phone="+17787623122")
    assert d.main_phone == "+17787623122"


def test_dealer_main_phone_masked_rejected():
    """Asterisk-masked main_phone is rejected."""
    with pytest.raises(ValidationError, match="does not match E.164"):
        Dealer(slug="test", name="Test", main_phone="+177****3122")


def test_sales_rep_phone_validated():
    """SalesRep.phone is required and must be E.164."""
    r = SalesRep(name="Bob", phone="+17787623122")
    assert r.phone == "+17787623122"


def test_sales_rep_phone_masked_rejected():
    """Asterisk-masked rep phone is rejected."""
    with pytest.raises(ValidationError, match="does not match E.164"):
        SalesRep(name="Bob", phone="+177****0199")


def test_routing_manager_phone_validated():
    """Routing.manager_phone is guarded."""
    r = Routing(manager_phone="+17787623122")
    assert r.manager_phone == "+17787623122"


def test_routing_manager_phone_masked_rejected():
    """Asterisk-masked manager_phone is rejected."""
    with pytest.raises(ValidationError, match="does not match E.164"):
        Routing(manager_phone="+177****3122")


# ── DealerConfig integration test ────────────────────────────────────────────

def test_load_dealer_config_valid():
    """Loading the real premier-auto.yaml must succeed (its numbers are valid)."""
    cfg = load_dealer_config("dealers/premier-auto.yaml")
    assert cfg.dealer.slug == "premier-auto"
    assert cfg.channels.sms_number is not None


def test_load_dealer_config_masked_rejected():
    """Injecting a masked number into the data must fail validation."""
    import yaml
    data = yaml.safe_load(open("dealers/premier-auto.yaml", encoding="utf-8"))
    data["channels"]["sms_number"] = "+177****3122"
    with pytest.raises(ValidationError, match="does not match E.164"):
        DealerConfig.model_validate(data)
