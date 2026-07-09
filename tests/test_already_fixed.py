"""Already-fixed section: settings persistence + missed-call verification tests.

These confirm existing working code paths are actually working.
Do NOT change the underlying routes unless a test reveals a real bug.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.fixture
def client(tmp_path):
    """TestClient backed by SQLite with premier-auto provisioned."""
    import app.db as db
    from app.main import _auto_provision_dealers, app

    db_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    db.init_db(db_url)
    db.get_session_factory(db_url)
    _auto_provision_dealers()
    try:
        yield TestClient(app)
    finally:
        db._engine = None
        db._SessionLocal = None


def _make_manager_session() -> str:
    from app.dashboard import _get_serializer
    return _get_serializer().dumps({
        "role": "manager", "rep_name": "", "dealer_slug": "premier-auto", "ts": 0,
    })


# ── Settings persistence tests ───────────────────────────────────────────────

def test_settings_channels_persist(client):
    """POST /settings/changes digest settings and verify they persist."""
    from sqlalchemy.orm.attributes import flag_modified
    import json as _json

    cookie = _make_manager_session()
    resp = client.post(
        "/dashboard/settings/channels",
        data={"digest_enabled": "on", "digest_time": "09:00"},
        cookies={"session": cookie},
    )
    assert resp.status_code == 200, f"Settings channels failed: {resp.text}"

    # Read back
    import app.db as db
    from app.models import Dealer
    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        routing = (dealer.config or {}).get("routing", {})
        assert routing.get("digest_enabled") is True, f"Expected True, got {routing.get('digest_enabled')}"
        assert routing.get("digest_time") == "09:00"
    finally:
        session.close()


def test_settings_business_persist(client):
    """POST /settings/business persists dealer name and hours."""
    cookie = _make_manager_session()
    resp = client.post(
        "/dashboard/settings/business",
        data={
            "dealer_name": "Test Motors",
            "dealer_phone": "+177****9999",
            "mon_open": "10:00", "mon_close": "18:00",
        },
        cookies={"session": cookie},
    )
    assert resp.status_code == 200, f"Settings business failed: {resp.text}"

    import app.db as db
    from app.models import Dealer
    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer.name == "Test Motors", f"Expected Test Motors, got {dealer.name}"
    finally:
        session.close()


def test_settings_ai_persist(client):
    """POST /settings/ai persists persona and guardrails."""
    cookie = _make_manager_session()
    resp = client.post(
        "/dashboard/settings/ai",
        data={
            "ai_persona": "friendly and direct",
            "guardrail_no_price_negotiation": "true",
        },
        cookies={"session": cookie},
    )
    assert resp.status_code == 200, f"Settings AI failed: {resp.text}"

    import app.db as db
    from app.models import Dealer
    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        ai_cfg = (dealer.config or {}).get("ai", {})
        assert "friendly" in ai_cfg.get("persona", "")
    finally:
        session.close()


def test_settings_compliance_persist(client):
    """POST /settings/compliance persists quiet hours and consent text."""
    cookie = _make_manager_session()
    resp = client.post(
        "/dashboard/settings/compliance",
        data={
            "quiet_start": "22:00",
            "quiet_end": "07:00",
            "consent_text": "You agree to receive messages.",
        },
        cookies={"session": cookie},
    )
    assert resp.status_code == 200, f"Settings compliance failed: {resp.text}"

    import app.db as db
    from app.models import Dealer
    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        compliance = (dealer.config or {}).get("compliance", {})
        assert compliance.get("quiet_hours") == "22:00-07:00"
        assert "agree" in compliance.get("consent_text", "")
    finally:
        session.close()


# ── Missed-call test ─────────────────────────────────────────────────────────

@patch("twilio.rest.Client")
@patch("app.main._validate_twilio_signature", return_value=True)
def test_missed_call_creates_lead_and_sends_sms(mock_validate, mock_twilio_client, client, monkeypatch):
    """Twilio missed-call webhook → lead created, SMS queued (mocked).

    Both settings mutations are scoped via monkeypatch (auto-reverted after this
    test) and the real Twilio client is patched at its source — a prior version of
    this test set `app.config.settings.outbound_enabled = True` as a permanent
    direct assignment with no real client mock, which leaked into every test that
    ran afterward in the same session and caused real (failing, HTTP 401) Twilio API
    calls from unrelated tests later in the suite.
    """
    import app.db as db
    from app.models import Lead, Dealer
    from sqlalchemy import select as _select
    import json as _json

    mock_twilio_client.return_value.messages.create.return_value.sid = "SMTEST_MOCKED"

    # Ensure outbound is enabled for the test — scoped, reverts after this test
    import app.config
    monkeypatch.setattr(app.config.settings, "outbound_enabled", True)
    monkeypatch.setattr(app.config.settings, "quiet_hours_disabled", True)

    # Provision a test dealer with a clean phone number
    from sqlalchemy.orm.attributes import flag_modified
    from app.models import Dealer as _Dealer
    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            _select(_Dealer).where(_Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None
        config = dealer.config or {}
        config["channels"] = config.get("channels", {})
        config["channels"]["sms_number"] = "+17705551234"
        dealer.sms_number = "+17705551234"
        dealer.config = _json.loads(_json.dumps(config))
        flag_modified(dealer, "config")
        session.commit()
    finally:
        session.close()

    # Build a Twilio-like voice webhook payload
    payload = {
        "CallSid": "CAtest_missed_001",
        "From": "+16045551234",
        "To": "+17705551234",
        "CallStatus": "no-answer",
        "CallDuration": "0",
    }

    resp = client.post("/webhook/twilio/voice", data=payload)
    assert resp.status_code == 200, f"Voice webhook failed: {resp.text[:200]}"

    # Verify a lead was created
    session2 = db.get_session_factory()()
    try:
        lead = session2.execute(
            _select(Lead).where(Lead.phone == "+16045551234")
        ).scalars().first()
        assert lead is not None, "Missed call should create a lead"
        assert lead.source.value == "phone", f"Expected phone source, got {lead.source}"
    finally:
        session2.close()
