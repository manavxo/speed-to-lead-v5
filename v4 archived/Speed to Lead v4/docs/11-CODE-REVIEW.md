# Speed to Lead v4 — Comprehensive Code Review

**Date:** 2026-06-06
**Reviewer:** Hermes Agent (automated)
**Scope:** Full codebase — stability, scalability, security, compliance, code quality, production readiness

---

## Executive Summary

The Speed to Lead v4 codebase is well-structured with a clean architecture (intake adapters, engine, tools, dashboard). The state machine is sound, the compliance model (CASL/PIPA-BC) is thoughtfully layered, and the dry-run safety gate is excellent for staging. However, there are **6 critical issues** that would cause crashes or data loss in production, plus several high-severity problems around security, scalability, and correctness.

### Issue Count by Severity

| Severity | Count |
|----------|-------|
| CRITICAL | 6     |
| HIGH     | 8     |
| MEDIUM   | 12    |
| LOW      | 7     |
| **Total** | **33** |

---

## CRITICAL Issues

### C-01: Twilio Signature Validation Is Bypassed — Accepts Any Request

**File:** `app/main.py`, lines 147-183
**Severity:** CRITICAL
**Category:** Security

The `_validate_twilio_signature()` function is a no-op even when `require_twilio_signature=True`. It only checks if the signature header *exists*, but never actually validates it against the request body. Any attacker who knows the endpoint URLs can inject fake SMS/WhatsApp messages.

```python
# Line 177-179 — current code
# Full validation happens when the middleware provides form data.
return bool(signature)  # ← BUG: only checks header exists, not validity
```

**Fix:**
```python
def _validate_twilio_signature(request: Request) -> bool:
    if not settings.require_twilio_signature:
        return True

    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(settings.twilio_auth_token)

        url = str(request.url)
        if settings.public_base_url and settings.public_base_url.startswith("https"):
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(url)
            ext_parsed = urlparse(settings.public_base_url)
            url = urlunparse((
                ext_parsed.scheme,
                ext_parsed.netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                "",
            ))

        signature = request.headers.get("X-Twilio-Signature", "")
        if not signature:
            return False

        # Must validate against the form data
        # NOTE: This requires reading the body once and re-injecting it
        import asyncio
        body_bytes = asyncio.run(request.body())  # or pass body_bytes in
        form_data = dict(asyncio.run(request.form()))
        # Build params from form data for validation
        params = {k: v for k, v in form_data.items()}
        return validator.validate(url, params, signature)
    except Exception:
        logger.exception("Twilio signature validation error")
        return False
```

**Better approach:** Create a middleware that reads and caches the body once, then use it in the validator. The current `async` endpoint + sync validation mismatch needs architectural fixing.

---

### C-02: `_normalize_db_url` in scheduler.py Has Syntax Error — Broken Module Import

**File:** `app/scheduler.py`, line 231
**Severity:** CRITICAL
**Category:** Stability

The `_normalize_db_url` function contains malformed syntax:
```python
return url.replace("postgresql:***@\")[-1])
```
This line has mismatched parentheses and a misplaced string literal. If `build_scheduler()` or `main()` is ever called (e.g., via `python -m app.scheduler`), it will raise a `SyntaxError`. The function also appears to have a stray `build_scheduler().start()` line after the return statement.

**Fix:** Replace the function with a proper implementation:
```python
def _normalize_db_url(url: str) -> str:
    """Render gives postgresql:// but SQLAlchemy needs the psycopg3 driver prefix."""
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    if "render.com" in url and "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url = url + sep + "sslmode=require"
    return url
```
Note: The correct implementation already exists in `app/db.py` at lines 20-31. The scheduler's copy is corrupt.

---

### C-03: N+1 Query Pattern in Escalation Sweep — Will Exhaust DB Under Load

**File:** `app/scheduler.py`, lines 36-98
**Severity:** CRITICAL
**Category:** Scalability

The escalation sweep runs every 1 minute and for every dealer:
1. Loads ALL dealers (1 query)
2. For each dealer: loads ALL ASSIGNED leads (N queries)
3. For each lead: loads the MOST RECENT LeadEvent (N*M queries)

