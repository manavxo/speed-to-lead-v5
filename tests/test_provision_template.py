"""1.5: Tests for WhatsApp template provisioning tool.

Tests the provision_whatsapp_template.py tool that auto-creates WhatsApp
content templates via Twilio Content API and updates dealer YAML files.
"""
import os
import re
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# Import the module under test
sys_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from tools.provision_whatsapp_template import (
    create_content_template,
    find_existing_template,
    submit_for_approval,
    check_approval_status,
    update_yaml_template_sid,
    get_twilio_creds,
    load_env,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def sample_yaml(tmp_path):
    """Create a sample dealer YAML file."""
    content = textwrap.dedent("""\
        dealer:
          slug: test-dealer
          name: "Test Dealer"
          timezone: America/Vancouver

        channels:
          sms_number: "+177****0099"
          whatsapp_sender: "+141****8886"

        sales_team:
          - { name: "Mike", phone: "+160****4001", active: true, notify_backend: twilio_whatsapp, notify_template_sid: "HX_replace_with_real_sid" }
          - { name: "Dana", phone: "+160****4002", active: true, notify_backend: sms, notify_template_sid: "HX_replace_with_real_sid" }
    """)
    yaml_path = tmp_path / "test-dealer.yaml"
    yaml_path.write_text(content, encoding="utf-8")
    return yaml_path


@pytest.fixture
def mock_twilio_creds(monkeypatch):
    """Set fake Twilio credentials."""
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_FAKE_SID")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "FAKE_TOKEN")


@pytest.fixture
def mock_requests():
    """Mock requests module for Twilio API calls."""
    with patch("tools.provision_whatsapp_template.requests") as mock:
        yield mock


# ── create_content_template tests ─────────────────────────────────────────

def test_create_content_template_success(mock_requests):
    """Template creation returns SID on 201."""
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "sid": "HX_FAKE_TEMPLATE_123",
        "friendly_name": "Test Template",
        "status": "unapproved",
    }
    mock_requests.post.return_value = mock_resp
    
    sid, err = create_content_template(
        "AC_FAKE", "FAKE_TOKEN",
        "Test Template",
        "New lead: {{1}}. Reply 1 to claim."
    )
    
    assert sid == "HX_FAKE_TEMPLATE_123"
    assert err is None


def test_create_content_template_409_finds_existing(mock_requests):
    """On 409 (conflict), searches for existing template by name."""
    # First call returns 409
    mock_resp_409 = MagicMock()
    mock_resp_409.status_code = 409
    mock_resp_409.text = "Conflict"
    
    # Second call (GET list) returns existing template
    mock_resp_list = MagicMock()
    mock_resp_list.status_code = 200
    mock_resp_list.json.return_value = {
        "contents": [
            {"sid": "HX_EXISTING_456", "friendly_name": "Speed to Lead"},
            {"sid": "HX_OTHER_789", "friendly_name": "Other Template"},
        ]
    }
    
    mock_requests.post.return_value = mock_resp_409
    mock_requests.get.return_value = mock_resp_list
    
    sid, err = create_content_template(
        "AC_FAKE", "FAKE_TOKEN",
        "Speed to Lead",
        "New lead: {{1}}"
    )
    
    assert sid == "HX_EXISTING_456"
    assert err is None


def test_create_content_template_http_error(mock_requests):
    """Returns error on non-201/409 status."""
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = '{"message": "Invalid template"}'
    mock_requests.post.return_value = mock_resp
    
    sid, err = create_content_template(
        "AC_FAKE", "FAKE_TOKEN",
        "Bad Template",
        ""
    )
    
    assert sid is None
    assert "400" in err


# ── submit_for_approval tests ─────────────────────────────────────────────

def test_submit_for_approval_success(mock_requests):
    """Approval submission returns status on 201."""
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "status": "received",
        "name": "speed_to_lead",
        "category": "UTILITY",
    }
    mock_requests.post.return_value = mock_resp
    
    status, err = submit_for_approval(
        "AC_FAKE", "FAKE_TOKEN",
        "HX_FAKE_123",
        "speed_to_lead"
    )
    
    assert status == "received"
    assert err is None


def test_submit_for_approval_already_approved(mock_requests):
    """Handles 200 (already approved) gracefully."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "approved"}
    mock_requests.post.return_value = mock_resp
    
    status, err = submit_for_approval(
        "AC_FAKE", "FAKE_TOKEN",
        "HX_FAKE_123",
        "speed_to_lead"
    )
    
    assert status == "approved"
    assert err is None


# ── check_approval_status tests ───────────────────────────────────────────

def test_check_approval_status_approved(mock_requests):
    """Returns approved status."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "approved"}
    mock_requests.get.return_value = mock_resp
    
    status, err = check_approval_status("AC_FAKE", "FAKE_TOKEN", "HX_FAKE_123")
    
    assert status == "approved"
    assert err is None


def test_check_approval_status_not_found(mock_requests):
    """Returns error on 404."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "Not found"
    mock_requests.get.return_value = mock_resp
    
    status, err = check_approval_status("AC_FAKE", "FAKE_TOKEN", "HX_FAKE_123")
    
    assert status is None
    assert "404" in err


# ── update_yaml_template_sid tests ────────────────────────────────────────

def test_update_yaml_replaces_placeholder(sample_yaml):
    """Replaces HX_replace_with_real_sid with real SID."""
    count = update_yaml_template_sid(sample_yaml, "HX_REAL_TEMPLATE_789")
    
    content = sample_yaml.read_text(encoding="utf-8")
    assert 'notify_template_sid: "HX_REAL_TEMPLATE_789"' in content
    assert "HX_replace_with_real_sid" not in content
    assert count == 2  # two reps


def test_update_yaml_replaces_existing_sid(sample_yaml):
    """Replaces existing HX... SID with new one."""
    # First, set a real SID
    update_yaml_template_sid(sample_yaml, "HX_OLD_TEMPLATE")
    
    # Then replace with new SID
    count = update_yaml_template_sid(sample_yaml, "HX_NEW_TEMPLATE")
    
    content = sample_yaml.read_text(encoding="utf-8")
    assert 'notify_template_sid: "HX_NEW_TEMPLATE"' in content
    assert "HX_OLD_TEMPLATE" not in content
    assert count == 2


def test_update_yaml_preserves_other_fields(sample_yaml):
    """Only changes notify_template_sid, preserves everything else."""
    original_content = sample_yaml.read_text(encoding="utf-8")
    
    update_yaml_template_sid(sample_yaml, "HX_NEW_123")
    
    new_content = sample_yaml.read_text(encoding="utf-8")
    
    # Check key fields preserved
    assert "slug: test-dealer" in new_content
    assert "name: \"Test Dealer\"" in new_content
    assert "+177****0099" in new_content
    assert "Mike" in new_content
    assert "Dana" in new_content


# ── get_twilio_creds tests ────────────────────────────────────────────────

def test_get_twilio_creds_from_env(monkeypatch):
    """Reads credentials from environment."""
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_TEST_SID")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "TEST_TOKEN")
    
    sid, token = get_twilio_creds()
    assert sid == "AC_TEST_SID"
    assert token == "TEST_TOKEN"


def test_get_twilio_creds_missing_exits(monkeypatch):
    """Exits with error if credentials missing."""
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    
    with pytest.raises(SystemExit):
        get_twilio_creds()
