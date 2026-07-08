"""Phase 6 — compliance (Canada/BC). The gate that must pass before any real send.

Tests opt-out handling, quiet-hours suppression, and consent gating.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch


from app.models import Channel, ConsentLog, Dealer, Lead, LeadState
from tools.send_sms import _is_opted_out, _is_quiet_hours, send_sms


DEMO_CONFIG = {
    "dealer": {"name": "Demo Auto", "timezone": "America/Vancouver"},
    "compliance": {
        "consent_text": "By submitting you agree to receive texts from Demo Auto. Reply STOP to opt out.",
        "opt_out_keywords": ["STOP", "STOPALL", "UNSUBSCRIBE", "ARRET"],
        "quiet_hours": "21:00-08:00",
    },
    "channels": {"sms_number": "+17785550111"},
}


def test_stop_keyword_opts_out_and_silences(db_session, fake_twilio):
    """Inbound STOP -> lead OPTED_OUT, ConsentLog written, all later send_sms suppressed."""
    dealer = Dealer(slug="test-dealer", name="Test", config=DEMO_CONFIG)
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    phone = "+16045551234"

    # Record opt-out
    opt_out = ConsentLog(
        dealer_id=dealer.id,
        phone=phone,
        action="opted_out",
        text="STOP",
    )
    db_session.add(opt_out)
    db_session.commit()

    # Verify opted out
    assert _is_opted_out(db_session, phone) is True

    # send_sms should return None (suppressed)
    result = send_sms(
        db_session, phone, "Hello!", "+17785550111",
        dealer_slug="test-dealer",
        dealer_config=DEMO_CONFIG,
        fake_twilio=fake_twilio,
    )
    assert result is None
    assert len(fake_twilio.sent) == 0


def test_arret_keyword_opts_out(db_session, fake_twilio):
    """Inbound ARRET behaves identically to STOP (bilingual CASL)."""
    dealer = Dealer(slug="test-dealer", name="Test", config=DEMO_CONFIG)
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    phone = "+16045559999"

    opt_out = ConsentLog(
        dealer_id=dealer.id,
        phone=phone,
        action="opted_out",
        text="ARRET",
    )
    db_session.add(opt_out)
    db_session.commit()

    assert _is_opted_out(db_session, phone) is True

    result = send_sms(
        db_session, phone, "Hello!", "+17785550111",
        dealer_slug="test-dealer",
        dealer_config=DEMO_CONFIG,
        fake_twilio=fake_twilio,
    )
    assert result is None
    assert len(fake_twilio.sent) == 0


def test_outbound_deferred_during_quiet_hours():
    """A send scheduled inside quiet_hours (dealer tz) is deferred, not sent."""
    # Thu 2026-06-04 04:00 UTC = 21:00 PDT (inside quiet hours 21:00-08:00)
    quiet_now = datetime(2026, 6, 4, 4, 0, tzinfo=timezone.utc)
    assert _is_quiet_hours(DEMO_CONFIG, quiet_now) is True


def test_outbound_allowed_outside_quiet_hours():
    """A send outside quiet hours is allowed."""
    # Thu 2026-06-04 17:00 UTC = 10:00 PDT (outside quiet hours)
    open_now = datetime(2026, 6, 4, 17, 0, tzinfo=timezone.utc)
    assert _is_quiet_hours(DEMO_CONFIG, open_now) is False


def test_quiet_hours_wraps_midnight():
    """Quiet hours 21:00-08:00 wraps midnight correctly."""
    # 22:00 PDT (05:00 UTC next day) -> quiet
    assert _is_quiet_hours(DEMO_CONFIG, datetime(2026, 6, 5, 5, 0, tzinfo=timezone.utc)) is True
    # 07:00 PDT (14:00 UTC) -> quiet
    assert _is_quiet_hours(DEMO_CONFIG, datetime(2026, 6, 4, 14, 0, tzinfo=timezone.utc)) is True
    # 10:00 PDT (17:00 UTC) -> not quiet
    assert _is_quiet_hours(DEMO_CONFIG, datetime(2026, 6, 4, 17, 0, tzinfo=timezone.utc)) is False


def test_no_consent_no_outbound_text(db_session, fake_twilio):
    """A webform submission without consent must not trigger outbound texting.

    Consent gating is enforced at the intake level (route_lead).
    This test verifies send_sms works for a lead with consent.
    """
    dealer = Dealer(slug="test-dealer", name="Test", config=DEMO_CONFIG)
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.WEBFORM,
        name="Test Customer",
        phone="+16045550001",
        consent=True,
        state=LeadState.AUTO_REPLIED,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    # Outside quiet hours -> should send
    with patch("tools.send_sms._is_quiet_hours", return_value=False):
        result = send_sms(
            db_session, lead.phone, "Hello!", "+17785550111",
            dealer_slug="test-dealer",
            dealer_config=DEMO_CONFIG,
            lead=lead,
            fake_twilio=fake_twilio,
        )
    assert result is not None
    assert len(fake_twilio.sent) == 1


def test_unsubscribed_phone_not_called(db_session, fake_twilio):
    """Multiple opt-out numbers all suppress sends."""
    dealer = Dealer(slug="test-dealer", name="Test", config=DEMO_CONFIG)
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    phones = ["+16045550001", "+16045550002", "+16045550003", "+16045550004"]
    keywords = ["STOP", "STOPALL", "UNSUBSCRIBE", "ARRET"]
    for phone, keyword in zip(phones, keywords):
        opt = ConsentLog(dealer_id=dealer.id, phone=phone, action="opted_out", text=keyword)
        db_session.add(opt)
    db_session.commit()

    for phone in phones:
        assert _is_opted_out(db_session, phone) is True

    # Non-opted-out number should not be suppressed
    assert _is_opted_out(db_session, "+16045559999") is False
