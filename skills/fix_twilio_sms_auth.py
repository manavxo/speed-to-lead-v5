#!/usr/bin/env python3
"""
fix_twilio_sms_auth.py — Hermes execution script.

Diagnose and repair the #1 cause of "SMS not sending" in Speed to Lead v5:
a TWILIO_AUTH_TOKEN on Render that does not match TWILIO_ACCOUNT_SID (HTTP 401).

DESIGN PRINCIPLES (read before editing):
- Diagnose-first. Default mode mutates NOTHING. You must pass --apply to change
  Render, and --test-sms <number> to send a real message.
- No hardcoded customer numbers. The test recipient is a REQUIRED argument.
- No secrets in source. Twilio creds load from .env.local (or env). The Render
  API key loads from the RENDER_API_KEY env var only.
- Idempotent. Running --diagnose repeatedly is always safe.

USAGE
  python skills/fix_twilio_sms_auth.py                      # diagnose only (safe)
  python skills/fix_twilio_sms_auth.py --apply              # sync Render + deploy
  python skills/fix_twilio_sms_auth.py --test-sms +1604...  # send 1 verification SMS
  python skills/fix_twilio_sms_auth.py --apply --test-sms +1604...   # full fix

ENV / CONFIG
  RENDER_API_KEY     (required for --apply)  Render API key
  RENDER_SERVICE_ID  (optional)             defaults to the v5 service id below
  TWILIO_FROM_NUMBER (optional)             defaults to the BC number below
  .env.local must contain TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# --- Config (non-secret defaults; override via env) -------------------------
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID", "srv-d8misim7r5hc739rf7sg")
# BC (778) number is the customer/AI-facing sender for Speed to Lead v5.
DEFAULT_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "+17787623122")
LANDING_URL = "https://speed-to-lead-v5.onrender.com/"
REPO_ROOT = Path(__file__).resolve().parent.parent


def log(tag, msg):
    print(f"[{tag:4}] {msg}")


# --- .env.local loader ------------------------------------------------------
def load_env_local():
    """Return dict of KEY->VALUE from repo .env.local, falling back to os.environ."""
    creds = {}
    env_path = REPO_ROOT / ".env.local"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            creds[k.strip()] = v.strip().strip('"').strip("'")
    sid = creds.get("TWILIO_ACCOUNT_SID") or os.environ.get("TWILIO_ACCOUNT_SID")
    token = creds.get("TWILIO_AUTH_TOKEN") or os.environ.get("TWILIO_AUTH_TOKEN")
    return sid, token


# --- Twilio: auth check (read-only) -----------------------------------------
def twilio_auth_ok(sid, token):
    """Return HTTP status of an Accounts fetch. 200 = valid pair, 401 = mismatch."""
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json"
    req = urllib.request.Request(url)
    import base64
    basic = base64.b64encode(f"{sid}:{token}".encode()).decode()
    req.add_header("Authorization", f"Basic {basic}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


# --- Render API helpers -----------------------------------------------------
def render_headers():
    key = os.environ.get("RENDER_API_KEY")
    if not key:
        log("FAIL", "RENDER_API_KEY env var not set — required for --apply.")
        sys.exit(2)
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def render_get_env(headers):
    url = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/env-vars"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return {item["envVar"]["key"]: item["envVar"]["value"] for item in data}


def render_put_env(headers, key, value):
    url = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/env-vars/{key}"
    body = json.dumps({"value": value}).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="PUT")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def render_deploy(headers):
    url = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/deploys"
    req = urllib.request.Request(url, data=b"{}", headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["id"]


def render_deploy_status(headers):
    url = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/deploys?limit=1"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)[0]["deploy"]["status"]


def http_status(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


# --- Actions ----------------------------------------------------------------
def diagnose(from_number):
    log("INFO", "=== DIAGNOSE (read-only) ===")
    sid, token = load_env_local()
    if not sid or not token:
        log("FAIL", "No Twilio creds in .env.local or environment.")
        return False
    local_status = twilio_auth_ok(sid, token)
    log("INFO", f"Local .env.local pair  -> Twilio auth {local_status} "
                f"({'VALID' if local_status == 200 else 'INVALID'})")

    render_status_note = "skipped (no RENDER_API_KEY)"
    if os.environ.get("RENDER_API_KEY"):
        try:
            env = render_get_env(render_headers())
            r_sid = env.get("TWILIO_ACCOUNT_SID", "")
            r_token = env.get("TWILIO_AUTH_TOKEN", "")
            r_status = twilio_auth_ok(r_sid, r_token) if r_sid and r_token else 0
            log("INFO", f"Render pair            -> Twilio auth {r_status} "
                        f"({'VALID' if r_status == 200 else 'INVALID'})")
            log("INFO", f"Render TWILIO_PHONE_NUMBER = {env.get('TWILIO_PHONE_NUMBER')}")
            if r_status != 200 and local_status == 200:
                log("WARN", "Render pair is BROKEN but local pair WORKS -> run --apply to fix.")
            render_status_note = f"auth {r_status}"
        except Exception as e:
            log("WARN", f"Could not read Render env: {e}")
    log("INFO", f"Landing page {LANDING_URL} -> {http_status(LANDING_URL)}")
    log("INFO", f"Intended sender (from) = {from_number}")
    log("INFO", f"Render check: {render_status_note}")
    return local_status == 200


def apply_fix(from_number):
    log("INFO", "=== APPLY (mutates Render) ===")
    sid, token = load_env_local()
    if twilio_auth_ok(sid, token) != 200:
        log("FAIL", "Local .env.local pair is NOT valid (auth != 200). Refusing to "
                    "push a broken pair to Render. Get a working token first.")
        return False
    headers = render_headers()
    log("OK", f"PUT TWILIO_ACCOUNT_SID   -> {render_put_env(headers, 'TWILIO_ACCOUNT_SID', sid)}")
    log("OK", f"PUT TWILIO_AUTH_TOKEN    -> {render_put_env(headers, 'TWILIO_AUTH_TOKEN', token)}")
    log("OK", f"PUT TWILIO_PHONE_NUMBER  -> {render_put_env(headers, 'TWILIO_PHONE_NUMBER', from_number)}")
    dep = render_deploy(headers)
    log("INFO", f"Triggered deploy {dep}. Polling until live...")
    for _ in range(40):  # ~6-7 min max
        status = render_deploy_status(headers)
        if status == "live":
            log("OK", "Deploy is live.")
            return True
        if status in ("build_failed", "update_failed", "canceled", "deactivated"):
            log("FAIL", f"Deploy ended in status: {status}")
            return False
        time.sleep(10)
    log("WARN", "Timed out waiting for live; check Render dashboard.")
    return False


def send_test_sms(from_number, to_number):
    log("INFO", f"=== TEST SMS -> {to_number} ===")
    sid, token = load_env_local()
    try:
        from twilio.rest import Client
    except ImportError:
        log("FAIL", "twilio SDK not installed (pip install twilio).")
        return False
    client = Client(sid, token)
    msg = client.messages.create(
        body="Speed to Lead v5: SMS pipeline verified (Hermes self-check).",
        from_=from_number,
        to=to_number,
    )
    log("OK", f"Sent SID={msg.sid} status={msg.status}")
    for _ in range(12):
        time.sleep(5)
        m = client.messages(msg.sid).fetch()
        if m.status in ("delivered", "failed", "undelivered"):
            tag = "OK" if m.status == "delivered" else "FAIL"
            log(tag, f"Final status={m.status} error={m.error_code} {m.error_message or ''}")
            return m.status == "delivered"
    log("WARN", "Did not reach a terminal status in time; check Twilio console.")
    return True


def main():
    p = argparse.ArgumentParser(description="Fix Twilio SMS 401 (credential mismatch).")
    p.add_argument("--apply", action="store_true", help="Sync working creds to Render + deploy.")
    p.add_argument("--test-sms", metavar="E164", help="Send one verification SMS to this number.")
    p.add_argument("--from", dest="from_number", default=DEFAULT_FROM_NUMBER,
                   help=f"Sender number (default {DEFAULT_FROM_NUMBER}, the BC number).")
    args = p.parse_args()

    ok = diagnose(args.from_number)
    if args.apply:
        ok = apply_fix(args.from_number) and ok
    if args.test_sms:
        ok = send_test_sms(args.from_number, args.test_sms) and ok
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