With 50 dealers and 100 assigned leads each, this is **5,001 queries per minute**.

```python
# Lines 54-59: loads ALL assigned leads per dealer
assigned_leads = session.execute(
    select(Lead).where(Lead.dealer_id == dealer.id, Lead.state == LeadState.ASSIGNED)
).scalars().all()

# Lines 63-68: loads last event PER LEAD (the N+1)
for lead in assigned_leads:
    latest_assigned_event = session.execute(
        select(LeadEvent).where(LeadEvent.lead_id == lead.id, ...)
    ).scalars().first()
```

**Fix:** Use a single query with a correlated subquery or window function:
```python
from sqlalchemy import func, and_

def _run_escalation_sweep():
    from app.db import get_session_factory
    from app.models import Dealer, Lead, LeadEvent, LeadState

    session = get_session_factory()()
    try:
        now = datetime.now(timezone.utc)

        # Single query: get all ASSIGNED leads with their dealer config
        dealers = session.execute(select(Dealer)).scalars().all()
        for dealer in dealers:
            dealer_config = dealer.config or {}
            timeout_min = dealer_config.get("routing", {}).get("claim_timeout_min", 5)
            cutoff = now - timedelta(minutes=timeout_min)

            # Use a single query with a subquery for the latest event
            latest_event_sq = (
                select(
                    LeadEvent.lead_id,
                    func.max(LeadEvent.created_at).label("max_time")
                )
                .where(LeadEvent.type == "state_change")
                .group_by(LeadEvent.lead_id)
                .subquery()
            )

            # Get leads that are ASSIGNED and timed out
            timed_out = session.execute(
                select(Lead, LeadEvent)
                .join(latest_event_sq, latest_event_sq.c.lead_id == Lead.id)
                .join(
                    LeadEvent,
                    and_(
                        LeadEvent.lead_id == latest_event_sq.c.lead_id,
                        LeadEvent.created_at == latest_event_sq.c.max_time,
                    ),
                )
                .where(
                    Lead.dealer_id == dealer.id,
                    Lead.state == LeadState.ASSIGNED,
                    latest_event_sq.c.max_time < cutoff,
                )
            ).all()

            for lead, event in timed_out:
                payload = event.payload or {}
                if payload.get("to") == "ASSIGNED":
                    # ... escalation logic
                    pass
    finally:
        session.close()
```

---

### C-04: Database Sessions Never Closed on Error Paths — Connection Leak

**File:** `app/main.py`, lines 58-61 + multiple webhooks
**Severity:** CRITICAL
**Category:** Stability / Scalability

`_get_session()` returns a raw session that callers must close manually. In the webhook routes, sessions are properly closed in `finally` blocks. However, the helper functions `_find_dealer_by_token`, `_find_dealer_by_sms`, `_find_dealer_by_whatsapp` each call `_exec(session, select(Dealer)).all()` on the legacy fallback path (lines 76, 99, 123), which loads ALL dealers into memory. More critically, `_get_session()` is also called in `readyz()` (line 206) where it's properly closed, but the pattern is fragile.

The bigger issue: `_get_session()` is NOT a FastAPI dependency (no `yield`), so it's not managed by the framework. If an exception occurs between `_get_session()` and the `finally` block, the session leaks.

**Fix:** Convert to a proper FastAPI dependency:
```python
# In app/db.py (already exists at line 58-65):
def get_session() -> Generator[Session, None, None]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()

# In app/main.py, use Depends:
from app.db import get_session

@app.post("/webhook/form/{token}")
async def webhook_form(token: str, request: Request, session: Session = Depends(get_session)):
    # ... session is auto-closed by FastAPI
```

---

### C-05: Legacy Fallback Scans ALL Dealers on Every Webhook — O(n) Full Table Scan

**File:** `app/main.py`, lines 76, 99, 123
**Severity:** CRITICAL
**Category:** Scalability

When a dealer's indexed column lookup fails (e.g., `web_form_token` not in the indexed column), the fallback loads ALL dealers from the database and iterates through their JSON config. This is O(n) per webhook call and will become a bottleneck as the number of dealers grows.

