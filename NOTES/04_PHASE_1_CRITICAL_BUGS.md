# Phase 1: Critical Bugs

## Task 1.1: Fix daily digest crash ✅

**Bug:** `send_daily_digest()` in `app/scheduler.py` referenced `dealer.id` at line ~422, but `dealer` was never defined — only `dealer_slug` was passed. Would crash with `NameError` when the job runs.

**Root cause:** The function received `dealer_slug` (a string) and `dealer_config` (a dict), but the line `Lead.dealer_id == dealer.id` expected a Dealer ORM object. The `dealer` variable existed in the caller (`_run_daily_digest_for_all_dealers_session` loop at line 343), but wasn't available inside `send_daily_digest`.

**Fix:** Added a Dealer lookup by slug at the top of `send_daily_digest()`:
```python
dealer = session.execute(
    select(Dealer).where(Dealer.slug == dealer_slug)
).scalars().first()
if dealer is None:
    logger.warning("No dealer found for slug %s — skipping digest", dealer_slug)
    return
```

**Verification:**
- RED test (`test_send_daily_digest_does_not_crash`) confirmed crash with `xfail`
- After fix: 2 new tests pass
- Full suite: 130 passed, 1 skipped (no regressions)

**Files changed:**
- `app/scheduler.py` — added Dealer import + slug lookup (+10 lines)
- `tests/test_digest_crash.py` — new test file (2 tests)

**Commit:** `79c4f45 Phase 1.1: Fix daily digest crash — undefined dealer variable`

## Task 1.2: Fix greeting_only lifecycle bypass ✅

**Bug:** Three places in `app/engine/conversation.py` set `lead.state = LeadState.ASSIGNED` directly without using `transition()`. This bypasses state validation, LeadEvent logging, and `updated_at` tracking.

**Affected locations:**
1. **Line 592** — `greeting_only` mode (AUTO_REPLIED → ASSIGNED)
2. **Line 627** — `qualify_only` mode handoff (ENGAGED → ASSIGNED)
3. **Line 715** — `max_turns_reached` handoff (ENGAGED → ASSIGNED)

**Root cause:** The original code manually created a `LeadEvent` with custom types like `"engagement_handoff"` and `"max_turns_reached"`, but the state change itself bypassed the lifecycle module. This is the "interface drift" pattern from the Zero-Rework Doctrine.

**Fix:**
- `app/engine/lifecycle.py` — Added `ENGAGED → ASSIGNED` to the allowed transitions table (was missing, needed for qualify_only and max-turns handoffs)
- `app/engine/conversation.py` — Replaced all 3 direct assignments with `transition()` calls:
  - `greeting_only`: `reason="greeting_only_mode"`, meta includes `inbound_count`
  - `qualify_only`: `reason="qualify_only_handoff"`, meta includes `inbound_count`
  - `max_turns_reached`: `reason="max_turns_reached"`, meta includes `inbound_count`
- Removed manual `LeadEvent` creation and `session.commit()` — `transition()` handles both

**Test impact:** Existing `test_max_turns_triggers_handoff` needed updating since the LeadEvent type changed from `max_turns_reached` to `state_change` (with reason in payload).

**Verification:**
- 4 new tests in `tests/test_lifecycle_bypass.py`:
  - `test_greeting_only_transitions_via_lifecycle` — LeadEvent exists after greeting only
  - `test_greeting_only_lead_event_reason` — reason includes "greeting"
  - `test_qualify_only_handoff_creates_lead_event` — LeadEvent after 3+ turns
  - `test_max_turns_handoff_creates_lead_event` — LeadEvent after max turns
- Existing `test_max_turns_triggers_handoff` updated for new payload shape
- Full suite: 134 passed, 1 skipped (no regressions)

**Files changed:**
- `app/engine/lifecycle.py` — added ENGAGED→ASSIGNED transition
- `app/engine/conversation.py` — replaced 3 direct assignments with transition()
- `tests/test_lifecycle_bypass.py` — new test file (4 tests)
- `tests/test_conversation.py` — updated existing max-turns test

**Commit:** `daa6deb Phase 1.2: Fix lifecycle bypass — greeting_only, qualify_only, max_turns`

## Task 1.3: Fix pass_count persistence 🔲

**Not started.** Next up.

## Task 1.4: Fix phone masking in email adapter 🔲

## Task 1.5: Fix consent=False in email adapter 🔲
