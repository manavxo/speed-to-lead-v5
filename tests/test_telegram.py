"""Phase 4.2: Telegram transport unit tests.

Tests the TelegramTransport class with mocked settings and HTTP so
no real Telegram API requests are made.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_settings():
    """Patch app.config.settings with Telegram-relevant values."""
    with patch("app.transports.telegram.settings") as mock:
        mock.telegram_bot_token = "test:token"
        mock.outbound_enabled = True
        yield mock


def test_telegram_name():
    """Transport name should be 'telegram'."""
    from app.transports.telegram import TelegramTransport
    transport = TelegramTransport()
    assert transport.name == "telegram"


def test_telegram_dry_run():
    """When outbound is disabled, returns dry_run=True."""
    with patch("app.transports.telegram.settings") as mock:
        mock.telegram_bot_token = "test:token"
        mock.outbound_enabled = False

        from app.transports.telegram import TelegramTransport
        transport = TelegramTransport()
        result = transport.send(to="12345", body="Test message")

    assert result.success is True
    assert result.backend == "telegram"
    assert result.dry_run is True
    assert result.message_id is not None
    assert result.message_id.startswith("DRYRUN_")


def test_telegram_send_success(mock_settings):
    """Successful Telegram API call returns success=True with message_id."""
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": True, "result": {"message_id": 42}},
        )

        from app.transports.telegram import TelegramTransport
        transport = TelegramTransport()
        result = transport.send(to="12345", body="Hello from test!")

    assert result.success is True
    assert result.backend == "telegram"
    assert result.message_id == "42"

    mock_post.assert_called_once_with(
        "https://api.telegram.org/bottest:token/sendMessage",
        json={
            "chat_id": "12345",
            "text": "Hello from test!",
            "parse_mode": "HTML",
        },
        timeout=10.0,
    )


def test_telegram_send_api_error(mock_settings):
    """Telegram API returns error — result should have success=False."""
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=400,
            json=lambda: {"ok": False, "description": "Bad Request: chat not found"},
        )

        from app.transports.telegram import TelegramTransport
        transport = TelegramTransport()
        result = transport.send(to="99999", body="Test")

    assert result.success is False
    assert result.backend == "telegram"
    assert result.error is not None
    assert "chat not found" in result.error.lower()


def test_telegram_no_token():
    """Without TELEGRAM_BOT_TOKEN, should return error."""
    with patch("app.transports.telegram.settings") as mock:
        mock.telegram_bot_token = ""
        mock.outbound_enabled = True

        from app.transports.telegram import TelegramTransport
        transport = TelegramTransport()
        result = transport.send(to="12345", body="Test")

    assert result.success is False
    assert "TELEGRAM_BOT_TOKEN" in (result.error or "")


def test_telegram_timeout(mock_settings):
    """httpx timeout should return success=False with error='timeout'."""
    with patch("httpx.post") as mock_post:
        from httpx import TimeoutException
        mock_post.side_effect = TimeoutException("Request timed out")

        from app.transports.telegram import TelegramTransport
        transport = TelegramTransport()
        result = transport.send(to="12345", body="Test")

    assert result.success is False
    assert result.backend == "telegram"
    assert result.error == "timeout"