```python
# Line 76 — legacy fallback
dealers = _exec(session, select(Dealer)).all()  # Loads EVERY dealer
for d in dealers:
    config = d.config or {}
    channels = config.get("channels", {})
    if channels.get("web_form_token") == token:
        return d
```

**Fix:** Remove the legacy fallback after migrating all dealers to have indexed columns. If legacy support is still needed, add a JSONB index:
```sql
CREATE INDEX idx_dealer_config_web_token
ON dealer USING btree ((config->'channels'->>'web_form_token'));
```

Or in the code, at minimum log a warning and skip the fallback in production:
```python
def _find_dealer_by_token(session: Session, token: str) -> Dealer | None:
    dealer = _exec(session,
        select(Dealer).where(Dealer.web_form_token == token)
    ).first()
    if dealer:
        return dealer
    if settings.environment == "production":
        logger.error("No dealer found for token=%s (legacy fallback disabled in prod)", token)
        return None
    # Legacy fallback only in dev/staging
    # ... existing scan
```

---

### C-06: OpenAI Client Created Per-Request — Memory Leak + Connection Churn

**File:** `app/engine/conversation.py`, lines 303-308
**Severity:** CRITICAL
**Category:** Stability / Scalability

Every conversation turn creates a new `OpenAI()` client instance. The OpenAI client maintains an HTTP connection pool. Creating it per-request means:
- Connection pool is never reused
- Each client holds internal state that's never cleaned up
- Under load, this will leak memory and exhaust file descriptors

```python
# Lines 303-308 — called on EVERY conversation turn
client = OpenAI(
    base_url=settings.openrouter_base_url,
    api_key=settings.openrouter_api_key,
)
```

**Fix:** Create the client once at module level (lazy singleton):
```python
_openai_client = None

def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
        )
    return _openai_client

# Then in _call_openrouter:
client = _get_openai_client()
```

---

## HIGH Issues

### H-01: Dashboard Auth Uses Plaintext Cookie — Easily Forgeable

**File:** `app/dashboard/__init__.py`, lines 391-425
**Severity:** HIGH
**Category:** Security

The dashboard authentication sets a cookie with the literal string `"authenticated"`. Anyone who knows this can set `session=authenticated` and bypass authentication entirely.

```python
# Line 418
response.set_cookie("session", "authenticated", httponly=True, max_age=86400)

# Line 394 — check
if session != "authenticated":
```

**Fix:** Use a signed session token:
```python
import hashlib, hmac, time

SECRET = settings.twilio_auth_token  # or a dedicated secret

def _create_session_token(username: str) -> str:
    ts = str(int(time.time()))
    sig = hmac.new(SECRET.encode(), f"{username}:{ts}".encode(), hashlib.sha256).hexdigest()
    return f"{username}:{ts}:{sig}"

def _validate_session_token(token: str) -> bool:
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return False
        username, ts, sig = parts
        expected = hmac.new(SECRET.encode(), f"{username}:{ts}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        # Check expiry (24 hours)
        if time.time() - int(ts) > 86400:
            return False
        return True
    except Exception:
        return False
```

---

### H-02: Dashboard Has No CSRF Protection on Login Form

**File:** `app/dashboard/__init__.py`, lines 410-425
**Severity:** HIGH
**Category:** Security

The POST `/dashboard/login` endpoint has no CSRF token. An attacker can create a form on another site that submits login credentials, potentially setting the auth cookie on the user's browser.

**Fix:** Add CSRF middleware or token validation:
```python
from fastapi_csrf_protect import CsrfProtect

# Or manually: generate a token in the GET handler, validate in the POST
```

---

### H-03: `readyz` Returns 200 Even on DB Failure

**File:** `app/main.py`, lines 203-214
**Severity:** HIGH
**Category:** Production Readiness

The readiness probe returns HTTP 200 with `{"ok": false}` when the DB is down. Kubernetes/Render will think the service is healthy and continue routing traffic to it.

```python
# Line 212 — returns 200 even when DB is down
return {"ok": False, "error": str(exc)}
```

