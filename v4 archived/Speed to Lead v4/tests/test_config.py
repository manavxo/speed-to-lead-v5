"""Phase 1 — config & onboarding. These run today against the implemented schema."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from app.config import DealerConfig, load_dealer_config


def _demo_dict(fixtures) -> dict:
    return yaml.safe_load((fixtures / "demo-dealer.yaml").read_text(encoding="utf-8"))


def test_example_dealer_is_valid(root):
    cfg = load_dealer_config(root / "dealers" / "example-dealer.yaml")
    assert cfg.dealer.slug == "sunrise-auto"
    assert cfg.dealer.timezone == "America/Vancouver"
    assert cfg.compliance.region == "CA-BC"
    assert "ARRET" in cfg.compliance.opt_out_keywords  # bilingual opt-out


def test_demo_dealer_loads(demo_config_path):
    cfg = load_dealer_config(demo_config_path)
    assert cfg.dealer.slug == "demo-auto"
    assert len(cfg.sales_team) == 3
    assert sum(r.active for r in cfg.sales_team) == 2  # Priya is inactive


def test_missing_slug_is_rejected(fixtures):
    data = _demo_dict(fixtures)
    del data["dealer"]["slug"]
    with pytest.raises(ValidationError):
        DealerConfig.model_validate(data)


def test_rep_without_phone_is_rejected(fixtures):
    data = _demo_dict(fixtures)
    data["sales_team"].append({"name": "NoNumber", "active": True})
    with pytest.raises(ValidationError):
        DealerConfig.model_validate(data)


def test_unknown_inventory_source_is_rejected(fixtures):
    data = _demo_dict(fixtures)
    data["inventory"]["source"] = "carrier-pigeon"
    with pytest.raises(ValidationError):
        DealerConfig.model_validate(data)


def test_unknown_lead_org_mode_is_rejected(fixtures):
    data = _demo_dict(fixtures)
    data["lead_org"]["mode"] = "telepathy"
    with pytest.raises(ValidationError):
        DealerConfig.model_validate(data)


def test_defaults_applied_when_blocks_omitted(fixtures):
    minimal = {"dealer": {"slug": "x", "name": "X"}}
    cfg = DealerConfig.model_validate(minimal)
    assert cfg.routing.claim_timeout_min == 5
    assert cfg.followups.cadence_min == [60, 1440, 4320, 10080]
    assert cfg.lead_org.mode.value == "native"  # universal floor
