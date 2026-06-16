"""Tests for the canonical phone normalization function.

Every phone number in the system — from Twilio payloads, web forms,
dealer YAMLs, and sales team configs — must go through normalize_phone()
before comparison or storage. These tests ensure it handles every format.
"""

from app.adapters.intake import normalize_phone


class TestNormalizePhone:
    """normalize_phone() must return E.164 format (+1XXXXXXXXXX) for all inputs."""

    def test_e164_with_plus(self):
        """Already-correct format passes through unchanged."""
        assert normalize_phone("+14155238886") == "+14155238886"

    def test_e164_without_plus(self):
        """11-digit number starting with 1 gets + prefix."""
        assert normalize_phone("14155238886") == "+14155238886"

    def test_10_digit_north_american(self):
        """10-digit number gets country code 1 prepended."""
        assert normalize_phone("4155238886") == "+14155238886"

    def test_with_spaces_and_dashes(self):
        """Common human formatting is stripped."""
        assert normalize_phone("+1 (415) 523-8886") == "+14155238886"

    def test_with_dashes_only(self):
        """Dash-separated numbers normalize correctly."""
        assert normalize_phone("415-523-8886") == "+14155238886"

    def test_with_dots(self):
        """Dot-separated numbers normalize correctly."""
        assert normalize_phone("415.523.8886") == "+14155238886"

    def test_whatsapp_prefix(self):
        """Twilio WhatsApp payload format (whatsapp:+1...) is handled."""
        assert normalize_phone("whatsapp:+14155238886") == "+14155238886"

    def test_whatsapp_prefix_no_plus(self):
        """WhatsApp prefix without + in the number."""
        assert normalize_phone("whatsapp:14155238886") == "+14155238886"

    def test_canadian_number(self):
        """Canadian 604 area code normalizes correctly."""
        assert normalize_phone("+1 (604) 839-2870") == "+16048392870"

    def test_canadian_number_bare(self):
        """Canadian number without formatting."""
        assert normalize_phone("6048392870") == "+16048392870"

    def test_empty_string(self):
        """Empty string returns None."""
        assert normalize_phone("") is None

    def test_none(self):
        """None returns None."""
        assert normalize_phone(None) is None

    def test_whitespace_only(self):
        """Whitespace-only returns None."""
        assert normalize_phone("   ") is None

    def test_no_digits(self):
        """String with no digits returns None."""
        assert normalize_phone("abc") is None

    def test_consistency_across_formats(self):
        """All representations of the same number must produce identical output."""
        formats = [
            "+14155238886",
            "14155238886",
            "4155238886",
            "+1 (415) 523-8886",
            "+1-415-523-8886",
            "1-415-523-8886",
            "(415) 523-8886",
            "415.523.8886",
            "whatsapp:+14155238886",
            "whatsapp:14155238886",
            "whatsapp:4155238886",
        ]
        results = {normalize_phone(f) for f in formats}
        assert results == {"+14155238886"}, f"Mismatch: {results}"

    def test_dealer_yaml_format(self):
        """The format used in dealers/premier-auto.yaml."""
        assert normalize_phone("+14155238886") == "+14155238886"

    def test_twilio_inbound_sms_from(self):
        """Twilio SMS From field format."""
        assert normalize_phone("+16048392870") == "+16048392870"

    def test_twilio_inbound_whatsapp_from(self):
        """Twilio WhatsApp From field format (with whatsapp: prefix)."""
        raw = "whatsapp:+16048392870"
        # The caller strips "whatsapp:" first, then normalizes
        stripped = raw.replace("whatsapp:", "")
        assert normalize_phone(stripped) == "+16048392870"