**Fix:**
```python
@app.get("/readyz")
def readyz() -> dict:
    session = _get_session()
    try:
        session.execute(select(1))
        return {"ok": True, "db": "connected"}
    except Exception as exc:
        logger.exception("readyz failed")
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": str(exc)},
        )
    finally:
        session.close()
```

---

### H-04: `_twiml` Allows XSS via Unsanitized Body

**File:** `app/main.py`, line 135
**Severity:** HIGH
**Category:** Security

The `_twiml` function injects `body` directly into an XML response without escaping. If the body contains XML special characters (`<`, `>`, `&`), this produces malformed XML or allows XML injection.

```python
def _twiml(body: str) -> PlainTextResponse:
    twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{body}</Message></Response>'
```

**Fix:**
```python
import html

def _twiml(body: str) -> PlainTextResponse:
    safe_body = html.escape(body, quote=True)
    twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{safe_body}</Message></Response>'
    return PlainTextResponse(twiml, media_type="application/xml")
```

---

### H-05: Conversation Context Lost — Single-Turn Only

**File:** `app/engine/conversation.py`, lines 310-313
**Severity:** HIGH
**Category:** Code Quality / Correctness

The conversation engine only sends the system prompt and the latest user message to the LLM. It does not load or send conversation history. This means the AI has no memory of previous turns in the conversation, making multi-turn qualification impossible.

```python
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": user_message},  # Only the latest message!
]
```

**Fix:** Load conversation history from the Message table:
```python
def _call_openrouter(...):
    # Load conversation history
    history = session.execute(
        select(Message)
        .where(Message.lead_id == lead.id)
        .order_by(Message.created_at.asc())
        .limit(20)  # Last 20 messages
    ).scalars().all()

    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        role = "user" if msg.direction == Direction.INBOUND else "assistant"
        messages.append({"role": role, "content": msg.body})
    messages.append({"role": "user", "content": user_message})

    # ... rest of the function
```

---

### H-06: Scheduler `_handle_followup` Is a No-Op

**File:** `app/scheduler.py`, lines 115-131
**Severity:** HIGH
**Category:** Correctness

The follow-up handler logs that a follow-up is scheduled but never actually sends a message. Cold leads will never get follow-up texts.

```python
def _handle_followup(lead_id, dealer_slug, minutes):
    lead = session.execute(select(Lead).where(Lead.id == lead_id)).scalar()
    if lead and lead.state not in (LeadState.SOLD, LeadState.LOST, LeadState.OPTED_OUT):
        # TODO: Send follow-up message via Twilio  ← NEVER EXECUTED
        logger.info("Lead %s is in state %s - follow-up scheduled", lead_id, lead.state)
```

**Fix:** Implement the follow-up message sending:
```python
def _handle_followup(lead_id: int, dealer_slug: str, minutes: int):
    session = get_session_factory()()
    try:
        lead = session.execute(select(Lead).where(Lead.id == lead_id)).scalar()
        if not lead or lead.state in (LeadState.SOLD, LeadState.LOST, LeadState.OPTED_OUT):
            return

        from app.models import Dealer
        dealer = session.execute(select(Dealer).where(Dealer.slug == dealer_slug)).scalar()
        if not dealer:
            return

        dealer_config = dealer.config or {}
        sms_number = dealer_config.get("channels", {}).get("sms_number", "")
        if not lead.phone or not sms_number:
            return

        followup_text = f"Hi {lead.name or 'there'}! Just checking in — are you still interested?"
        from tools.send_sms import send_sms
        send_sms(session, to=lead.phone, body=followup_text,
                 from_number=sms_number, dealer_slug=dealer_slug,
                 dealer_config=dealer_config, lead=lead)
    except Exception:
        logger.exception("Follow-up failed for lead %s", lead_id)
    finally:
        session.close()
```

---

### H-07: `datetime.utcnow()` Is Deprecated — Mixed Timezone Handling

**File:** `app/scheduler.py`, line 107
**Severity:** HIGH
**Category:** Code Quality / Correctness

```python
run_date=datetime.utcnow() + timedelta(minutes=minutes),
```

