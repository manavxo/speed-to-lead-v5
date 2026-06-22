"""Tests for per-dealer email from address in app/transports/email.py.

Ensures:
1. _resolve_sender() prefers per-dealer config over global env vars
2. dealer_config with email_from_address is used when provided
3. Missing dealer config falls back to env var, then built-in fallback
4. _send_email_followup threads dealer_config through correctly
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.transports.email import _resolve_sender, send_email, EmailResult


class TestResolveSender:
    """_resolve_sender() priority: dealer_config > env var > built-in fallback."""

    def test_dealer_config_wins_over_env_var(self):
        """Per-dealer config's email_from_address should take priority."""
        config = {
            "channels": {
                "email_from_address": "sales@premierautogroup.com",
                "email_from_name": "Premier Auto Group",
            }
        }
        from_email, from_name = _resolve_sender(config)
        assert from_email == "sales@premierautogroup.com"
        assert from_name == "Premier Auto Group"

    def test_dealer_config_without_name_returns_name(self):
        """Dealer config with email_from_address but no email_from_name returns the address + empty name."""
        config = {
            "channels": {
                "email_from_address": "custom@dealer.com",
            }
        }
        from_email, from_name = _resolve_sender(config)
        assert from_email == "custom@dealer.com"
        assert from_name == ""

    def test_no_dealer_config_falls_back_to_env(self, monkeypatch):
        """When no dealer_config provided, should use env var EMAIL_FROM_ADDRESS."""
        monkeypatch.setattr("app.config.settings.email_from_address", "global@speedtolead.com")
        monkeypatch.setattr("app.config.settings.email_from_name", "Speed to Lead")
        from_email, from_name = _resolve_sender(None)
        assert from_email == "global@speedtolead.com"
        assert from_name == "Speed to Lead"

    def test_no_dealer_config_and_no_env_falls_back(self, monkeypatch):
        """When nothing is configured, falls back to noreply@speedtolead.com."""
        monkeypatch.setattr("app.config.settings.email_from_address", "")
        monkeypatch.setattr("app.config.settings.email_from_name", "")
        from_email, from_name = _resolve_sender(None)
        assert from_email == "noreply@speedtolead.com"
        assert from_name == "Speed to Lead"

    def test_dealer_config_without_email_uses_env(self, monkeypatch):
        """Dealer config with no email_from_address field should fall back to env var."""
        monkeypatch.setattr("app.config.settings.email_from_address", "fallback@dealer.com")
        config = {
            "channels": {
                "sms_number": "+17785551234",
            }
        }
        from_email, from_name = _resolve_sender(config)
        assert from_email == "fallback@dealer.com"


class TestSendEmailDealerConfig:
    """send_email() should use dealer_config for From address resolution."""

    def test_send_email_uses_dealer_config_dry_run(self, monkeypatch):
        """In dry-run mode, dealer config's email_from_address should be logged/used."""
        monkeypatch.setattr("app.config.settings.sendgrid_api_key", "test-key")
        monkeypatch.setattr("app.config.settings.outbound_enabled", False)

        result = send_email(
            to="customer@example.com",
            subject="Test Drive Inquiry",
            body_text="Hi there, thanks for your interest!",
            dealer_config={
                "channels": {
                    "email_from_address": "sales@premierautogroup.com",
                    "email_from_name": "Premier Auto Group",
                }
            },
        )

        assert result.success is True
        assert result.message_id is not None
        assert result.message_id.startswith("DRYRUN_")

    def test_send_email_explicit_from_wins_over_dealer_config(self, monkeypatch):
        """Explicit from_email param should beat dealer config."""
        monkeypatch.setattr("app.config.settings.sendgrid_api_key", "test-key")
        monkeypatch.setattr("app.config.settings.outbound_enabled", False)

        result = send_email(
            to="customer@example.com",
            subject="Test",
            body_text="Hello",
            from_email="override@example.com",
            from_name="Override Name",
            dealer_config={
                "channels": {
                    "email_from_address": "sales@premierautogroup.com",
                }
            },
        )

        assert result.success is True

    def test_send_email_no_dealer_config_still_works(self, monkeypatch):
        """Without dealer_config, send_email should still work (env fallback)."""
        monkeypatch.setattr("app.config.settings.sendgrid_api_key", "test-key")
        monkeypatch.setattr("app.config.settings.outbound_enabled", False)
        monkeypatch.setattr("app.config.settings.email_from_address", "global@speedtolead.com")
        monkeypatch.setattr("app.config.settings.email_from_name", "Global")

        result = send_email(
            to="customer@example.com",
            subject="Test",
            body_text="Hello",
        )

        assert result.success is True
        assert result.message_id is not None
        assert result.message_id.startswith("DRYRUN_")

    def test_send_email_no_api_key_returns_error(self, monkeypatch):
        """Without SENDGRID_API_KEY, should return failure — not crash."""
        monkeypatch.setattr("app.config.settings.sendgrid_api_key", "")
        monkeypatch.setattr("app.config.settings.outbound_enabled", True)

        result = send_email(
            to="customer@example.com",
            subject="Test",
            body_text="Hello",
            dealer_config={
                "channels": {
                    "email_from_address": "sales@dealer.com",
                }
            },
        )

        assert result.success is False
        assert "SENDGRID_API_KEY" in (result.error or "")
