"""P0-01: Twilio signature validation on /webhook/twilio/* endpoints.

Every Twilio webhook handler MUST validate the X-Twilio-Signature header
against the request body. Unsigned, missing, or tampered requests return 403.

The real Twilio RequestValidator requires HTTPS + a real auth token. In tests
we inject a FakeValidator via monkeypatch so we can assert on the contract
without hitting Twilio's signing logic.
"""

from __future__ import annotations

import hashlib
import hmac
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TWILIO_AUTH_TOKEN, make_signed_twilio_request


# --- Fakes for the twilio.request_validator module ----------------------------

class FakeValidator:
    """Stand-in for twilio.request_validator.RequestValidator.

    The fake's behavior is configured per-test via the test class / monkeypatch
    fixtures. Default: signature is "valid" iff it matches the expected HMAC
    for the (uri, body) pair — i.e. it mimics Twilio's real signing.
    """

    def __init__(self, token: str) -> None:
        self.token = token

    def validate(self, uri: str, body, signature: str) -> bool:
        if not signature:
            return False
        # body may be a dict (form params) or bytes
        if isinstance(body, dict):
            body_str = urlencode(sorted(body.items()))
        else:
            body_str = body.decode("utf-8") if isinstance(body, bytes) else str(body)
        expected = hmac.new(
            self.token.encode("utf-8"),
            (uri + body_str).encode("utf-8"),
            hashlib.sha1,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


@pytest.fixture
def fake_validator(monkeypatch):
    """Inject FakeValidator in place of twilio.request_validator.RequestValidator."""
    import twilio.request_validator as rv

    monkeypatch.setattr(rv, "RequestValidator", FakeValidator)


@pytest.fixture
def client():
    """FastAPI test client. Each test gets a fresh one."""
    from app.main import app

    return TestClient(app)


# --- Unit tests for _validate_twilio_signature --------------------------------

def test_validate_accepts_valid_signature(monkeypatch, fake_validator):
    """A properly-signed request returns True."""
    from app.main import _validate_twilio_signature, _twilio_validator_url
    from starlette.requests import Request

    # Build a minimal request-like object (Starlette Request)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/webhook/twilio/sms",
        "headers": [],
        "query_string": b"",
    }
    request = Request(scope)
    # Sign using the SAME URL the validator will compute
    url = _twilio_validator_url(request)
    req_data = make_signed_twilio_request(
        uri=url,
        body={"From": "+160****4567", "Body": "hi"},
    )
    # Inject the signature header
    scope["headers"] = [(b"x-twilio-signature", req_data["headers"]["X-Twilio-Signature"].encode())]
    request = Request(scope)

    assert _validate_twilio_signature(request, req_data["body"]) is True


def test_validate_rejects_missing_signature(monkeypatch, fake_validator):
    """An empty X-Twilio-Signature header returns False."""
    from app.main import _validate_twilio_signature
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/webhook/twilio/sms",
        "headers": [],  # no X-Twilio-Signature
        "query_string": b"",
    }
    request = Request(scope)

    assert _validate_twilio_signature(request, {"From": "+1", "Body": "x"}) is False


def test_validate_rejects_tampered_body(monkeypatch, fake_validator):
    """Signature is bound to (uri, body). Different body = invalid signature."""
    from app.main import _validate_twilio_signature, _twilio_validator_url
    from starlette.requests import Request

    # Build a scope with a known URL
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/webhook/twilio/sms",
        "headers": [],
        "query_string": b"",
    }
    request = Request(scope)
    url = _twilio_validator_url(request)

    # Sign for one body
    signed = make_signed_twilio_request(uri=url, body={"Body": "untampered"})
    # But send a different body
    tampered_body = {"Body": "<script>alert(1)</script>"}

    scope["headers"] = [(b"x-twilio-signature", signed["headers"]["X-Twilio-Signature"].encode())]
    request = Request(scope)

    assert _validate_twilio_signature(request, tampered_body) is False


def test_validate_rejects_when_no_auth_token(monkeypatch):
    """No TWILIO_AUTH_TOKEN configured => fail closed (False)."""
    from app import config as cfg
    from app.main import _validate_twilio_signature
    from starlette.requests import Request

    # Simulate "no auth token"
    monkeypatch.setattr(cfg.settings, "twilio_auth_token", "")

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/webhook/twilio/sms",
        "headers": [(b"x-twilio-signature", b"anything")],
        "query_string": b"",
    }
    request = Request(scope)

    assert _validate_twilio_signature(request, {"Body": "x"}) is False


def test_validate_rejects_garbage_signature(monkeypatch, fake_validator):
    """Random/garbage signature does not match the HMAC."""
    from app.main import _validate_twilio_signature
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/webhook/twilio/sms",
        "headers": [(b"x-twilio-signature", b"deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")],
        "query_string": b"",
    }
    request = Request(scope)

    assert _validate_twilio_signature(request, {"Body": "x"}) is False


# --- HTTP-level tests on the actual /webhook/twilio/sms endpoint --------------

def test_sms_webhook_returns_403_on_unsigned_request(client):
    """POST /webhook/twilio/sms without a valid X-Twilio-Signature returns 403."""
    response = client.post(
        "/webhook/twilio/sms",
        data={"From": "+160****4567", "Body": "test"},
        headers={"X-Twilio-Signature": "garbage"},
    )
    assert response.status_code == 403


def test_sms_webhook_returns_403_on_missing_signature(client):
    """POST /webhook/twilio/sms with no signature header returns 403."""
    response = client.post(
        "/webhook/twilio/sms",
        data={"From": "+160****4567", "Body": "test"},
    )
    assert response.status_code == 403


def test_voice_webhook_returns_403_on_unsigned_request(client):
    """POST /webhook/twilio/voice without a valid signature returns 403."""
    response = client.post(
        "/webhook/twilio/voice",
        data={"From": "+160****4567", "To": "+177****3122"},
        headers={"X-Twilio-Signature": "garbage"},
    )
    assert response.status_code == 403


def test_whatsapp_webhook_returns_403_on_unsigned_request(client):
    """POST /webhook/twilio/whatsapp without a valid signature returns 403."""
    response = client.post(
        "/webhook/twilio/whatsapp",
        data={"From": "whatsapp:+160****4567", "Body": "1"},
        headers={"X-Twilio-Signature": "garbage"},
    )
    assert response.status_code == 403
