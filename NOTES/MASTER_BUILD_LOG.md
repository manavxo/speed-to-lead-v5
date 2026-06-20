# Speed to Lead v5 — Master Build Log

> **Purpose:** Trace any bug or problem back to the originating phase.
> Each phase entry records: what changed, what tests were added, what the test results were.
> If something breaks later, check here first to see if a specific phase introduced it.

---

## Phase 0: Cleanup

### Task 0.1 — Remove .claude/ scaffolding
**Files changed:**
- `.gitignore` — added 7 patterns for scaffolding directories

**What happened:** Deleted `.claude/`, `.claude-flow/`, `.mcp.json`, `HTTP` (all dev-only scaffolding from previous AI agent sessions, not product code).

**Tests added:** None (regression-only — existing 128 tests must still pass)

**Result:** 128 passed, 1 skipped — clean

**Commit:** `89325ba`

---

### Task 0.2 — Remove test-mode WhatsApp handler
**Files changed:**
- `app/main.py` — deleted `_handle_customer_whatsapp_test()` (~180 lines), non-rep WhatsApp now returns empty TwiML
- `tests/test_webhook_whatsapp.py` — updated customer-initiated test to expect empty TwiML

**What happened:** The test-mode handler was ~180 lines of production-quality code (AI conversation, lead creation, Twilio send) running inside a "test" route. It duplicated the SMS handler. Deleted it. Comments said "Remove this function before deploying to real dealers."

**Tests added:** Updated `test_customer_initiated_whatsapp_returns_empty_twiml`

**Result:** 128 passed, 1 skipped

**Commit:** `0bae6bc`

---

## Phase 1: Critical Bugs

### Task 1.1 — Fix daily digest crash
**Files changed:**
- `app/scheduler.py` — added Dealer lookup by slug, `dealer.id` was undefined
- `tests/test_digest_crash.py` — NEW test file (2 tests)

**Bug:** `send_daily_digest()` referenced `dealer.id` but `dealer` was never loaded — only `dealer_slug` was passed. Would crash with `NameError`.

**Fix:** Added `session.execute(select(Dealer).where(Dealer.slug == dealer_slug))` at the top of `send_daily_digest()`.

**Tests added:**
- `test_send_daily_digest_does_not_crash` — verifies no NameError
- `test_send_daily_digest_skips_when_no_manager_phone` — verifies early return

**Result:** 130 passed, 1 skipped

**Commit:** `79c4f45`

---

### Task 1.2 — Fix lifecycle bypass (3 sites)
**Files changed:**
- `app/engine/lifecycle.py` — added `ENGAGED → ASSIGNED` to transition table
- `app/engine/conversation.py` — replaced 3 direct state assignments with `transition()`
- `tests/test_lifecycle_bypass.py` — NEW test file (4 tests)
- `tests/test_conversation.py` — updated max-turns test for new payload shape

**Bug:** Three places in conversation.py set `lead.state = LeadState.ASSIGNED` directly without using `transition()`. Bypasses state validation, LeadEvent logging, and `updated_at` tracking.

**Sites fixed:**
1. `greeting_only` mode
2. `qualify_only` handoff
3. `max_turns_reached` handoff

**Tests added:**
- `test_greeting_only_transitions_via_lifecycle` — LeadEvent exists
- `test_greeting_only_lead_event_reason` — reason="greeting_only_mode"
- `test_qualify_only_handoff_creates_lead_event` — LeadEvent after 3+ turns
- `test_max_turns_handoff_creates_lead_event` — LeadEvent after max turns

**Result:** 134 passed, 1 skipped

**Commit:** `daa6deb`

---

### Task 1.3 — Fix pass_count persistence
**Files changed:**
- `app/models/__init__.py` — explicit `Field(default=0)` for pass_count
- `app/engine/router.py` — replaced `getattr(lead, "pass_count", 0)` with `(lead.pass_count or 0)`
- `tests/test_pass_count.py` — NEW test file (3 tests)

**Bug:** `pass_count` used `getattr` fallback — defensive code from when column might not have existed. Column already persisted correctly.

**Tests added:**
- `test_pass_count_defaults_to_zero`
- `test_pass_count_increments_across_session_refresh`
- `test_pass_count_reaches_max_and_escalates`

**Result:** 137 passed, 1 skipped

**Commit:** `7ca8cfc`

---

### Tasks 1.4 + 1.5 — Fix email adapter (phone masking + consent)
**Files changed:**
- `app/adapters/intake/email_lead.py` — removed `mask_phone()`, changed `consent=False` to `True`
- `tests/test_email_adapter.py` — NEW test file (3 tests)

**Bug 1.4:** Phone was stored masked (`+160****1234`) in email lead parsing — broke dedup across channels.

**Bug 1.5:** `consent=False` for listing site leads — customer submitting their info voluntarily has implied consent under CASL.

**Tests added:**
- `test_email_adapter_phone_stored_unmasked`
- `test_email_adapter_consent_is_true`
- `test_email_adapter_parse_full_lead`

**Result:** 140 passed, 1 skipped

**Commit:** `5efad4b`

---

## Phase 2: Database & Migrations

### Task 2.1 — Install and configure Alembic
**Files created:**
- `alembic.ini`
- `alembic/env.py`
- `alembic/script.py.mako`
- `alembic/versions/` (directory)

**Configuration:** `env.py` imports `app.models` for auto-discovery, reads `DATABASE_URL` from `app.config.settings`, uses `_normalize_db_url()` from `app.db`.

---

### Task 2.2 — Create initial migration
**Files created:**
- `alembic/versions/82864cde1dc2_initial_schema.py`

**Detects:** All 7 tables (dealer, vehicle, lead, message, leadevent, appointment, consentlog) with all columns, indexes, foreign keys, and enums.

**Note:** Baseline migration. On Render (existing tables), run `alembic upgrade head` with `--fake` flag.

---

### Task 2.3 — Increase connection pool size
**Files changed:**
- `app/db.py` — `pool_size`: 2→5, `max_overflow`: 2→10

**Why:** Previous values (2+2=4 max connections) were too small for production under load, especially with background scheduler competing with web requests.

---

### Task 2.4 — Remove duplicated `_normalize_db_url`
**Files changed:**
- `app/scheduler.py` — removed duplicate 7-line function, added `from app.db import _normalize_db_url`

**Why:** Same function existed in `app/db.py` and `app/scheduler.py`. Classic copy-paste multiplication — maintenance risk if one copy diverged.

---

**Phase 2 result:** 140 passed, 1 skipped

**Commit:** `879d582`
