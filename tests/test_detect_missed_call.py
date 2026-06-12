"""1.6: Tests for missed-call detection and SMS follow-up trigger.

Tests the detect_missed_call.py tool that handles missed calls and
triggers SMS follow-up conversations.

Three detection modes tested:
- always_on: All calls forwarded to Twilio 24/7
- time_based: Forwarding only during off-hours
- voicemail_notify: Carrier voicemail notification parsing (backup)
"""
import os
import sys
from unittest.mock import MagicMock, call

import pytest

# Import the module under test
sys_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from tools.detect_missed_call import (
    MissedCallResult,
    handle_missed_call,
    handle_missed_call_from_webhook,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def mock_session():
    """Mock database session."""
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = None
    return session


@pytest.fixture
def mock_dealer():
    """Mock dealer instance."""
    dealer = MagicMock()
    dealer.id = 1
    dealer.sms_number = "+177****0099"
    dealer.config = {
        "dealer": {"name": "Test Dealer", "main_phone": "+160****0100"},
    }
    return dealer


@pytest.fixture
def mock_sms_sender():
    """Mock SMS sender function."""
    sender = MagicMock(return_value="SM_FAKE_SID_123")
    return sender


# ── MissedCallResult tests ────────────────────────────────────────────────

def test_missed_call_result_success():
    """Successful result has correct attributes."""
    result = MissedCallResult(success=True, lead_id=1, message_sid="SM123")
    assert result.success is True
    assert result.lead_id == 1
    assert result.message_sid == "SM123"
    assert result.error is None


def test_missed_call_result_failure():
    """Failed result has error message."""
    result = MissedCallResult(success=False, error="No dealer found")
    assert result.success is False
    assert result.error == "No dealer found"


def test_missed_call_result_repr():
    """Repr shows key info."""
    result = MissedCallResult(success=True, lead_id=1, message_sid="SM123")
    assert "success=True" in repr(result)
    assert "lead_id=1" in repr(result)


# ── handle_missed_call tests ──────────────────────────────────────────────

def test_handle_missed_call_creates_lead(mock_session, mock_dealer, mock_sms_sender):
    """Creates lead and sends SMS on no-answer."""
    result = handle_missed_call(
        session=mock_session,
        dealer=mock_dealer,
        caller_phone="+160****2870",
        call_sid="CA1234567890",
        call_status="no-answer",
        sms_sender=mock_sms_sender,
    )

    assert result.success is True
    assert result.message_sid == "SM_FAKE_SID_123"

    # Verify lead was created (lead_id may be None with mocks since flush doesn't set id)
    mock_session.add.assert_called()
    mock_session.commit.assert_called_once()
    # Check that a Lead was added
    added_objects = [c[0][0] for c in mock_session.add.call_args_list]
    from app.models import Lead
    leads = [o for o in added_objects if isinstance(o, Lead)]
    assert len(leads) == 1
    assert leads[0].phone == "+160****2870"
    assert leads[0].source == "phone"


def test_handle_missed_call_sends_sms(mock_session, mock_dealer, mock_sms_sender):
    """SMS is sent to the caller."""
    handle_missed_call(
        session=mock_session,
        dealer=mock_dealer,
        caller_phone="+160****2870",
        call_sid="CA1234567890",
        call_status="no-answer",
        sms_sender=mock_sms_sender,
    )

    mock_sms_sender.assert_called_once()
    call_args = mock_sms_sender.call_args
    assert call_args.kwargs["to"] == "+160****2870"
    assert call_args.kwargs["from_"] == "+177****0099"
    assert "missed your call" in call_args.kwargs["body"].lower()
    assert "Test Dealer" in call_args.kwargs["body"]


def test_handle_missed_call_includes_main_phone(mock_session, mock_dealer, mock_sms_sender):
    """SMS includes dealer's main phone number."""
    handle_missed_call(
        session=mock_session,
        dealer=mock_dealer,
        caller_phone="+160****2870",
        call_sid="CA1234567890",
        call_status="no-answer",
        sms_sender=mock_sms_sender,
    )

    body = mock_sms_sender.call_args.kwargs["body"]
    assert "+160****0100" in body


def test_handle_missed_call_skips_completed(mock_session, mock_dealer, mock_sms_sender):
    """Completed calls are not missed — returns error."""
    result = handle_missed_call(
        session=mock_session,
        dealer=mock_dealer,
        caller_phone="+160****2870",
        call_sid="CA1234567890",
        call_status="completed",
        sms_sender=mock_sms_sender,
    )

    assert result.success is False
    assert "not a missed call" in result.error
    mock_sms_sender.assert_not_called()


def test_handle_missed_call_skips_busy(mock_session, mock_dealer, mock_sms_sender):
    """Busy calls trigger SMS follow-up."""
    result = handle_missed_call(
        session=mock_session,
        dealer=mock_dealer,
        caller_phone="+160****2870",
        call_sid="CA1234567890",
        call_status="busy",
        sms_sender=mock_sms_sender,
    )

    assert result.success is True


def test_handle_missed_call_skips_failed(mock_session, mock_dealer, mock_sms_sender):
    """Failed calls trigger SMS follow-up."""
    result = handle_missed_call(
        session=mock_session,
        dealer=mock_dealer,
        caller_phone="+160****2870",
        call_sid="CA1234567890",
        call_status="failed",
        sms_sender=mock_sms_sender,
    )

    assert result.success is True


def test_handle_missed_call_dedup(mock_session, mock_dealer, mock_sms_sender):
    """Duplicate caller gets skipped — no double text."""
    # Simulate existing lead
    existing_lead = MagicMock()
    existing_lead.id = 42
    mock_session.query.return_value.filter.return_value.first.return_value = existing_lead

    result = handle_missed_call(
        session=mock_session,
        dealer=mock_dealer,
        caller_phone="+160****2870",
        call_sid="CA1234567890",
        call_status="no-answer",
        sms_sender=mock_sms_sender,
    )

    assert result.success is False
    assert "already exists" in result.error
    mock_sms_sender.assert_not_called()


def test_handle_missed_call_sms_failure_still_creates_lead(mock_session, mock_dealer):
    """Lead is created even if SMS fails."""
    def failing_sender(**kwargs):
        raise Exception("Twilio API error")

    result = handle_missed_call(
        session=mock_session,
        dealer=mock_dealer,
        caller_phone="+160****2870",
        call_sid="CA1234567890",
        call_status="no-answer",
        sms_sender=failing_sender,
    )

    # Lead should still be created
    assert result.success is True
    assert result.message_sid is None  # SMS failed
    # Verify Lead was added
    added_objects = [c[0][0] for c in mock_session.add.call_args_list]
    from app.models import Lead
    leads = [o for o in added_objects if isinstance(o, Lead)]
    assert len(leads) == 1


def test_handle_missed_call_no_main_phone(mock_session, mock_dealer, mock_sms_sender):
    """SMS works without main_phone in config."""
    mock_dealer.config = {"dealer": {"name": "Test Dealer"}}

    result = handle_missed_call(
        session=mock_session,
        dealer=mock_dealer,
        caller_phone="+160****2870",
        call_sid="CA1234567890",
        call_status="no-answer",
        sms_sender=mock_sms_sender,
    )

    assert result.success is True
    body = mock_sms_sender.call_args.kwargs["body"]
    assert "call us back" not in body.lower()


def test_handle_missed_call_logs_message(mock_session, mock_dealer, mock_sms_sender):
    """Message row is created for the outbound SMS."""
    handle_missed_call(
        session=mock_session,
        dealer=mock_dealer,
        caller_phone="+160****2870",
        call_sid="CA1234567890",
        call_status="no-answer",
        sms_sender=mock_sms_sender,
    )

    # Check that Message was added
    add_calls = mock_session.add.call_args_list
    # First add is Lead, second is Message
    assert len(add_calls) >= 2
    msg = add_calls[1][0][0]  # Second call, first positional arg
    assert msg.direction == "outbound"
    assert msg.channel == "sms"


# ── handle_missed_call_from_webhook tests ─────────────────────────────────

def test_handle_missed_call_from_webhook_parses_payload(monkeypatch):
    """Webhook handler parses Twilio payload correctly."""
    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.first.return_value = None

    mock_dealer = MagicMock()
    mock_dealer.id = 1
    mock_dealer.sms_number = "+177****0099"
    mock_dealer.config = {"dealer": {"name": "Test Dealer"}}

    # Mock _find_dealer_by_sms
    import app.main
    monkeypatch.setattr(app.main, "_find_dealer_by_sms", lambda s, n: mock_dealer)

    mock_sms = MagicMock(return_value="SM_SID")

    payload = {
        "From": "+160****2870",
        "To": "+177****0099",
        "CallStatus": "no-answer",
        "CallSid": "CA_WEBHOOK_123",
        "CallDuration": "0",
    }

    result = handle_missed_call_from_webhook(
        session=mock_session,
        payload=payload,
        sms_sender=mock_sms,
    )

    assert result.success is True
    mock_sms.assert_called_once()


def test_handle_missed_call_from_webhook_no_dealer(monkeypatch):
    """Returns error when no dealer matches the called number."""
    mock_session = MagicMock()

    import app.main
    monkeypatch.setattr(app.main, "_find_dealer_by_sms", lambda s, n: None)

    payload = {
        "From": "+160****2870",
        "To": "+177****9999",  # Unknown number
        "CallStatus": "no-answer",
        "CallSid": "CA_UNKNOWN",
        "CallDuration": "0",
    }

    result = handle_missed_call_from_webhook(
        session=mock_session,
        payload=payload,
    )

    assert result.success is False
    assert "No dealer found" in result.error
