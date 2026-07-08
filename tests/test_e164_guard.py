"""E.164 validation regression guard — dealer phone numbers must be valid E.164."""
import pytest
import yaml
from app.config import DealerConfig, SalesRep, _validate_e164

class TestE164Validation:
    """Phase 2 guard: detects masked/corrupted phone numbers in dealer YAML configs."""

    def test_real_e164_accepted(self):
        """Valid E.164 numbers pass validation."""
        result = _validate_e164("+17745553122")
        assert result == "+17745553122"

    def test_short_e164_accepted(self):
        """10-digit E.164 (minimum) passes."""
        result = _validate_e164("+1604555123")
        assert result == "+1604555123"

    def test_masked_number_rejected(self):
        """Asterisk-masked numbers are caught."""
        with pytest.raises(ValueError, match="does not match E.164"):
            _validate_e164("+177****3122")

    def test_no_plus_rejected(self):
        """Missing + prefix is caught."""
        with pytest.raises(ValueError, match="does not match E.164"):
            _validate_e164("16045551234")

    def test_too_short_rejected(self):
        """Too few digits is caught."""
        with pytest.raises(ValueError, match="does not match E.164"):
            _validate_e164("+1555")

    def test_letters_rejected(self):
        """Non-digit characters are caught."""
        with pytest.raises(ValueError, match="does not match E.164"):
            _validate_e164("+1ABC5551234")

    def test_none_accepted(self):
        """None values are accepted (optional phone fields)."""
        result = _validate_e164(None)
        assert result is None

    def test_empty_string_accepted(self):
        """Empty string values are accepted (optional fields)."""
        result = _validate_e164("")
        assert result == ""

    def test_salesrep_directly_rejects_masked(self):
        """SalesRep model itself rejects asterisk phone numbers (regression)."""
        with pytest.raises(ValueError, match="does not match E.164"):
            SalesRep(name="Test", pin="1234", phone="+177****3122", active=True)

    def test_salesrep_directly_accepts_real(self):
        """SalesRep model accepts valid E.164 numbers."""
        r = SalesRep(name="Test", pin="1234", phone="+17745553122", active=True)
        assert r.phone == "+17745553122"

    def test_dealer_yaml_phone_validity(self):
        """Check that ALL phones in the committed premier-auto.yaml are valid E.164.
        
        This test will FAIL if someone introduces asterisk-masked numbers,
        which is the exact corruption pattern from the Phase 2 bug.
        """
        data = yaml.safe_load(open("dealers/premier-auto.yaml"))
        cfg = DealerConfig.model_validate(data)
        
        # Debug: print what we got
        print(f"\nLoaded {len(cfg.sales_team)} reps from YAML")
        print(f"Dealer main_phone: {cfg.dealer.main_phone!r}")
        print(f"SMS number: {cfg.channels.sms_number!r}")
        print(f"WhatsApp sender: {cfg.channels.whatsapp_sender!r}")
        for r in cfg.sales_team:
            print(f"  {r.name}: phone={r.phone!r}")
        if cfg.routing.manager_phone:
            print(f"Manager: phone={cfg.routing.manager_phone!r}")
        
        # Check dealer main_phone
        assert cfg.dealer.main_phone is None or "+" in cfg.dealer.main_phone, \
            f"main_phone looks corrupt: {cfg.dealer.main_phone!r}"
        
        # Check channel phones
        ch = cfg.channels
        for field_name in ("sms_number", "whatsapp_sender", "voice_number"):
            val = getattr(ch, field_name, None)
            if val:
                assert "*" not in val, \
                    f"channels.{field_name} contains asterisks (corrupted): {val!r}"
        
        # Check sales_team phones
        for r in cfg.sales_team:
            assert "*" not in r.phone, \
                f"sales_team.{r.name}.phone contains asterisks (corrupted): {r.phone!r}"
        
        # Check manager_phone
        if cfg.routing.manager_phone:
            assert "*" not in cfg.routing.manager_phone, \
                f"routing.manager_phone contains asterisks (corrupted): {cfg.routing.manager_phone!r}"
