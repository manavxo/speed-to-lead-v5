"""P0-08: CSRF protection on dashboard login.

The login form must require a CSRF token. The token is generated on
GET /dashboard/login (rendered as a hidden field and set as a
double-submit cookie). POST /dashboard/login must validate that the
form's csrf_token matches the cookie. Missing or mismatched tokens
return 403 before any credential check happens.

Pattern: double-submit cookie. Server generates a random token, sets
it in a cookie, and mirrors it in the form. POST compares form to
cookie using constant-time comparison.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _extract_csrf_token(html: str) -> str:
    """Pull the csrf_token value out of a rendered login page."""
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert match is not None, (
        f"csrf_token hidden input not found in login HTML:\n{html[:500]}"
    )
    return match.group(1)


# ---- GET /dashboard/login ---------------------------------------------------

def test_login_page_renders_csrf_token_input(client):
    """GET /dashboard/login must render a hidden csrf_token input with a
    real (non-empty, non-placeholder) value."""
    response = client.get("/dashboard/login")
    assert response.status_code == 200
    token = _extract_csrf_token(response.text)
    assert len(token) >= 32, (
        f"CSRF token too short ({len(token)} chars), looks like a placeholder: {token!r}"
    )


def test_login_page_sets_csrf_token_cookie(client):
    """GET /dashboard/login must set a csrf_token cookie that mirrors the
    form value (double-submit pattern)."""
    response = client.get("/dashboard/login")
    assert response.status_code == 200
    cookie = response.cookies.get("csrf_token")
    assert cookie is not None, "csrf_token cookie not set on login page"
    form_value = _extract_csrf_token(response.text)
    assert cookie == form_value, (
        f"Cookie value must match form value (double-submit). "
        f"cookie={cookie!r}, form={form_value!r}"
    )


# ---- POST /dashboard/login (CSRF enforcement) ------------------------------

def test_login_post_without_csrf_token_returns_403(client):
    """POST without a csrf_token form field is rejected with 403, regardless
    of credentials. The CSRF check must happen before any other validation."""
    response = client.post(
        "/dashboard/login",
        data={
            "dealer_slug": "smoke-test",
            "username": "admin",
            "password": "any-password",
        },
    )
    assert response.status_code == 403, (
        f"POST without csrf_token should be 403, got {response.status_code}: "
        f"{response.text[:200]}"
    )


def test_login_post_with_mismatched_csrf_token_returns_403(client):
    """POST with a form csrf_token that doesn't match the cookie is rejected
    with 403. Simulates an attacker who can't read the cookie but guesses
    a form value."""
    # Get a real cookie from the GET
    get_response = client.get("/dashboard/login")
    assert get_response.status_code == 200

    # POST with a fake token (mismatched with the real cookie)
    response = client.post(
        "/dashboard/login",
        data={
            "dealer_slug": "smoke-test",
            "username": "admin",
            "password": "any-password",
            "csrf_token": "attacker-controlled-fake-token",
        },
    )
    assert response.status_code == 403, (
        f"POST with mismatched csrf_token should be 403, got {response.status_code}"
    )
