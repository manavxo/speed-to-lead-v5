"""Phase 3 — intake adapters (Axis 3).

Each test documents the expected NormalizedLead for its fixture (see fixtures/*.json|txt).
"""

from __future__ import annotations

import json
from pathlib import Path


from app.adapters.intake.email_lead import EmailLeadAdapter
from app.adapters.intake.twilio_sms import TwilioSmsAdapter
from app.adapters.intake.webform import WebFormAdapter


def test_webform_parse(fixtures):
    payload = json.loads((fixtures / "webform_payload.json").read_text(encoding="utf-8"))
    lead = WebFormAdapter().parse(payload)
    assert lead.name == "Sarah Chen"
    assert lead.phone == "+160****1234"      # normalized to E.164
    assert lead.vehicle_ref == "SA1001"
    assert lead.consent is True               # consent_sms checkbox captured (CASL)
    assert lead.email == "sarah.chen@example.com"


def test_email_lead_parse(fixtures):
    raw = (fixtures / "lead_email_cargurus.txt").read_text(encoding="utf-8")
    lead = EmailLeadAdapter().parse({"raw": raw})
    assert lead.name == "Marcus Bell"
    assert lead.vehicle_ref == "SA1002"
    assert lead.email == "marcus.bell@example.com"
    assert lead.phone == "+177****9087"


def test_sms_inquiry_parse(fixtures):
    cases = json.loads((fixtures / "twilio_sms_inbound.json").read_text(encoding="utf-8"))
    lead = TwilioSmsAdapter().parse(cases["inquiry"])
    assert lead.phone == "+160****1234"
    assert lead.message == "Hi, still have the silver RAV4?"
    assert lead.consent is True  # SMS leads have CASL implied consent (customer texted first)


def test_webform_minimal_payload():
    """Webform adapter handles missing optional fields gracefully."""
    lead = WebFormAdapter().parse({"full_name": "Test User", "consent_sms": True})
    assert lead.name == "Test User"
    assert lead.phone is None
    assert lead.consent is True


def test_webform_phone_normalization():
    """Phone numbers are normalized to E.164."""
    adapter = WebFormAdapter()
    lead = adapter.parse({"phone": "(604) 555-1234"})
    assert lead.phone == "+160****1234"

    lead2 = adapter.parse({"phone": "6045551234"})
    assert lead2.phone == "+160****1234"

    lead3 = adapter.parse({"phone": "+160****1234"})
    assert lead3.phone == "+160****1234"


def test_ingest_lead_creates_auto_replied(db_session, fake_twilio):
    """Full intake pipeline: webform parse -> ingest_lead -> AUTO_REPLIED state."""
    from app.models import Dealer
    from tools.route_lead import ingest_lead

    # Set up dealer
    dealer = Dealer(slug="test-dealer", name="Test Auto", config={
        "dealer": {"name": "Test Auto", "timezone": "America/Vancouver"},
        "compliance": {
            "consent_text": "By submitting you agree to receive texts from Test Auto. Reply STOP to opt out.",
            "quiet_hours": "21:00-08:00",
        },
        "channels": {"sms_number": "+177****0111"},
    })
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    # Parse webform
    payload = json.loads((fixtures_path() / "webform_payload.json").read_text(encoding="utf-8"))
    lead_data = WebFormAdapter().parse(payload)

    # Ingest
    lead = ingest_lead(db_session, dealer, lead_data)

    from app.models import LeadState
    assert lead.state == LeadState.AUTO_REPLIED
    assert lead.name == "Sarah Chen"
    assert lead.phone == "+160****1234"
    assert lead.consent is True


def fixtures_path() -> Path:
    return Path(__file__).resolve().parent / "fixtures"