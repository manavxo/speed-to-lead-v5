#!/usr/bin/env python3
"""Configure + verify the Twilio WhatsApp sandbox webhook for Speed to Lead v5.

Steps performed:
  1. Load credentials from .env.local
  2. Health-check the webhook endpoint (expects 405 on GET = live)
  3. Send a Twilio-signed test POST to confirm the endpoint accepts valid requests
  4. Attempt automated sandbox config via Twilio API (graceful fallback if unsupported)
  5. Print exact manual Console steps + direct URL if automation isn't possible
  6. Final verification summary

Usage:
  python configure_twilio_sandbox.py [--verify-only]

  --verify-only  Skip setup steps; just check current webhook health.
"""

import hashlib
import hmac
import os
import sys
import urllib.parse
import urllib.request
import base64
import json
import argparse
from pathlib import Path


# --- Config -------------------------------------------------------------------

WEBHOOK_URL = "https://speed-to-lead-v5.onrender.com/webhook/twilio/whatsapp"
SANDBOX_NUMBER = "+14155238886"
CONSOLE_URL = (
    "https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn"
)


# --- Helpers ------------------------------------------------------------------

def _load_env():
    env_file = Path(__file__).parent / ".env.local"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def _twilio_signature(auth_token: str, url: str, params: dict) -> str:
    """Compute X-Twilio-Signature for a POST request."""
    s = url
    for key in sorted(params.keys()):
        s += key + str(params[key])
    mac = hmac.new(
        auth_token.encode("utf-8"), s.encode("utf-8"), hashlib.sha1
    )
    return base64.b64encode(mac.digest()).decode()


def _http_get(url: str, timeout: int = 15) -> tuple[int, str]:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except Exception as e:
        return 0, str(e)


def _http_post_form(url: str, params: dict, headers: dict,
                    timeout: int = 15) -> tuple[int, str]:
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except Exception as e:
        return 0, str(e)


def _twilio_api(account_sid: str, auth_token: str,
                path: str, method: str = "GET",
                body=None):
    creds = base64.b64encode(
        f"{account_sid}:{auth_token}".encode()
    ).decode()
    url = f"https://api.twilio.com{path}"
    headers = {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = urllib.parse.urlencode(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read())
        except Exception:
            payload = {"error": str(e)}
        return e.code, payload
    except Exception as e:
        return 0, {"error": str(e)}


def _ok(msg: str): print(f"  [OK]  {msg}")
def _warn(msg: str): print(f"  [!!]  {msg}")
def _info(msg: str): print(f"  [ ]   {msg}")
def _section(title: str): print(f"\n{'='*60}\n{title}\n{'='*60}")


# --- Steps --------------------------------------------------------------------

def step_health_check() -> bool:
    _section("1. Webhook endpoint health check")
    status, body = _http_get(WEBHOOK_URL)
    if status == 405:
        _ok(f"Endpoint live - GET->405 (correct, POST-only webhook)")
        return True
    elif status == 200:
        _ok(f"Endpoint live - GET->200")
        return True
    elif status == 0:
        _warn(f"Endpoint unreachable: {body}")
        return False
    else:
        _warn(f"Unexpected GET response: {status}")
        return True  # might still accept POST


def step_signed_test(account_sid: str, auth_token: str) -> bool:
    _section("2. Signed webhook test (simulates Twilio POST)")
    test_params = {
        "AccountSid": account_sid,
        "From": f"whatsapp:{SANDBOX_NUMBER}",
        "To": "whatsapp:+14155238886",
        "Body": "HERMES_SANDBOX_VERIFY",
        "MessageSid": "SM_HERMES_SANDBOX_TEST",
        "NumMedia": "0",
    }
    sig = _twilio_signature(auth_token, WEBHOOK_URL, test_params)
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Twilio-Signature": sig,
    }
    status, body = _http_post_form(WEBHOOK_URL, test_params, headers)
    if status in (200, 204):
        _ok(f"Endpoint accepted signed POST -> {status}")
        _info(f"Response snippet: {body[:120]}")
        return True
    elif status == 400:
        _warn(f"Endpoint returned 400 - likely no dealer configured for sandbox number")
        _info("This is expected before a dealer's whatsapp_sender matches the sandbox number")
        _info(f"Response: {body[:200]}")
        return True  # endpoint works, just no matching dealer
    elif status == 403:
        _warn("Endpoint rejected signature - check TWILIO_AUTH_TOKEN matches Render env var")
        return False
    else:
        _warn(f"Unexpected response: {status}")
        _info(f"Body: {body[:200]}")
        return False


