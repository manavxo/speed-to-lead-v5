"""P1-2: Real Twilio WhatsApp + SMS transport for notify_rep().

The unit tests below mock twilio.rest.Client and assert on the call kwargs.
This proves the contract: the right to / from_ / content_sid / content_variables
land on the Twilio client when notify_rep is asked to actually send.

A live integration test (gated on RUN_TWILIO_INTEGRATION=true) lands at the
bottom of the file. It is opt-in per the v5 hard rule: never burn Twilio
credits on automatic tests.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.config import settings
from app.models import Channel, Dealer, Lead, LeadState, Message


# --- Shared fixtures (mirror test_notify_rep.py) -----------------------------

@pytest.fixture
def nr_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def nr_session(nr_engine):
    TestSession = sessionmaker(bind=nr_engine, expire_on_commit=False)
    session = TestSession()
    yield session
    session.close()


@pytest.fixture
def dealer_with_rep(nr_session):
    dealer = Dealer(
        slug="twilio-test",
        name="Twilio Test Dealer",
        sms_number="+177****0099",
        whatsapp_sender="+141****0099",
        config={
            "dealer": {"name": "Twilio Test Dealer"},
            "channels": {
                "sms_number": "+177****0099",
                "whatsapp_sender": "+141****0099",
            },
            "sales_team": [
                {
                    "name": "Mike",
                    "phone": "+160****4001",
                    "active": True,
                    "notify_backend": "twilio_whatsapp",
                    "notify_template_sid": "HXtemplateSID123",
                }
            ],
        },
    )
    nr_session.add(dealer)
    nr_session.commit()
    nr_session.refresh(dealer)
    return dealer


@pytest.fixture
def lead_for_notify(nr_session, dealer_with_rep):
    lead = Lead(
        dealer_id=dealer_with_rep.id,
        source=Channel.SMS,
        name="Real Twilio Test",
        phone="+160****4999",
        state=LeadState.ASSIGNED,
    )
    nr_session.add(lead)
    nr_session.commit()
    nr_session.refresh(lead)
    return lead


# --- Unit tests: real Twilio call with mocked Client -------------------------

def test_real_whatsapp_uses_template_content_sid(
    nr_session, dealer_with_rep, lead_for_notify, monkeypatch
):
    """When a template_sid is set, the Twilio call uses content_sid + content_variables."""
    from tools.notify_rep import notify_rep

    # Mock the Twilio Client before the call
    fake_client = MagicMock()
    fake_message = MagicMock()
    fake_message.sid = "SM_real_whatsapp_123"
    fake_client.messages.create.return_value = fake_message

    monkeypatch.setattr(settings, "outbound_enabled", True)
    monkeypatch.setattr(settings, "twilio_account_sid", "AC_fake_sid")
    monkeypatch.setattr(settings, "twilio_auth_token", "test_auth_token_placeholder")

    with patch("tools.notify_rep._get_twilio_client", return_value=fake_client):
        result = notify_rep(
            session=nr_session,
            rep_config=dealer_with_rep.config["sales_team"][0],
            lead=lead_for_notify,
            message_type="claim",
            payload={
                "customer_name": "Real Twilio Test",
                "vehicle": "2019 Honda Civic",
            },
            dealer_config=dealer_with_rep.config,
        )

    assert result.success is True
    assert result.backend == "twilio_whatsapp"
    assert result.message_sid == "SM_real_whatsapp_123"
    assert result.dry_run is False

    # The Twilio call: kwargs MUST include the right fields
    fake_client.messages.create.assert_called_once()
    kwargs = fake_client.messages.create.call_args.kwargs
    assert kwargs["to"] == "whatsapp:+160****4001"
    assert kwargs["from_"] == "whatsapp:+141****0099"
    assert kwargs["content_sid"] == "HXtemplateSID123"
    # content_variables is a JSON-encoded string per Twilio API
    assert json.loads(kwargs["content_variables"]) == {
        "customer_name": "Real Twilio Test",
        "vehicle": "2019 Honda Civic",
    }
    # No body when using a template
    assert "body" not in kwargs


def test_real_whatsapp_falls_back_to_body_when_no_template(
    nr_session, dealer_with_rep, lead_for_notify, monkeypatch
):
    """When no template_sid, the Twilio call uses free-form body."""
    from tools.notify_rep import notify_rep

    fake_client = MagicMock()
    fake_message = MagicMock()
    fake_message.sid = "SM_no_template_456"
    fake_client.messages.create.return_value = fake_message

    # Rep config without notify_template_sid
    rep_config = {
        "name": "Mike",
        "phone": "+160****4001",
        "active": True,
        "notify_backend": "twilio_whatsapp",
        # no notify_template_sid
    }

    monkeypatch.setattr(settings, "outbound_enabled", True)
    monkeypatch.setattr(settings, "twilio_account_sid", "AC_fake_sid")
    monkeypatch.setattr(settings, "twilio_auth_token", "test_auth_token_placeholder")

    with patch("tools.notify_rep._get_twilio_client", return_value=fake_client):
        result = notify_rep(
            session=nr_session,
            rep_config=rep_config,
            lead=lead_for_notify,
            message_type="claim",
            payload={"customer_name": "Fallback Test"},
            dealer_config=dealer_with_rep.config,
        )

    assert result.success is True
    assert result.message_sid == "SM_no_template_456"
    kwargs = fake_client.messages.create.call_args.kwargs
    assert "body" in kwargs
    assert "Fallback Test" in kwargs["body"]
    assert "content_sid" not in kwargs


def test_real_sms_transport_sends_via_twilio(
    nr_session, dealer_with_rep, lead_for_notify, monkeypatch
):
    """SMS backend also goes through the real Twilio client (no template)."""
    from tools.notify_rep import notify_rep

    fake_client = MagicMock()
    fake_message = MagicMock()
    fake_message.sid = "SM_sms_fallback_789"
    fake_client.messages.create.return_value = fake_message

    rep_config = {
        "name": "Dana",
        "phone": "+160****4002",
        "active": True,
        "notify_backend": "sms",
    }

    monkeypatch.setattr(settings, "outbound_enabled", True)
    monkeypatch.setattr(settings, "twilio_account_sid", "AC_fake_sid")
    monkeypatch.setattr(settings, "twilio_auth_token", "test_auth_token_placeholder")

    with patch("tools.notify_rep._get_twilio_client", return_value=fake_client):
        result = notify_rep(
            session=nr_session,
            rep_config=rep_config,
            lead=lead_for_notify,
            message_type="claim",
            payload={"customer_name": "SMS Test"},
            dealer_config=dealer_with_rep.config,
        )

    assert result.success is True
    assert result.backend == "sms"
    assert result.message_sid == "SM_sms_fallback_789"
    kwargs = fake_client.messages.create.call_args.kwargs
    # SMS: no "whatsapp:" prefix on to / from_
    assert kwargs["to"] == "+160****4002"
    assert kwargs["from_"] == "+177****0099"
    assert "content_sid" not in kwargs
    assert "body" in kwargs
    assert "SMS Test" in kwargs["body"]


def test_real_twilio_exception_is_handled(
    nr_session, dealer_with_rep, lead_for_notify, monkeypatch
):
    """If Twilio raises, notify_rep returns a not-success result (no crash)."""
    from tools.notify_rep import notify_rep

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = Exception("Twilio is down")

    monkeypatch.setattr(settings, "outbound_enabled", True)
    monkeypatch.setattr(settings, "twilio_account_sid", "AC_fake_sid")
    monkeypatch.setattr(settings, "twilio_auth_token", "test_auth_token_placeholder")

    with patch("tools.notify_rep._get_twilio_client", return_value=fake_client):
        result = notify_rep(
            session=nr_session,
            rep_config=dealer_with_rep.config["sales_team"][0],
            lead=lead_for_notify,
            message_type="claim",
            payload={"customer_name": "Exception Test"},
            dealer_config=dealer_with_rep.config,
        )

    assert result.success is False
    assert "Twilio is down" in (result.error or "")
    # No Message row written on hard failure (the existing _log_rep_message
    # is only called on success).
    msgs = nr_session.query(Message).all()
    assert len(msgs) == 0


# --- Live integration test (opt-in only) -------------------------------------

@pytest.mark.skipif(
    os.environ.get("RUN_TWILIO_INTEGRATION", "").lower() != "true",
    reason="Live Twilio integration test. Set RUN_TWILIO_INTEGRATION=true to enable. "
           "BURNING TWILIO CREDITS — never enable on CI.",
)
def test_live_twilio_whatsapp_send(nr_session, dealer_with_rep, lead_for_notify, monkeypatch):
    """Actually call Twilio. Requires real TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN
    in the environment, OUTBOUND_ENABLED=true, and a real Twilio WhatsApp sender
    + a verified destination phone.

    Required env vars to enable this test:
      RUN_TWILIO_INTEGRATION=true       # gate
      TWILIO_ACCOUNT_SID                # your real Twilio account SID
      TWILIO_AUTH_TOKEN                 # your real Twilio auth token
      INTEGRATION_TEST_WHATSAPP_SENDER  # your real Twilio WhatsApp-enabled sender
                                         #   (the dealer_with_rep fixture has a
                                         #   placeholder; for the live call Twilio
                                         #   needs the actual registered number)
      INTEGRATION_TEST_PHONE            # a real phone that can receive WhatsApp
      INTEGRATION_TEST_TEMPLATE_SID     # a real pre-approved HX... template SID

    Run:
      RUN_TWILIO_INTEGRATION=true \\
      TWILIO_ACCOUNT_SID=AC... \\
      TWILIO_AUTH_TOKEN=... \\
      INTEGRATION_TEST_WHATSAPP_SENDER=whatsapp:+1604... \\
      INTEGRATION_TEST_PHONE=+1604... \\
      INTEGRATION_TEST_TEMPLATE_SID=HX... \\
        pytest tests/test_notify_rep_real.py::test_live_twilio_whatsapp_send -v
    """
    from tools.notify_rep import notify_rep

    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        pytest.skip("TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN not set")

    # The dealer_with_rep fixture has a placeholder whatsapp_sender. For a
    # live call, Twilio needs the actual registered WhatsApp number. Override
    # the dealer's config with the real sender from env (skip if not set so
    # we don't accidentally call Twilio with a bogus From).
    real_sender = os.environ.get("INTEGRATION_TEST_WHATSAPP_SENDER")
    if not real_sender:
        pytest.skip("INTEGRATION_TEST_WHATSAPP_SENDER not set")

    real_dealer_config = dict(dealer_with_rep.config)
    real_dealer_config["channels"] = dict(real_dealer_config.get("channels", {}))
    real_dealer_config["channels"]["whatsapp_sender"] = real_sender

    monkeypatch.setattr(settings, "outbound_enabled", True)

    result = notify_rep(
        session=nr_session,
        rep_config={
            "name": "Integration Test",
            "phone": os.environ.get("INTEGRATION_TEST_PHONE", "+160****0001"),
            "active": True,
            "notify_backend": "twilio_whatsapp",
            "notify_template_sid": os.environ.get(
                "INTEGRATION_TEST_TEMPLATE_SID", "HX_integration_test"
            ),
        },
        lead=lead_for_notify,
        message_type="claim",
        payload={"customer_name": "Live Integration Test"},
        dealer_config=real_dealer_config,
    )

    assert result.success is True
    assert result.message_sid is not None
    assert result.message_sid.startswith("SM") or result.message_sid.startswith("WA")
    # Real SID, not a DRYRUN
    assert not result.dry_run
    # The Message row was persisted
    msgs = nr_session.query(Message).filter(Message.lead_id == lead_for_notify.id).all()
    assert len(msgs) == 1
    assert msgs[0].channel == Channel.WHATSAPP
    assert msgs[0].recipient_role == "rep"