`datetime.utcnow()` returns a naive datetime (no timezone info) and is deprecated in Python 3.12+. Other parts of the code use `datetime.now(timezone.utc)`, creating inconsistency. Comparing naive and aware datetimes will raise `TypeError`.

**Fix:**
```python
run_date=datetime.now(timezone.utc) + timedelta(minutes=minutes),
```

---

### H-08: `check_inventory.search` Uses User Input in ILIKE Without Escaping

**File:** `tools/check_inventory.py`, lines 65, 98, 101, 104
**Severity:** HIGH
**Category:** Security (SQL Injection via LIKE wildcards)

User-supplied `query`, `body`, and `make` parameters are directly interpolated into `ILIKE` patterns without escaping `%` and `_` wildcards:

```python
pattern = f"%{query}%"
stmt = stmt.where(Vehicle.make.ilike(pattern))
```

An attacker sending `query=%` would match everything. While not a full SQL injection (SQLAlchemy parameterizes), the `%` and `_` wildcards in LIKE patterns are not escaped, allowing unintended broad matches.

**Fix:**
```python
def _escape_like(value: str) -> str:
    """Escape LIKE wildcards in user input."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

# Then in search():
if query:
    pattern = f"%{_escape_like(query)}%"
    stmt = stmt.where(
        or_(
            Vehicle.make.ilike(pattern, escape="\\"),
            Vehicle.model.ilike(pattern, escape="\\"),
            Vehicle.trim.ilike(pattern, escape="\\"),
            Vehicle.body.ilike(pattern, escape="\\"),
        )
    )
```

---

## MEDIUM Issues

### M-01: No Transaction Isolation for Multi-Step Lead Ingestion

**File:** `tools/route_lead.py`, lines 47-174
**Severity:** MEDIUM
**Category:** Stability

`ingest_lead()` performs multiple `session.commit()` calls (lead creation at line 110, consent log at line 126, auto-reply transition at line 130-131). If the process crashes between commits, the database will be left in an inconsistent state (e.g., lead created but never transitioned from NEW).

**Fix:** Use a single transaction or nested savepoints:
```python
def ingest_lead(session, dealer, lead_data, **kwargs):
    # ... all operations without intermediate commits ...
    # Single commit at the end, or use savepoints:
    try:
        session.begin_nested()
        # ... all operations ...
        session.commit()
    except Exception:
        session.rollback()
        raise
```

---

### M-02: Dashboard Loads ALL Messages for Response Metrics

**File:** `app/dashboard/__init__.py`, lines 286-288
**Severity:** MEDIUM
**Category:** Scalability

```python
all_messages = session.execute(
    select(Message).order_by(Message.created_at.asc())
).scalars().all()
```

This loads EVERY message in the database into memory. With 100k messages, this will OOM the process.

**Fix:** Use SQL aggregation:
```python
from sqlalchemy import func

# Compute response times in SQL
subq = session.execute(
    select(
        Message.lead_id,
        func.min(case(
            (Message.direction == Direction.OUTBOUND, Message.created_at),
        )).label("first_outbound"),
        func.min(case(
            (Message.direction == Direction.INBOUND, Message.created_at),
        )).label("first_inbound"),
    )
    .group_by(Message.lead_id)
).all()
```

---

### M-03: Dashboard Stats Page Loads ALL Leads Without Pagination

**File:** `app/dashboard/__init__.py`, lines 557-559
**Severity:** MEDIUM
**Category:** Scalability

```python
leads = session.execute(
    select(Lead).order_by(Lead.created_at.desc())
).scalars().all()
```

No `limit()` — loads every lead in the system. Same pattern at lines 634-636 (team page).

**Fix:** Add pagination or limit:
```python
leads = session.execute(
    select(Lead).order_by(Lead.created_at.desc()).limit(500)
).scalars().all()
```

---

### M-04: No Rate Limiting on Webhook Endpoints

**File:** `app/main.py`, all webhook routes
**Severity:** MEDIUM
**Category:** Security

There's no rate limiting on any webhook endpoint. An attacker can flood the endpoints, causing database exhaustion and Twilio cost overruns.