def step_api_configure(account_sid: str, auth_token: str) -> bool:
    _section("3. Attempting automated sandbox webhook configuration")

    # Twilio doesn't expose a REST endpoint for WhatsApp sandbox webhook.
    # We attempt the call anyway so Hermes has a record of what was tried.
    # Expected: 404 (sandbox endpoint doesn't exist in REST API).
    status, resp = _twilio_api(
        account_sid, auth_token,
        f"/2010-04-01/Accounts/{account_sid}/IncomingPhoneNumbers.json",
    )
    if status == 200:
        numbers = resp.get("incoming_phone_numbers", [])
        sandbox_entry = next(
            (n for n in numbers if n.get("phone_number") == SANDBOX_NUMBER), None
        )
        if sandbox_entry:
            phone_sid = sandbox_entry["sid"]
            _info(f"Found sandbox number SID: {phone_sid} - attempting update…")
            upd_status, upd_resp = _twilio_api(
                account_sid, auth_token,
                f"/2010-04-01/Accounts/{account_sid}/IncomingPhoneNumbers/{phone_sid}.json",
                method="POST",
                body={"SmsUrl": WEBHOOK_URL, "SmsMethod": "POST"},
            )
            if upd_status == 200:
                _ok("Webhook configured automatically via REST API!")
                return True
            else:
                _warn(f"Update failed: {upd_status} - {upd_resp}")
        else:
            _info("Sandbox number not in IncomingPhoneNumbers (shared sandbox - expected)")
    else:
        _info(f"Phone number list: {status}")

    _warn("Automated configuration not possible - WhatsApp sandbox requires manual Console setup")
    return False


def step_manual_instructions():
    _section("4. Manual configuration (ONE-TIME, takes ~60 seconds)")
    print(f"""
  The Twilio WhatsApp Sandbox webhook MUST be set via the Twilio Console.
  This is a Twilio platform limitation - no REST API exists for sandbox webhook config.

  +-----------------------------------------------------------------+
  |  STEP A  Open this URL (you must be logged into Twilio):        |
  |  {CONSOLE_URL:<63}|
  |                                                                 |
  |  STEP B  Scroll to "Sandbox Configuration"                      |
  |                                                                 |
  |  STEP C  Set "WHEN A MESSAGE COMES IN":                         |
  |  {WEBHOOK_URL:<63}|
  |  Method: POST                                                   |
  |                                                                 |
  |  STEP D  Click Save                                             |
  +-----------------------------------------------------------------+

  After saving, run this script again with --verify-only to confirm.
""")


def step_verify_summary(health_ok: bool, signed_ok: bool):
    _section("5. Summary")
    if health_ok and signed_ok:
        _ok("Webhook endpoint is live and accepts Twilio-signed requests")
        _ok(f"URL: {WEBHOOK_URL}")
        _info("Final step: complete the Console configuration above, then test")
        _info(f"by sending a WhatsApp message to {SANDBOX_NUMBER}")
    else:
        _warn("One or more checks failed - see details above")


# --- Entry point --------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true",
                        help="Skip setup; only run health + signed test")
    args = parser.parse_args()

    _load_env()

    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not account_sid or not auth_token:
        print("ERROR: TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN not set in .env.local")
        sys.exit(1)

    print(f"\nSpeed to Lead v5 - Twilio WhatsApp Sandbox Configurator")
    print(f"Account: {account_sid}")
    print(f"Target:  {WEBHOOK_URL}")

    health_ok = step_health_check()
    signed_ok = step_signed_test(account_sid, auth_token)

    if not args.verify_only:
        auto_ok = step_api_configure(account_sid, auth_token)
        if not auto_ok:
            step_manual_instructions()

    step_verify_summary(health_ok, signed_ok)


if __name__ == "__main__":
    main()
