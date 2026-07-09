# FIX RECEIPTS — Dealer Readiness Execution

## Phase 0 — Baseline

**Date:** 2026-07-09
**Commit:** d8522a5 (HEAD)
**git status:** clean except untracked files (NOTES/, scripts/, tests/e2e/*.js/.png, etc.)

### pytest baseline
```
pytest tests/ -q → 253 passed, 4 failed, 1 skipped
```

**Known date-sensitive failures (not fixed in this spec):**
1. `test_full_pipeline_e2e` — `book_appointment` raises ValueError (June 2026 date in past)
2. `test_escalation_after_timeout` — same cause
3. `test_round_robin_distribution` — same cause
4. `test_book_appointment_calls_notify_rep_for_appointment_set` — same cause

All 4 are pre-existing and documented as such.

---

## Phase 1 — Email parser consolidation

### After Phase 1a (port cars_com + dealer_website_form + update __init__.py)
`pytest tests/ -q` → 4 failed, 253 passed, 1 skipped (unchanged)

### After Phase 1b (delete dead file + registry test)
`pytest tests/ -q` → 4 failed, 265 passed, 1 skipped (+12 tests)

**Commits:**
- `631df3a` Phase 1a: port cars_com & dealer_website_form parsers
- `08e74c4` Phase 1b: delete dead email_parsers.py, add registry test

---

## Phase 2 — poll_inbox integration test

`pytest tests/ -q` → 4 failed, 269 passed, 1 skipped (+4 tests)

**Commit:**
- `df9ecbc` Phase 2: add poll_inbox integration test with mocked IMAP (4 scenarios)

---

## Phase 3 — Dashboard login fixes

`pytest tests/ -q` → 4 failed, 269 passed, 1 skipped (no regression)

**Commits:**
- `bafe6fd` Phase 3a: filter inactive reps from api_sales_team
- `601414e` Phase 3b: reject inactive reps at login_submit
- `ec1e878` Phase 3c: fix login_page config=None crash
- `5ee6b6f` Phase 3d: log auto-provision failures at ERROR with slug and error summary
- `a2f4ca6` Phase 3e: extend e2e login dropdown repro + active-rep filtering test

---

## Phase 4 — Review, extend, and commit engine test harness

`pytest tests/ -q` → 4 failed, 269 passed, 1 skipped (no regression — harness is standalone)

**Harness run result:** 22 pass, 8 fail (see NOTES/ENGINE_TEST_REPORT_2026-07.md)

**Commits:**
- `2d054ba` Phase 4: review, extend, commit engine test harness + report

### Failures documented (not fixed — engine behavior issues):
| ID | Scenario | Issue |
|----|----------|-------|
| S9-emoji-T1 | Verbosity | 3 emojis in inventory intro (style) |
| S9-concise-T3/T4 | Verbosity | 4-5 sentences for vehicle detail (style) |
| S11-book-first | Double-booking | Date sensitivity — June 26 in past |
| S11-double-book | Double-booking | Cascaded from above |
| S12-stop | STOP opt-out | AI responds politely but lead stays ENGAGED — opt-out not routed to CASL state machine in handle_turn |
| S12-reasonable | Reasonable opt-out | Same issue — "please stop texting me" not honored |
| S13-quiet-hours | Quiet hours | mode='send' not 'quiet_hours' at 22:00 local |

---

## Phase 5 — Round-robin + escalation coverage

`pytest tests/ -q` → 4 failed, 274 passed, 1 skipped (+5 tests)

**Commit:**
- `442368d` Phase 5: round-robin + escalation coverage extensions (4 tests)

---

## Final counts

**Baseline → Final:** 253 → 274 passed (+21 new tests), 4 failed (pre-existing, unchanged)
**New files tracked:** `scripts/engine_test_harness.py` (committed from untracked)
**Total commits this session:** 11