**Fix:** Add rate limiting middleware:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/webhook/twilio/sms")
@limiter.limit("100/minute")
async def webhook_twilio_sms(request: Request):
    # ...
```

---

### M-05: `dashboard_password` Defaults to Empty String

**File:** `app/config.py`, line 46
**Severity:** MEDIUM
**Category:** Security

```python
dashboard_password: str = ""
```

If `DASHBOARD_PASSWORD` is not set, the dashboard login accepts an empty password. The `require_auth` check at line 391-398 also only checks for cookie value `"authenticated"`, which is set on successful login.

**Fix:**
```python
dashboard_password: str = Field(..., min_length=8)  # Required, minimum 8 chars
# Or at minimum:
@field_validator("dashboard_password")
@classmethod
def _validate_password(cls, v):
    if not v or len(v) < 8:
        raise ValueError("Dashboard password must be at least 8 characters")
    return v
```

---

### M-06: Phone Number Masking Applied Before Storage — Deduplication Will Fail

**File:** `app/adapters/intake/__init__.py`, line 41-56 + `app/adapters/intake/webform.py`, line 37
**Severity:** MEDIUM
**Category:** Correctness

`mask_phone()` is called in the webform adapter before the phone is stored as the lead's phone number. This means leads are stored with masked phones like `+160****1234`, making deduplication in `route_lead.py` (line 79) compare masked values. Two leads from the same number will have the same masked value (which is good), but Twilio SMS auto-replies will be sent to the MASKED number, which will fail.

```python
# webform.py line 37
phone = mask_phone(_normalize_phone(payload.get("phone")))  # ← stores masked
```

**Fix:** Store the unmasked phone for the lead record, only mask for logging:
```python
phone = _normalize_phone(payload.get("phone"))
# Use mask_phone() only when logging or displaying
```

---

### M-07: `_is_opted_out` Only Checks ConsentLog — Doesn't Check Lead State

**File:** `tools/send_sms.py`, lines 34-44
**Severity:** MEDIUM
**Category:** Correctness

The opt-out check only looks for a `ConsentLog` entry with `action="opted_out"`. It doesn't check if the lead is in `OPTED_OUT` state. If the ConsentLog write failed but the state transition succeeded (or vice versa), messages could still be sent to opted-out contacts.

**Fix:**
```python
def _is_opted_out(session: Session, phone: str, lead: Lead | None = None) -> bool:
    # Check lead state first (faster)
    if lead and lead.state == LeadState.OPTED_OUT:
        return True
    # Then check consent log
    result = session.execute(
        select(ConsentLog).where(
            ConsentLog.phone == phone,
            ConsentLog.action == "opted_out",
        )
    ).scalars().first()
    return result is not None
```

---

### M-08: Background Scheduler Uses `BackgroundScheduler` — Not Async-Safe

**File:** `app/main.py`, line 37
**Severity:** MEDIUM
**Category:** Stability

`BackgroundScheduler` spawns threads, but the FastAPI app is async. The scheduler jobs call synchronous SQLAlchemy code in threads, which is fine, but the `BackgroundScheduler` doesn't integrate with the async event loop. If a job takes too long, it can block the GIL.

**Fix:** Use `AsyncIOScheduler` or run the scheduler in a separate process:
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
```
Or keep `BackgroundScheduler` but ensure all job functions are quick.

---

### M-09: No Input Validation on Webhook Form Payload

**File:** `app/main.py`, lines 220-249
**Severity:** MEDIUM
**Category:** Security / Stability

The form webhook accepts arbitrary JSON and passes it directly to `WebFormAdapter().parse()`. There's no size limit, no schema validation at the endpoint level, and no sanitization of the `token` path parameter.

```python
@app.post("/webhook/form/{token}")
async def webhook_form(token: str, request: Request):
    payload = await request.json()  # No size limit!
```

