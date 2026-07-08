# Speed to Lead v5 — Build Plan

> **For the build session:** Work task-by-task. Test fails first, then implementation, then verify, then commit. One commit per task. No fabricated results. Stop at the end of each task to confirm with the user before moving to the next.

> **Scope of this plan:** Phase 0 (P0-01 + P0-08) + Phase 1 step 1 (the `notify_rep` abstraction with Twilio WhatsApp default). The remaining 4 P0 fixes (P0-02, P0-04, P0-05, P0-06) and the rest of Phase 1 are deferred to later sessions and outlined at the bottom.

> **v5 hard rule:** `OUTBOUND_ENABLED=false` default. Real SMS / WhatsApp only when user explicitly says "enable live." Twilio credits burned in v4 by automated tests — never again.

---

## Phase 0 — Safety net

### Task 0.1: Twilio signature validation (P0-01)

**Why first:** This is the only P0 fix that's a non-negotiable prerequisite for the WhatsApp feature — we're literally about to add more Twilio surface area (WhatsApp templates), so the signature bypass has to be closed first. Without it, any attacker who knows the webhook URL can fake both customer SMS and WhatsApp messages.

**Files:**
- Create: `tests/test_webhook_security.py`
- Modify: `app/main.py` (add `_validate_twilio_signature`, apply to all /webhook/twilio/* handlers)

**Step 1: Write failing test (RED)**

```python
"""P0-01: Twilio signature validation.

Every /webhook/twilio/* endpoint MUST validate the X-Twilio-Signature
header against the request body. Unsigned or tampered requests return 403.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app, _validate_twilio_signature
from tests.conftest import TWILIO_AUTH_TOKEN


# A valid signed request for a test endpoint
def _signed_request(uri: str, body: dict, signature: str = "valid-sig") -> dict:
    return {"uri": uri, "body": body, "signature": signature}


def test_validate_accepts_valid_signature():
    """Signed request with valid signature must return True."""
    # Note: we mock the validator via monkeypatch since the real Twilio
    # validation requires HTTPS and a real auth token.
    from app import main as m
    monkey = pytest.MonkeyPatch()

    class FakeValidator:
        def validate(self, uri, body, signature):
            return signature == "valid-sig"
    monkey.setattr(m, "RequestValidator", lambda token: FakeValidator())

    result = m._validate_twilio_signature(
        uri="https://example.com/webhook/twilio/sms",
        body=b"From=%2B16041234567&Body=hi",
        signature="valid-sig",
    )
    assert result is True
    monkey.undo()


def test_validate_rejects_missing_signature():
    """Missing X-Twilio-Signature header must return False."""
    from app import main as m

    class FakeValidator:
        def validate(self, uri, body, signature):
            return bool(signature)
    m.RequestValidator = lambda token: FakeValidator()

    result = m._validate_twilio_signature(
        uri="https://example.com/webhook/twilio/sms",
        body=b"From=%2B16041234567&Body=hi",
        signature="",
    )
    assert result is False


def test_validate_rejects_tampered_body():
    """Body that was modified after signing must return False."""
    from app import main as m

    class FakeValidator:
        def validate(self, uri, body, signature):
            # Real validator: signature is computed from the body, so a
            # tampered body fails. Simulate: signature valid only for
            # body that starts with "untampered:"
            return body.startswith(b"untampered:") and signature == "valid-sig"
    m.RequestValidator = lambda token: FakeValidator()

    # Tampered body: not the one that was signed
    result = m._validate_twilio_signature(
        uri="https://example.com/webhook/twilio/sms",
        body=b"<script>alert(1)</script>",
        signature="valid-sig",
    )
    assert result is False


def test_sms_webhook_rejects_unsigned_request():
    """POST to /webhook/twilio/sms without a valid signature returns 403."""
    client = TestClient(app)
    response = client.post(
        "/webhook/twilio/sms",
        data={"From": "+16041234567", "Body": "test"},
        headers={"X-Twilio-Signature": "garbage"},
    )
    assert response.status_code == 403


def test_sms_webhook_accepts_signed_request():
    """POST to /webhook/twilio/sms with a valid signature returns 200."""
    # This test relies on the FakeValidator fixture in conftest.py
    # and the test client to round-trip a properly-signed request.
    # The fixture in conftest.py should make this work end-to-end.
    from tests.conftest import make_signed_twilio_request
    client = TestClient(app)
    request_data = make_signed_twilio_request(
        uri="/webhook/twilio/sms",
        body={"From": "+16041234567", "Body": "test"},
    )
    response = client.post(
        request_data["uri"],
        data=request_data["body"],
        headers=request_data["headers"],
    )
    assert response.status_code in (200, 204)
```

Run: `pytest tests/test_webhook_security.py -v`
Expected: FAIL — `ImportError: cannot import name '_validate_twilio_signature'`

**Step 2: Implement (GREEN)**

Add to `app/main.py`:

```python
from twilio.request_validator import RequestValidator


def _validate_twilio_signature(uri: str, body: bytes, signature: str) -> bool:
    """Validate a Twilio webhook signature.

    Twilio computes an HMAC-SHA1 of (uri + sorted form params) using the
    auth token. The signature comes in the X-Twilio-Signature header.
    Returns True only if the signature matches.
    """
    if not signature:
        return False
    token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    if not token:
        # Fail closed — never accept unsigned requests when no token is set
        return False
    validator = RequestValidator(token)
    # Twilio validates the form-encoded body. The RequestValidator takes
    # the body as a dict of params (already parsed by FastAPI/Starlette).
    return validator.validate(uri, body, signature)
```

Then update each `/webhook/twilio/*` handler to call it. Pattern:

```python
@app.post("/webhook/twilio/sms")
async def webhook_twilio_sms(request: Request) -> Response:
    # P0-01: validate Twilio signature
    body = await request.body()
    sig = request.headers.get("X-Twilio-Signature", "")
    uri = str(request.url)
    if not _validate_twilio_signature(uri, body, sig):
        return Response(status_code=403, content="invalid signature")
    # ... existing handler logic ...
```

Apply the same pattern to:
- `/webhook/twilio/voice`
- `/webhook/twilio/whatsapp`

Run: `pytest tests/test_webhook_security.py -v`
Expected: PASS — all 5 tests green

Run: `pytest tests/ -v`
Expected: existing tests still pass (some webhook tests may need the `make_signed_twilio_request` fixture — see Step 3)

**Step 3: Add `make_signed_twilio_request` fixture to conftest.py**

The existing tests in `tests/test_pipeline_e2e.py` and `tests/test_conversation.py` POST to webhook URLs. With signature validation in place, those tests need to sign their requests too. Add to `tests/conftest.py`:

```python
def make_signed_twilio_request(uri: str, body: dict, secret: str = "test-twilio-secret") -> dict:
    """Build a properly-signed Twilio webhook request for testing."""
    import hmac
    import hashlib
    from urllib.parse import urlencode

    # Twilio signs: uri + sorted query/form params concatenated
    # Reference: https://www.twilio.com/docs/usage/webhooks/webhooks-security
    body_str = urlencode(sorted(body.items()))
    data = (uri + body_str).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), data, hashlib.sha1).hexdigest()
    return {
        "uri": uri,
        "body": body,
        "headers": {"X-Twilio-Signature": sig},
    }
```

Then update the conftest to set `TWILIO_AUTH_TOKEN=test-twilio-secret` for tests:

```python
@pytest.fixture(autouse=True)
def set_test_env(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-twilio-secret")
    monkeypatch.setenv("OUTBOUND_ENABLED", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    # ... other test env vars
```

Update existing tests in `test_pipeline_e2e.py` to use `make_signed_twilio_request` for webhook POSTs. (The subagent should know which lines to update — search for `client.post.*twilio` and wrap with the fixture.)

Run: `pytest tests/ -v`
Expected: ALL tests pass

**Step 4: Commit**

```bash
cd "C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5"
git add -A
git commit -m "fix: P0-01 Twilio signature validation

Closes the no-op signature bypass on /webhook/twilio/{sms,voice,whatsapp}.
Uses twilio.request_validator.RequestValidator. Returns 403 on missing,
invalid, or tampered signatures. Test fixture make_signed_twilio_request
added to conftest.py for use by other tests."
```

**Step 5: Stop and report**

Report to the user:
- 5 tests added in tests/test_webhook_security.py
- `_validate_twilio_signature` added in app/main.py
- Applied to 3 webhook endpoints (sms, voice, whatsapp)
- conftest.py updated with `make_signed_twilio_request` fixture
- Existing webhook tests updated to use the fixture
- Commit hash
- Test results: `pytest -v` summary

---

### Task 0.2: CSRF on dashboard login (P0-08) — DEFERRED

Will land in a later session. The notification abstraction (Task 1.1) doesn't need it. Defer to keep this session focused on the WhatsApp feature.

### Tasks 0.3 through 0.7: Other P0 fixes (P0-02, P0-04, P0-05, P0-06) — DEFERRED

Will land in a later session. The notification abstraction (Task 1.1) doesn't need them. Defer to keep this session focused on the WhatsApp feature.

---

## Phase 1, Step 1 — `notify_rep` abstraction with Twilio WhatsApp

### Task 1.1: `notify_rep()` chokepoint

**Why:** Today, `app/engine/router.py` calls `send_sms()` directly for rep claim pings. That sends an SMS, not a WhatsApp message. We need a single chokepoint so:
- The default channel is WhatsApp (per the user's directive)
- The backend can be swapped (Twilio → Meta direct → email → dashboard) without touching callers
- All rep notifications land in the `Message` table (the lead detail page shows them)
- Every notification respects the `OUTBOUND_ENABLED` dry-run gate

**Files:**
- Create: `tools/notify_rep.py`
- Create: `tests/test_notify_rep.py`
- Modify: `app/engine/router.py` (replace direct `send_sms` for rep claim with `notify_rep`)
- Modify: `dealers/example-dealer.yaml` (add `notification_preferences` per rep)
- Modify: `app/models/__init__.py` (if needed — add a `Rep` model field for `notify_backend`)

**Step 1: Write failing test (RED)**

```python
"""P1-1: notify_rep abstraction.

A single chokepoint for all dealer-side notifications. The backend
is configurable per rep: twilio_whatsapp (default), sms (fallback),
email (Phase 2), dashboard (Phase 2).

Every notification persists a Message row and respects OUTBOUND_ENABLED.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from app.models import Channel, Dealer, Lead, LeadState, Message, Rep
from tools.notify_rep import notify_rep, NotificationResult


@pytest.fixture
def dealer_with_rep(db_session):
    dealer = Dealer(
        slug="notify-test",
        name="Notify Test Dealer",
        config={
            "dealer": {"name": "Notify Test Dealer"},
            "sales_team": [
                {"name": "Mike", "phone": "+16041234001", "active": True,
                 "notify_backend": "twilio_whatsapp", "notify_template_sid": "HXxxxxxx"}
            ],
        },
    )
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)
    return dealer


def test_notify_rep_dispatches_to_twilio_whatsapp_by_default(db_session, dealer_with_rep, monkeypatch):
    """Default backend is twilio_whatsapp — calls Twilio with a template."""
    lead = Lead(
        dealer_id=dealer_with_rep.id,
        customer_name="Test Customer",
        customer_phone="+16041234999",
        channel=Channel.SMS,
        state=LeadState.ASSIGNED,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    rep_config = dealer_with_rep.config["sales_team"][0]
    fake_messages = []
    def fake_send_whatsapp_template(to, from_, body, **kwargs):
        fake_messages.append({"to": to, "from": from_, "body": body, **kwargs})
        return "FAKE_SID"
    monkeypatch.setattr(
        "tools.notify_rep.send_whatsapp_template",
        fake_send_whatsapp_template,
    )

    result = notify_rep(
        rep_config=rep_config,
        lead=lead,
        message_type="claim",
        payload={"lead_id": lead.id, "customer_name": "Test Customer", "vehicle": "2019 Honda Civic"},
        dealer_config=dealer_with_rep.config,
    )

    assert result.success is True
    assert result.backend == "twilio_whatsapp"
    assert result.message_sid == "FAKE_SID"
    assert len(fake_messages) == 1
    assert fake_messages[0]["to"] == "+16041234001"


def test_notify_rep_falls_back_to_sms_when_whatsapp_unavailable(db_session, dealer_with_rep, monkeypatch):
    """If WhatsApp not provisioned, fallback to SMS."""
    lead = Lead(
        dealer_id=dealer_with_rep.id,
        customer_name="Test Customer",
        customer_phone="+16041234999",
        channel=Channel.SMS,
        state=LeadState.ASSIGNED,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    rep_config = {"name": "Dana", "phone": "+16041234002", "active": True, "notify_backend": "sms"}

    fake_sms = []
    def fake_send_sms(*args, **kwargs):
        fake_sms.append({"to": kwargs.get("to_phone"), "body": kwargs.get("body")})
        return "FAKE_SMS_SID"
    monkeypatch.setattr("tools.notify_rep.send_sms", fake_send_sms)

    result = notify_rep(
        rep_config=rep_config,
        lead=lead,
        message_type="claim",
        payload={"lead_id": lead.id, "customer_name": "Test Customer"},
        dealer_config=dealer_with_rep.config,
    )

    assert result.success is True
    assert result.backend == "sms"
    assert len(fake_sms) == 1
    assert fake_sms[0]["to"] == "+16041234002"


def test_notify_rep_persists_message_row(db_session, dealer_with_rep, monkeypatch):
    """A Message row is always persisted (the lead detail page needs it)."""
    lead = Lead(
        dealer_id=dealer_with_rep.id,
        customer_name="Test Customer",
        customer_phone="+16041234999",
        channel=Channel.SMS,
        state=LeadState.ASSIGNED,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    rep_config = dealer_with_rep.config["sales_team"][0]
    monkeypatch.setattr("tools.notify_rep.send_whatsapp_template", lambda *a, **kw: "FAKE_SID")

    initial_count = len(db_session.query(Message).all())

    notify_rep(
        rep_config=rep_config,
        lead=lead,
        message_type="claim",
        payload={"lead_id": lead.id},
        dealer_config=dealer_with_rep.config,
    )

    final_count = len(db_session.query(Message).all())
    assert final_count == initial_count + 1
    new_msg = db_session.query(Message).order_by(Message.id.desc()).first()
    assert new_msg.direction.value == "outbound"  # or Direction.OUTBOUND
    assert new_msg.lead_id == lead.id
    assert new_msg.recipient_role == "rep"  # new field, see Step 2


def test_notify_rep_respects_outbound_disabled(db_session, dealer_with_rep, monkeypatch):
    """When OUTBOUND_ENABLED=false, no real send happens — the message is logged."""
    lead = Lead(
        dealer_id=dealer_with_rep.id,
        customer_name="Test Customer",
        customer_phone="+16041234999",
        channel=Channel.SMS,
        state=LeadState.ASSIGNED,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    rep_config = dealer_with_rep.config["sales_team"][0]
    monkeypatch.setattr("tools.notify_rep.send_whatsapp_template", lambda *a, **kw: "REAL_SID")
    monkeypatch.setenv("OUTBOUND_ENABLED", "false")

    result = notify_rep(
        rep_config=rep_config,
        lead=lead,
        message_type="claim",
        payload={"lead_id": lead.id},
        dealer_config=dealer_with_rep.config,
    )

    # The "send" was a no-op (dry-run), but the message is still recorded
    assert result.dry_run is True
    assert result.success is True
    assert result.message_sid is None  # No real SID in dry-run
```

Run: `pytest tests/test_notify_rep.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.notify_rep'`

**Step 2: Implement (GREEN)**

Create `tools/notify_rep.py`:

```python
"""Single chokepoint for dealer-side notifications.

The router and other engine modules call this instead of send_sms()
directly for rep-targeted messages. The backend is configurable per
rep via the `notify_backend` field in the dealer config.

Backends:
- twilio_whatsapp (default): pre-approved Twilio WhatsApp template
- sms (fallback): legacy SMS via send_sms()
- email (Phase 2): not yet implemented
- dashboard (Phase 2): in-app notification when dealer is logged in
"""
from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from typing import Any

from app.models import Lead, Message, Direction, Channel, LeadEvent

logger = logging.getLogger(__name__)


@dataclass
class NotificationResult:
    success: bool
    backend: str
    message_sid: str | None
    dry_run: bool = False
    error: str | None = None


def _build_message_body(message_type: str, payload: dict) -> str:
    """Map (message_type, payload) to a human-readable notification body."""
    if message_type == "claim":
        return (
            f"New lead: {payload.get('customer_name', 'A customer')} "
            f"wants the {payload.get('vehicle', 'a vehicle')}. "
            f"Reply 1 to claim, 2 to pass."
        )
    elif message_type == "escalation":
        return (
            f"Lead #{payload.get('lead_id')} unclaimed for "
            f"{payload.get('minutes', '?')} min. Needs a new rep."
        )
    elif message_type == "appointment":
        return (
            f"Test drive booked! {payload.get('customer_name')} for "
            f"the {payload.get('vehicle')} on {payload.get('datetime')}."
        )
    elif message_type == "missed_call_handoff":
        return (
            f"{payload.get('customer_name')} asked for you by name "
            f"after a missed call. Their number: {payload.get('phone')}."
        )
    else:
        return f"Lead update: {payload}"


def _send_via_twilio_whatsapp(rep_config: dict, body: str) -> str | None:
    """Send via Twilio WhatsApp template. Returns message SID or None on dry-run."""
    from tools.notify_rep_deps import send_whatsapp_template  # local import for testability
    return send_whatsapp_template(
        to=rep_config["phone"],
        from_=os.environ.get("TWILIO_WHATSAPP_FROM", ""),
        body=body,
        template_sid=rep_config.get("notify_template_sid"),
    )


def _send_via_sms(rep_config: dict, body: str) -> str | None:
    """Fallback: send via SMS chokepoint."""
    from tools.send_sms import send_sms
    return send_sms(
        to_phone=rep_config["phone"],
        body=body,
        channel=Channel.SMS,
    )


def notify_rep(
    rep_config: dict,
    lead: Lead,
    message_type: str,
    payload: dict,
    dealer_config: dict,
    db_session=None,
) -> NotificationResult:
    """Send a dealer-side notification. The single chokepoint.

    Args:
        rep_config: the rep's row from dealer config (with phone, notify_backend, etc.)
        lead: the Lead this notification is about
        message_type: "claim" | "escalation" | "appointment" | "missed_call_handoff"
        payload: dict with message_type-specific fields
        dealer_config: the full dealer config (for templates, etc.)
        db_session: optional SQLAlchemy session (if None, looks up from app.db)

    Returns:
        NotificationResult with success flag, backend used, and message SID
    """
    if not rep_config.get("active", True):
        return NotificationResult(
            success=False, backend="none", message_sid=None,
            error="rep is inactive",
        )

    body = _build_message_body(message_type, payload)
    backend = rep_config.get("notify_backend", "twilio_whatsapp")
    dry_run = os.environ.get("OUTBOUND_ENABLED", "false").lower() != "true"
    message_sid = None
    error = None

    if dry_run:
        logger.info(
            "[DRYRUN] notify_rep: backend=%s to=%s type=%s body=%s",
            backend, rep_config.get("phone"), message_type, body,
        )
    else:
        try:
            if backend == "twilio_whatsapp":
                message_sid = _send_via_twilio_whatsapp(rep_config, body)
            elif backend == "sms":
                message_sid = _send_via_sms(rep_config, body)
            elif backend == "email":
                return NotificationResult(
                    success=False, backend=backend, message_sid=None,
                    error="email backend not yet implemented (Phase 2)",
                )
            elif backend == "dashboard":
                return NotificationResult(
                    success=True, backend=backend, message_sid=None,
                    error=None,  # dashboard is always "success" since it just persists
                )
            else:
                return NotificationResult(
                    success=False, backend=backend, message_sid=None,
                    error=f"unknown backend: {backend}",
                )
        except Exception as e:
            logger.exception("notify_rep failed: backend=%s type=%s", backend, message_type)
            error = str(e)

    # Always persist a Message row (the lead detail page needs it)
    try:
        if db_session is None:
            from app.db import get_session_factory
            db_session = get_session_factory()()

        outbound_msg = Message(
            lead_id=lead.id,
            direction=Direction.OUTBOUND,
            channel=Channel.SMS if backend == "sms" else Channel.WHATSAPP,
            body=body,
            sender_role="system",
            recipient_role="rep",
            twilio_sid=message_sid,
        )
        db_session.add(outbound_msg)

        # Also log a LeadEvent for audit
        event = LeadEvent(
            lead_id=lead.id,
            event_type=f"notify_rep_{message_type}",
            event_data={"backend": backend, "dry_run": dry_run, "sid": message_sid},
        )
        db_session.add(event)
        db_session.commit()
    except Exception:
        logger.exception("notify_rep: failed to persist Message row")
        # Don't fail the notification just because persistence failed

    return NotificationResult(
        success=error is None,
        backend=backend,
        message_sid=message_sid,
        dry_run=dry_run,
        error=error,
    )
```

You'll also need to add:
- `Message.recipient_role` field (a string, default "customer")
- `Message.sender_role` field (a string, default "system" or "ai")

These are Pydantic additions to `app/models/__init__.py`. Migration: since v5 doesn't use Alembic, just update the SQLModel and add a `create_all` on startup that handles the new columns (existing rows will have NULL for the new fields, which is fine).

Also create `tools/notify_rep_deps.py` for the WhatsApp template sender stub (real implementation in Task 1.2):

```python
"""WhatsApp template sender — stub for Phase 1 step 2.

Will be replaced with a real Twilio WhatsApp template send.
For now, this is a no-op that returns None (the dry-run path covers tests).
"""
def send_whatsapp_template(to: str, from_: str, body: str, template_sid: str | None = None) -> str | None:
    """Send via Twilio WhatsApp template. Returns message SID."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info("[STUB] Would send WhatsApp template: to=%s template=%s body=%s", to, template_sid, body)
    return None
```

**Step 3: Update `dealers/example-dealer.yaml`**

Add `notification_preferences` per rep:

```yaml
sales_team:
  - name: "Mike"
    phone: "+16041234001"
    active: true
    role: "sales"
    notify_backend: "twilio_whatsapp"     # NEW: default
    notify_template_sid: "HXxxxxxxxxxxxxx"  # NEW: pre-approved template SID
  - name: "Dana"
    phone: "+16041234002"
    active: true
    role: "manager"
    notify_backend: "twilio_whatsapp"
    notify_template_sid: "HXxxxxxxxxxxxxx"
```

The pre-approved template body should be something like:
> "New lead at {{dealer_name}}: {{customer_name}} wants the {{vehicle}}. Reply 1 to claim, 2 to pass."

We'll register the template in Twilio during Task 1.2 setup.

**Step 4: Repoint `app/engine/router.py` to use `notify_rep`**

In `app/engine/router.py`, find the existing call to `send_sms` for the claim ping. Replace it with a call to `notify_rep`. The current code looks something like:

```python
# OLD: send_sms via Twilio
from tools.send_sms import send_sms
sid = send_sms(
    to_phone=rep["phone"],
    body=claim_message,
    lead_id=lead.id,
)
```

Replace with:

```python
# NEW: notify_rep via the chokepoint
from tools.notify_rep import notify_rep
result = notify_rep(
    rep_config=rep,
    lead=lead,
    message_type="claim",
    payload={"customer_name": lead.customer_name, "vehicle": vehicle_str},
    dealer_config=dealer_config,
)
if not result.success:
    logger.warning("notify_rep claim failed: %s", result.error)
```

The rep's claim/pass reply is still via SMS (the customer-facing SMS webhook). The rep can reply with "1" to claim or "2" to pass. The CLAIM body format is the same as before — rep's existing behavior unchanged.

**Step 5: Add an end-to-end test**

In `tests/test_notify_rep_e2e.py`:

```python
"""E2E: lead ingested → rep claim ping sent via notify_rep (WhatsApp) → rep claims."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Dealer, Lead, Channel, LeadState, Message, Direction
from tools.notify_rep import notify_rep


def test_e2e_lead_to_rep_claim_via_whatsapp(db_session, monkeypatch):
    """Full path: webform → auto-reply → claim ping via WhatsApp."""
    # Set up dealer with a rep that uses WhatsApp
    dealer_config = {
        "dealer": {"name": "E2E Dealer", "timezone": "America/Vancouver",
                   "hours": {"mon": "09:00-18:00"}},
        "sales_team": [
            {"name": "Mike", "phone": "+16041234001", "active": True,
             "notify_backend": "twilio_whatsapp", "notify_template_sid": "HXtest"}
        ],
    }
    dealer = Dealer(slug="e2e-dealer", name="E2E Dealer", config=dealer_config)
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    # Stub the WhatsApp send
    sent = []
    def fake_send(to, from_, body, **kwargs):
        sent.append({"to": to, "body": body, "template": kwargs.get("template_sid")})
        return "E2E_SID"
    monkeypatch.setattr("tools.notify_rep_deps.send_whatsapp_template", fake_send)

    # Ingest a lead (webform path)
    from tools.route_lead import ingest_lead
    lead = ingest_lead(
        db_session=db_session,
        dealer_slug="e2e-dealer",
        customer_name="E2E Customer",
        customer_phone="+16041234999",
        vehicle_text="2019 Honda Civic",
        source="webform",
    )
    db_session.commit()

    # The lead should have an outbound claim-ping Message row
    outbound_msgs = (
        db_session.query(Message)
        .filter(Message.lead_id == lead.id, Message.recipient_role == "rep")
        .all()
    )
    assert len(outbound_msgs) >= 1
    assert "E2E Customer" in outbound_msgs[-1].body
    assert "2019 Honda Civic" in outbound_msgs[-1].body

    # And a WhatsApp send was made to Mike
    assert len(sent) == 1
    assert sent[0]["to"] == "+16041234001"
    assert "E2E Customer" in sent[0]["body"]
```

Run: `pytest tests/test_notify_rep.py tests/test_notify_rep_e2e.py -v`
Expected: all green

Run: `pytest tests/ -v`
Expected: ALL tests pass (no regression)

**Step 6: Commit**

```bash
cd "C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5"
git add -A
git commit -m "feat: P1-1 notify_rep abstraction with Twilio WhatsApp default

Adds tools/notify_rep.py as the single chokepoint for dealer-side
notifications. Default backend is twilio_whatsapp (pre-approved template).
Fallback to sms (existing chokepoint), then email and dashboard (Phase 2).

Repoints app/engine/router.py to call notify_rep instead of send_sms
for claim pings. All notifications persist a Message row with
recipient_role='rep' for the lead detail page.

Adds Message.recipient_role and Message.sender_role fields to the model.
Updates dealers/example-dealer.yaml with notify_backend per rep.

Respects OUTBOUND_ENABLED dry-run gate (DRYRUN default, no real sends).

Tests: tests/test_notify_rep.py (unit) and tests/test_notify_rep_e2e.py
(full pipeline E2E). Both green."
```

**Step 7: Stop and report**

Report to the user:
- 5 tests added (4 unit + 1 E2E)
- `tools/notify_rep.py` created
- `tools/notify_rep_deps.py` stub created (real WhatsApp send in Task 1.2)
- `Message.recipient_role` and `Message.sender_role` fields added
- `dealers/example-dealer.yaml` updated
- `app/engine/router.py` repointed to use `notify_rep`
- Commit hash
- Test results summary

---

### Task 1.2: Real Twilio WhatsApp template send (replace the stub)

**Why:** The `tools/notify_rep_deps.send_whatsapp_template()` is currently a no-op stub. We need the real Twilio WhatsApp template call so that when `OUTBOUND_ENABLED=true`, the rep actually gets a WhatsApp message.

**Files:**
- Modify: `tools/notify_rep_deps.py` (replace stub with real Twilio call)
- Create: `tests/test_notify_rep_twilio_integration.py` (optional — integration test against Twilio sandbox)

**Step 1: Write failing test (RED)**

```python
"""Integration test: real Twilio WhatsApp send (sandbox only — DRYRUN by default)."""
import os
import pytest


@pytest.mark.skipif(
    os.environ.get("RUN_TWILIO_INTEGRATION") != "true",
    reason="integration test, opt-in via RUN_TWILIO_INTEGRATION=true"
)
def test_real_twilio_whatsapp_send():
    """Sends a real WhatsApp message to the dealer's test number.
    Requires the user to set:
    - TWILIO_ACCOUNT_SID
    - TWILIO_AUTH_TOKEN
    - TWILIO_WHATSAPP_FROM (e.g., 'whatsapp:+14155238886' for the sandbox)
    - TEST_REP_PHONE (e.g., the user's phone with whatsapp: prefix)
    """
    from tools.notify_rep_deps import send_whatsapp_template
    sid = send_whatsapp_template(
        to=os.environ["TEST_REP_PHONE"],
        from_=os.environ["TWILIO_WHATSAPP_FROM"],
        body="Test: a new lead wants the 2019 Honda Civic. Reply 1 to claim, 2 to pass.",
        template_sid=os.environ.get("TWILIO_WHATSAPP_TEMPLATE_SID"),
    )
    assert sid is not None
    assert sid.startswith("SM") or sid.startswith("MM")  # Twilio SIDs start with these
```

Run: `pytest tests/test_notify_rep_twilio_integration.py -v`
Expected: SKIPPED (the `@pytest.mark.skipif` makes it skip in normal runs)

**Step 2: Implement the real send (GREEN)**

In `tools/notify_rep_deps.py`:

```python
"""WhatsApp template sender — real Twilio integration.

Sends via Twilio's WhatsApp Business API. Requires:
- TWILIO_ACCOUNT_SID
- TWILIO_AUTH_TOKEN
- TWILIO_WHATSAPP_FROM (e.g., 'whatsapp:+14155238886')

For pre-approved templates (business-initiated), pass template_sid +
the template variables. For free-form replies within a 24h session
window, omit template_sid.
"""
from __future__ import annotations
import logging
import os

logger = logging.getLogger(__name__)


def send_whatsapp_template(
    to: str,
    from_: str,
    body: str,
    template_sid: str | None = None,
    template_variables: dict | None = None,
) -> str | None:
    """Send a WhatsApp message via Twilio.

    Args:
        to: recipient E.164 (e.g., '+16041234001' — we'll prepend 'whatsapp:')
        from_: sender (e.g., 'whatsapp:+14155238886')
        body: the message body (used if no template, or as fallback)
        template_sid: pre-approved Twilio template SID (for business-initiated)
        template_variables: dict of variables to fill into the template

    Returns:
        Twilio message SID, or None on failure (logged but not raised)
    """
    try:
        from twilio.rest import Client
        sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        if not sid or not token:
            logger.error("send_whatsapp_template: TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN not set")
            return None

        client = Client(sid, token)

        # Ensure 'whatsapp:' prefix on both ends
        to_whatsapp = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
        from_whatsapp = from_ if from_.startswith("whatsapp:") else f"whatsapp:{from_}"

        kwargs = {
            "to": to_whatsapp,
            "from_": from_whatsapp,
            "body": body,
        }
        if template_sid:
            kwargs["content_sid"] = template_sid
            if template_variables:
                # Twilio expects a JSON string of variables
                import json
                kwargs["content_variables"] = json.dumps(template_variables)
            else:
                kwargs["content_variables"] = "{}"

        message = client.messages.create(**kwargs)
        logger.info("WhatsApp sent: to=%s sid=%s", to_whatsapp, message.sid)
        return message.sid
    except Exception as e:
        logger.exception("send_whatsapp_template failed: to=%s", to)
        return None
```

**Step 3: Test it**

`pytest tests/ -v` — should still pass (no regression)

For the user's manual test (after they set `OUTBOUND_ENABLED=true`):
1. Set the Twilio sandbox: send "join <sandbox-keyword>" to `+1 415 523 8886` from your phone
2. Set `TWILIO_WHATSAPP_FROM=whatsapp:+14155238886` in `.env`
3. Set `TEST_REP_PHONE=whatsapp:+1<your-phone>` in `.env`
4. Run `RUN_TWILIO_INTEGRATION=true pytest tests/test_notify_rep_twilio_integration.py -v -s`
5. Confirm you got the WhatsApp message on your phone

**Step 4: Commit**

```bash
cd "C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5"
git add -A
git commit -m "feat: P1-2 real Twilio WhatsApp send via send_whatsapp_template

Replaces the no-op stub in tools/notify_rep_deps.py with a real Twilio
WhatsApp send. Uses Twilio's content_sid (template) for business-
initiated messages. Free-form fallback for the 24h session window.

Integration test is opt-in via RUN_TWILIO_INTEGRATION=true to prevent
accidental real sends during normal pytest runs.

User must set:
- TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN (already in .env.example)
- TWILIO_WHATSAPP_FROM (e.g., 'whatsapp:+14155238886' for sandbox)
- TEST_REP_PHONE for the integration test"
```

**Step 5: Stop and report**

Report:
- `tools/notify_rep_deps.py` replaced (stub → real Twilio call)
- 1 integration test added (opt-in only)
- Commit hash
- Reminder to user: when they want to test live, set `OUTBOUND_ENABLED=true` and the Twilio creds

---

## Phase 1, Step 2 — Outlined (deferred to next session)

**The 4 things still on the Phase 1 list:**

1. **Real Twilio WhatsApp inbound webhook** — currently `/webhook/twilio/whatsapp` exists but may not handle the full message lifecycle. Verify: rep reply "1" to claim, rep reply "2" to pass, customer-initiated WhatsApp. Land in next session.
2. **Auto-creating WhatsApp templates in Twilio** — for production, the template `HXxxxxxx` is registered in Twilio's content template builder. We need a setup script.
3. **State machine: notify on APPT_SET, ESCALATED, SOLD** — `tools/route_lead.py` and `app/engine/router.py` need to call `notify_rep` for the additional state transitions.
4. **Missed-call handoff decision rule** (owner note 4) — `/webhook/twilio/voice` needs the human-handoff logic from PIPELINE_REVIEW.md Section C3.

**Out of scope for now, but tracked:**
- P0-02 (normalize_db_url), P0-04 (tenant resolution), P0-05/06 (other critical), P0-08 (CSRF)
- Phase 1 step 3-5: email intake, quiet hours per-dealer, inventory freshness
- Phase 2 features (per PIPELINE_REVIEW.md Section G.4)

---

## Notes for the build session

- **TDD discipline:** every code change has a failing test first. The test runs and FAILS, then the implementation, then the test runs and PASSES, then commit. No "I'll add tests later."
- **DRYRUN stays on.** Real sends only when user says "enable live" and sets `OUTBOUND_ENABLED=true`.
- **Don't touch v4.** v5 is the only thing that moves in this session.
- **Don't run `uvicorn` or `pip install`.** The build session is about writing code + tests, not about running the app.
- **Stop at the end of each task.** Report results, wait for "next task."
- **If a tool call fails or a test fails for an unexpected reason:** say so honestly. Don't make up results. The user has the "figure it out" mandate — exhaust options before reporting a blocker.
- **The user's video:** this build session is being recorded. The build agent should produce clean output (no raw terminal spam), clear commit messages, and TDD-style test runs.
