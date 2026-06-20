# Phase 0: Cleanup

## Task 0.1: Remove AI agent scaffolding ✅

**What was done:**
- Deleted `.claude/` — AI agent swarm coordination, agent configs, SPARC methodology files (~25 files)
- Deleted `.claude-flow/` — swarm metrics, audit logs, config (~7 files)
- Deleted `.mcp.json` — MCP server config for Claude Flow ruflo
- Deleted `HTTP` — empty file (0 bytes)
- Updated `.gitignore` with scaffolding patterns so they can't be re-introduced

**Why:**
These were dev-only scaffolding added by previous AI agent sessions. Not product code. Shipping them would be production drift.

**Verification:**
- `pytest tests/ -x --tb=short` → 128 passed, 1 skipped (same as baseline, no regressions)
- `git status` shows no scaffolding files remaining
- `.gitignore` now blocks: `.claude/`, `.claude-flow/`, `.mcp.json`, `HTTP`, `.mimocode/`, `MIMO_CONTEXT_PASTE.txt`, `MIMO_HANDOFF.md`

**Files changed:**
- `.gitignore` — added 7 new patterns for scaffolding

## Task 0.2: Remove test-mode WhatsApp handler ✅

**What was done:**
- Deleted the entire `_handle_customer_whatsap_test()` function (~180 lines) from `app/main.py`
- Updated the `webhook_twilio_whatsapp` route: non-rep WhatsApp now returns empty TwiML (no-op) instead of routing to conversation engine
- Updated the docstring to reflect new behavior
- Renamed test `test_customer_initiated_whatsapp_unknown_rep` → `test_customer_initiated_whatsapp_returns_empty_twiml` with updated docstring

**Why:**
This was ~180 lines of production-quality code (AI conversation, lead creation, Twilio send) running inside a "test mode" handler. It duplicated logic from the SMS handler. The comments explicitly said "Remove this function before deploying to real dealers." Production deployments should not include test-only code paths.

**What was the test handler doing before removal?**
- Checking STOP/START opt-out keywords
- Finding existing leads by phone (with masked-phone fallback)
- Logging inbound messages
- Transitioning AUTO_REPLIED → ENGAGED
- Handling AI conversation turn
- Creating new leads via `ingest_lead()`
- Sending WhatsApp replies via Twilio
All of this duplicated the SMS handler. Customers should use SMS, not WhatsApp.

**Verification:**
- WhatsApp webhook tests: 9 passed (same as before)
- Full test suite: 128 passed, 1 skipped (no regressions)
- Test `test_customer_initiated_whatsapp_returns_empty_twiml` verifies non-rep WhatsApp gets empty TwiML

**Files changed:**
- `app/main.py` — deleted `_handle_customer_whatsap_test()` (-180 lines), updated webhook handler
- `tests/test_webhook_whatsapp.py` — renamed/updated customer WhatsApp test

**Commit:** `0bae6bc Phase 0.2: Remove test-mode WhatsApp handler from app/main.py`

## Task 0.3: Next in Phase 0 🔲

No more cleanup tasks planned. Phase 0 is complete.

## What's next: Phase 1 — Critical Bugs

1. **1.1 Fix daily digest crash** (CRITICAL — undefined `dealer` var in `app/scheduler.py`)
2. **1.2 Fix greeting_only lifecycle bypass** (direct state assignment instead of `transition()`)
3. **1.3 Fix pass_count persistence** (runtime attribute, not DB column)
4. **1.4 Fix phone masking in email adapter**
5. **1.5 Fix consent=False in email adapter**

