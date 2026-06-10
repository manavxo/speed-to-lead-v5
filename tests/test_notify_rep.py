"""P1-1: notify_rep abstraction.

A single chokepoint for all dealer-side notifications (rep claim pings,
escalations, appointment confirmations, missed-call handoffs).

The backend is configurable per rep:
- twilio_whatsapp (default): pre-approved Twilio WhatsApp template
- sms (fallback):         legacy SMS via the send_sms chokepoint
- email:                  Phase 2 (not yet implemented)
- dashboard:              Phase 2 (not yet implemented)

Every notification persists a Message row with recipient_role="rep" so the
lead detail page can show it, and respects OUTBOUND_ENABLED as a dry-run gate.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.models import Channel, Dealer, Direction, Lead, LeadState, Message


# --- Fixtures ----------------------------------------------------------------

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
        slug="notify-test",
        name="Notify Test Dealer",
        sms_number="+177****0099",
        whatsapp_sender="+141****0099",
        config={
            "dealer": {"name": "Notify Test Dealer", "timezone": "America/Vancouver"},
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
                    "notify_template_sid": "HXxxxxxx",
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
        name="Test Customer",
        phone="+160****4999",
        state=LeadState.ASSIGNED,
    )
    nr_session.add(lead)
    nr_session.commit()
    nr_session.refresh(lead)
    return lead


# --- Tests -------------------------------------------------------------------

def test_notify_rep_dispatches_to_twilio_whatsapp_by_default(
    nr_session, dealer_with_rep, lead_for_notify, monkeypatch
):
    """Default backend is twilio_whatsapp — calls the WhatsApp transport."""
    from app.config import settings
    from tools.notify_rep import notify_rep

    sent: list[dict] = []

    def fake_send_whatsapp(*, to_phone, from_phone, body, template_sid=None, variables=None):
        sent.append({
            "to_phone": to_phone,
            "from_phone": from_phone,
            "body": body,
            "template_sid": template_sid,
            "variables": variables,
        })
        return "FAKE_WA_SID"

    monkeypatch.setattr("tools.notify_rep.send_via_twilio_whatsapp", fake_send_whatsapp)
    # Opt in to real-send path. Pydantic Settings caches the value at import
    # time, so we patch the attribute directly (env var alone won't work).
    monkeypatch.setattr(settings, "outbound_enabled", True)

    rep_config = dealer_with_rep.config["sales_team"][0]
    result = notify_rep(
        session=nr_session,
        rep_config=rep_config,
        lead=lead_for_notify,
        message_type="claim",
        payload={"customer_name": "Test Customer", "vehicle": "2019 Honda Civic"},
        dealer_config=dealer_with_rep.config,
    )

    assert result.success is True
    assert result.backend == "twilio_whatsapp"
    assert result.message_sid == "FAKE_WA_SID"
    assert result.dry_run is False
    assert len(sent) == 1
    assert sent[0]["to_phone"] == "+160****4001"
    assert "Test Customer" in sent[0]["body"]


def test_notify_rep_falls_back_to_sms_when_configured(
    nr_session, dealer_with_rep, lead_for_notify, monkeypatch
):
    """If rep_config has notify_backend='sms', use the SMS transport."""
    from app.config import settings
    from tools.notify_rep import notify_rep

    sent: list[dict] = []

    def fake_send_sms(*, to_phone, from_phone, body):
        sent.append({"to_phone": to_phone, "from_phone": from_phone, "body": body})
        return "FAKE_SMS_SID"

    monkeypatch.setattr("tools.notify_rep.send_via_sms", fake_send_sms)
    monkeypatch.setattr(settings, "outbound_enabled", True)

    rep_config = {
        "name": "Dana",
        "phone": "+160****4002",
        "active": True,
        "notify_backend": "sms",
    }
    result = notify_rep(
        session=nr_session,
        rep_config=rep_config,
        lead=lead_for_notify,
        message_type="claim",
        payload={"customer_name": "Test Customer"},
        dealer_config=dealer_with_rep.config,
    )

    assert result.success is True
    assert result.backend == "sms"
    assert result.message_sid == "FAKE_SMS_SID"
    assert len(sent) == 1
    assert sent[0]["to_phone"] == "+160****4002"


def test_notify_rep_persists_message_row_with_recipient_role(
    nr_session, dealer_with_rep, lead_for_notify, monkeypatch
):
    """Every send persists exactly one Message row with recipient_role='rep'."""
    from tools.notify_rep import notify_rep

    monkeypatch.setattr(
        "tools.notify_rep.send_via_twilio_whatsapp",
        lambda **kw: "FAKE_WA_SID",
    )

    rep_config = dealer_with_rep.config["sales_team"][0]
    initial_count = len(nr_session.query(Message).all())

    result = notify_rep(
        session=nr_session,
        rep_config=rep_config,
        lead=lead_for_notify,
        message_type="claim",
        payload={"customer_name": "Test Customer"},
        dealer_config=dealer_with_rep.config,
    )
    assert result.success is True

    final_count = len(nr_session.query(Message).all())
    assert final_count == initial_count + 1
    new_msg = nr_session.query(Message).order_by(Message.id.desc()).first()
    assert new_msg.direction == Direction.OUTBOUND
    assert new_msg.lead_id == lead_for_notify.id
    assert new_msg.recipient_role == "rep"
    # WhatsApp channel
    assert new_msg.channel == Channel.WHATSAPP


def test_notify_rep_respects_outbound_disabled(
    nr_session, dealer_with_rep, lead_for_notify, monkeypatch
):
    """When OUTBOUND_ENABLED=false, no real send happens — message is still logged."""
    from tools.notify_rep import notify_rep, send_via_twilio_whatsapp

    send_calls: list[dict] = []

    def fake_send(**kwargs):
        send_calls.append(kwargs)
        return "REAL_SID_SHOULD_NOT_BE_USED"

    monkeypatch.setattr("tools.notify_rep.send_via_twilio_whatsapp", fake_send)
    # env is set OUTBOUND_ENABLED=false in conftest.py; assert here for clarity
    monkeypatch.setenv("OUTBOUND_ENABLED", "false")

    rep_config = dealer_with_rep.config["sales_team"][0]
    result = notify_rep(
        session=nr_session,
        rep_config=rep_config,
        lead=lead_for_notify,
        message_type="claim",
        payload={"customer_name": "Test Customer"},
        dealer_config=dealer_with_rep.config,
    )

    # Dry-run: transport NOT called, but message still recorded
    assert send_calls == []
    assert result.dry_run is True
    assert result.success is True
    assert result.message_sid is not None
    assert result.message_sid.startswith("DRYRUN_")


def test_notify_rep_returns_error_for_email_backend(
    nr_session, dealer_with_rep, lead_for_notify
):
    """Email backend is Phase 2 — return a not-implemented result, not a crash."""
    from tools.notify_rep import notify_rep

    rep_config = {
        "name": "Dana",
        "phone": "+160****4002",
        "active": True,
        "notify_backend": "email",
    }
    result = notify_rep(
        session=nr_session,
        rep_config=rep_config,
        lead=lead_for_notify,
        message_type="claim",
        payload={"customer_name": "Test Customer"},
        dealer_config=dealer_with_rep.config,
    )

    assert result.success is False
    assert result.backend == "email"
    assert "not implemented" in (result.error or "").lower()


def test_notify_rep_handles_missing_phone(
    nr_session, dealer_with_rep, lead_for_notify
):
    """A rep with no phone number fails gracefully (no crash, no send)."""
    from tools.notify_rep import notify_rep

    rep_config = {"name": "NoPhone", "active": True, "notify_backend": "twilio_whatsapp"}
    # No 'phone' key

    result = notify_rep(
        session=nr_session,
        rep_config=rep_config,
        lead=lead_for_notify,
        message_type="claim",
        payload={"customer_name": "Test Customer"},
        dealer_config=dealer_with_rep.config,
    )

    assert result.success is False
    assert "phone" in (result.error or "").lower()
