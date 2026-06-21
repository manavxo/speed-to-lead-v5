"""Phase 9: Email transport unit tests.

Tests the SendGrid email transport with mocked API calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_sg_settings():
    """Patch app.config.settings with email-relevant values."""
    with patch("app.transports.email.settings") as mock:
        mock.sendgrid_api_key = "SG.test_key"
        mock.email_from_address = "sales@test.com"
        mock.email_from_name = "Test Dealer"
        mock.outbound_enabled = True
        yield mock


def test_email_name():
    """Module imports without error."""
    from app.transports.email import send_email, EmailResult
    assert send_email is not None
    assert EmailResult is not None


def test_email_dry_run():
    """When outbound is disabled, returns success with DRYRUN_ message_id."""
    with patch("app.transports.email.settings") as mock:
        mock.sendgrid_api_key = "SG.test_key"
        mock.outbound_enabled = False

        from app.transports.email import send_email
        result = send_email("test@example.com", "Subject", "Body")

    assert result.success is True
    assert result.message_id is not None
    assert result.message_id.startswith("DRYRUN_")


def test_email_no_api_key():
    """Without SENDGRID_API_KEY, returns error."""
    with patch("app.transports.email.settings") as mock:
        mock.sendgrid_api_key = ""
        mock.outbound_enabled = True

        from app.transports.email import send_email
        result = send_email("test@example.com", "Subject", "Body")

    assert result.success is False
    assert "SENDGRID_API_KEY" in (result.error or "")


@patch("app.transports.email.settings", sendgrid_api_key="SG.test", email_from_address="sales@test.com", email_from_name="Test", outbound_enabled=True)
@patch("sendgrid.SendGridAPIClient")
def test_email_send_success(mock_sg_client, mock_sg_settings):
    """Successful SendGrid send returns success=True with message_id."""
    mock_response = MagicMock()
    mock_response.status_code = 202
    mock_response.headers = {"X-Message-Id": "sg_msg_123"}
    mock_sg_client.return_value.send.return_value = mock_response

    from app.transports.email import send_email
    result = send_email("customer@example.com", "Your inquiry", "Thanks for reaching out!")

    assert result.success is True
    assert result.message_id == "sg_msg_123"


@patch("app.transports.email.settings", sendgrid_api_key="SG.test", email_from_address="sales@test.com", email_from_name="Test", outbound_enabled=True)
@patch("sendgrid.SendGridAPIClient")
def test_email_send_api_error(mock_sg_client, mock_sg_settings):
    """SendGrid returns non-2xx — result should have success=False."""
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_sg_client.return_value.send.return_value = mock_response

    from app.transports.email import send_email
    result = send_email("customer@example.com", "Subject", "Body")

    assert result.success is False