**Fix:**
```python
from fastapi import HTTPException
import re

@app.post("/webhook/form/{token}")
async def webhook_form(token: str, request: Request):
    # Validate token format
    if not re.match(r'^[a-zA-Z0-9_-]{8,64}$', token):
        raise HTTPException(status_code=400, detail="Invalid token format")

    # Limit body size
    body = await request.body()
    if len(body) > 10_000:  # 10KB max
        raise HTTPException(status_code=413, detail="Payload too large")

    payload = await request.json()
    # ...
```

---

### M-10: Escalation Re-assigns to Same Rep After Timeout

**File:** `app/engine/escalation.py`, lines 57-64
**Severity:** MEDIUM
**Category:** Correctness

When escalation fires, it calls `assign_lead()` which uses the round-robin pointer. But if there's only one active rep, or if the pointer wraps around, the same rep gets reassigned. There's no tracking of which reps have already been pinged.

**Fix:** Track pinged reps in the lead's metadata and skip them:
```python
# In assign_lead:
already_pinged = lead.assigned_rep  # The rep who didn't claim
# Skip to next rep if possible
if rep["name"] == already_pinged and len(active) > 1:
    rep = next_rep(dealer, sales_team)  # Advance once more
```

---

### M-11: `webhook_form` Returns 200 on Error

**File:** `app/main.py`, lines 245-247
**Severity:** MEDIUM
**Category:** Correctness

```python
except Exception as exc:
    logger.exception("webhook_form error")
    return {"error": str(exc)}  # ← Returns 200 with error dict
```

The webhook caller (the dealer's website) won't know the request failed.

**Fix:**
```python
except Exception as exc:
    logger.exception("webhook_form error")
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=500, content={"error": str(exc)})
```

---

### M-12: Scheduler `_normalize_db_url` Would Crash — But Dead Code

**File:** `app/scheduler.py`, lines 228-231
**Severity:** MEDIUM
**Category:** Code Quality

The `_normalize_db_url` function in `scheduler.py` is broken (see C-02), but it's only called by `build_scheduler()` which is only called from `main()` (standalone mode). The FastAPI lifespan uses `register_jobs()` instead, which doesn't call `build_scheduler()`. So the broken code is dead code in production, but would crash if anyone tries `python -m app.scheduler`.

---

## LOW Issues

### L-01: Duplicate `_normalize_phone` Functions

**Files:** `app/adapters/intake/webform.py` (line 11), `app/adapters/intake/twilio_sms.py` (line 11)
**Severity:** LOW
**Category:** Code Quality

Both files define identical `_normalize_phone()` functions. This should be in the shared `__init__.py`.

**Fix:** Move to `app/adapters/intake/__init__.py` and import from there.

---

### L-02: Duplicate `_exec` Helper Functions

**Files:** `app/main.py` (line 54), `tools/route_lead.py` (line 24), `tools/check_inventory.py` (line 16)
**Severity:** LOW
**Category:** Code Quality

Three files define the same `_exec(session, stmt)` helper. Extract to a shared utility.

---

### L-03: `get_attention_items` and `appointments_page` Do N+1 Queries for Leads

**File:** `app/dashboard/__init__.py`, lines 100, 117, 693
**Severity:** LOW
**Category:** Scalability

After loading appointments or messages, the code calls `session.get(Lead, appt.lead_id)` individually to get the associated lead. This should use a JOIN or eager loading.

---

### L-04: `_dryrun_counter` Is Not Thread-Safe

**File:** `tools/send_sms.py`, lines 25-31
**Severity:** LOW
**Category:** Stability

```python
_dryrun_counter = 0

def _next_dryrun_sid() -> str:
    global _dryrun_counter
    _dryrun_counter += 1
```

If multiple threads call this simultaneously (via the scheduler), the counter could have race conditions.

**Fix:** Use `itertools.count()` or `threading.Lock`.

---

### L-05: No Logging Configuration

**File:** `app/main.py` (no `logging.basicConfig` or handler setup)
**Severity:** LOW
**Category:** Production Readiness

The app creates loggers but never configures handlers. In production, log output depends on the deployment environment's default logging. JSON structured logging would be better for log aggregation.

**Fix:** Add logging configuration in the lifespan:
```python
import logging
import sys

@app.on_event("startup")  # or in lifespan
async def configure_logging():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}'
    ))
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)
```

---

### L-06: `Dashboard` Settings Page Only Shows First Dealer

**File:** `app/dashboard/__init__.py`, lines 737
**Severity:** LOW
**Category:** Code Quality

```python
dealer = session.execute(select(Dealer).limit(1)).scalars().first()
```

In a multi-tenant system, this always shows the first dealer's settings. There should be a dealer selector.

---

### L-07: `start.sh` Uses `exec` + `&` — PID Tracking Issue

**File:** `start.sh`, lines 26-33
**Severity:** LOW
**Category:** Production Readiness

```bash
exec uvicorn app.main:app ... &
UVICORN_PID=$!
```

`exec` replaces the current shell process, so the `&` background operator and subsequent `UVICORN_PID=$!` never execute. The `cleanup` trap will never fire.

**Fix:**
```bash
uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "$WEB_PORT" \
    --workers 1 \
    --log-level info \
    --proxy-headers \
    --forwarded-allow-ips '*' &
UVICORN_PID=$!

wait "$UVICORN_PID"
```

---

## Compliance Notes (CASL + PIPA-BC)

### What's Done Well:
1. **ConsentLog table** — proper audit trail for consent grants and opt-outs
2. **STOP keyword handling** — automatic opt-out on STOP/STOPALL/UNSUBSCRIBE/ARRET
3. **`mask_phone()` function** — PIPA-BC phone masking for logs
4. **Quiet hours enforcement** — respects dealer-configured quiet hours
5. **Opt-out check before sending** — `_is_opted_out()` in `send_sms.py`
6. **Consent text in auto-reply** — includes opt-out instructions

### What's Missing:
1. **No START/resubscribe handler** — The auto-reply says "Reply START to resubscribe" but there's no handler for START messages in the SMS webhook
2. **Consent not required for SMS leads** — `TwilioSmsAdapter` sets `consent=False` but the lead still gets auto-replied to. CASL allows this for "existing business relationships" but the code doesn't track relationship status
3. **No consent expiry** — CASL consent should be refreshed periodically; there's no expiry mechanism
4. **Phone masking applied before storage** (see M-06) — masks the phone for the lead record, which could cause issues with consent lookups

---

## Deployment Issues

### D-01: Render Free Tier Sleeps After 15 Minutes

**File:** `render.yaml`, line 16
**Severity:** MEDIUM
**Category:** Production Readiness

```yaml
plan: free  # Free tier (sleeps after 15 min)
```

With the free tier, the app will sleep after 15 minutes of inactivity. The escalation sweep runs every 1 minute, so leads could wait up to 16+ minutes for escalation if the app was sleeping. The background scheduler only runs when the app is awake.

**Fix:** Upgrade to "starter" plan ($7/month) for always-on, or use an external cron service to keep the app warm.

### D-02: Single Worker Limitation

**File:** `start.sh`, line 29
**Severity:** MEDIUM
**Category:** Scalability

```bash
--workers 1  # REQUIRED because the scheduler runs in-process
```

The app is limited to a single worker because the APScheduler runs in-process. This means the app can only handle one concurrent request at a time (though async endpoints are non-blocking). For high-traffic scenarios, the scheduler should be extracted to a separate process.

---

## Summary of Recommended Fixes (Priority Order)

1. **C-01**: Fix Twilio signature validation (security)
2. **C-02**: Fix broken `_normalize_db_url` in scheduler.py
3. **C-03**: Fix N+1 query pattern in escalation sweep
4. **C-04**: Convert to FastAPI dependency injection for DB sessions
5. **C-05**: Remove or gate legacy dealer fallback scans
6. **C-06**: Create OpenAI client as singleton
7. **H-01**: Implement signed session tokens for dashboard
8. **H-03**: Fix readyz to return 503 on DB failure
9. **H-04**: XML-escape TwiML responses
10. **H-05**: Add conversation history to LLM calls
11. **H-06**: Implement follow-up message sending
12. **M-01**: Use single transaction for lead ingestion
13. **M-02**: Fix response metrics to use SQL aggregation
14. **L-07**: Fix `start.sh` `exec` + `&` bug
