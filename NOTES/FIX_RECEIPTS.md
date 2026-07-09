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


# Speed to Lead v5 — Rep Scheduling + Telegram (2026-07-09)

## Phase 0 — Baseline

**git status:** clean after calendar fix commit

### pytest baseline
```
pytest tests/ -q → 275 passed, 4 failed, 1 skipped
```

**Known date-sensitive failures (unchanged):**
1. `test_full_pipeline_e2e` — booked June 2026 date in past
2. `test_escalation_after_timeout` — same cause
3. `test_round_robin_distribution` — same cause
4. `test_book_appointment_calls_notify_rep_for_appointment_set` — same cause

---

## Calendar fix + week-view tests

**Fix:** Changed `day.items` → `day.appts` in `app/dashboard/templates/appointments.html` (line 490). Backend already used `"appts"` as the dict key; Jinja was resolving `day.items` to Python's built-in `dict.items()` method, crashing with `TypeError`.

**Tests added:** 4 new tests in `tests/test_dashboard_pages.py`:
- `test_appointments_view_list_returns_200`
- `test_appointments_view_week_returns_200` — seeds an appointment, asserts name in rendered grid
- `test_appointments_view_week_navigation` — week_offset=-1 and 1 both return 200
- `test_appointments_view_week_rep_can_access` — rep-scoped week view

`pytest tests/test_dashboard_pages.py -q` → 23 passed (including 4 new)

**Commit:**
- `570abb8` Fix calendar: day.items → day.appts + permanent week-view tests

---

## Phase 1 — Rep availability

**Changes:**
- Added `UnavailableWindow` Pydantic model to `app/config.py` (date/start/end/note with format validators)
- Added `unavailable_windows: list[UnavailableWindow]` field to `SalesRep` with default empty list
- Added `POST /dashboard/team/{rep_name}/unavailable` endpoint (manager-only, validates via Pydantic)
- Added `POST /dashboard/team/{rep_name}/unavailable/remove` endpoint (manager-only, removes by index)
- Used `flag_modified(current_dealer, "config")` for SQLite JSON column mutation tracking

**Tests (`tests/test_rep_availability.py`, 10 tests):**
- Adding a window persists in dealer config
- Malformed date/time rejected (400)
- End before start rejected (400)
- Unknown rep returns 404
- Auth required (401/303)
- Rep role redirect (manager-only)
- Remove window by index works
- YAML load validates windows correctly
- YAML load rejects bad date

`pytest tests/ -q` → 289 passed (+14), 4 failed (pre-existing)

**Commit:**
- `6b9b7b1` Phase 1: rep availability — data model, dashboard endpoints, 10 tests

---

## Phase 2 — Telegram free-text router

**Changes:**
- New module `app/telegram_free_text.py` with `handle_free_text()` entry point
- Three intents: availability (with confirmation step), new_lead (uses `ingest_lead`), no_show_reply
- LLM classification via `_get_openai_client()` (reuses conversation engine's plumbing)
- `_CONFIRMATION_CACHE` module-level dict for pending availability confirmations
- Wired into `webhook_telegram` in `app/main.py` — free-text from known reps routed to handler

**Tests (`tests/test_telegram_free_text.py`, 7 tests, all mocked):**
- Availability → confirmation reply, nothing written yet
- Confirmation → window committed to dealer.config
- Deny → window not written
- New lead → Lead row created with correct fields, assigned to submitting rep
- Garbage message → help reply, no side effects
- Unrecognized chat_id → ignored/logged
- No-show reply without active nudge → guidance message

`pytest tests/ -q` → 296 passed (+7), 4 failed (pre-existing)

**Commit:**
- `e06e443` Phase 2: Telegram free-text router — 3 intents, confirmation step, 7 tests

---

## Phase 3 — Smart booking pairing

**Changes:**
- Added `find_available_rep_for_slot()` to `app/engine/router.py` — filters active reps by:
  - Not having an unavailability window covering the time
  - Not already having an appointment at that exact time
  - Falls back to round-robin among qualifying reps
- Modified `book_appointment()` in `tools/book_appointment.py`:
  - Replaced dealer-wide slot conflict with per-rep check
  - Uses `find_available_rep_for_slot` instead of blind `assign_lead`
  - Respects already-assigned reps (checks their availability)

**Tests (`tests/test_smart_booking.py`, 4 tests):**
- One rep blocked, one free → picks the free rep
- Two customers, same time, two free reps → different reps
- All reps blocked → no rep available
- No windows → round-robin fairness preserved

`pytest tests/ -q` → 300 passed (+4), 4 failed (pre-existing)
`test_router.py` existing round-robin tests still pass unmodified

**Commit:**
- `543e562` Phase 3: smart booking pairing — per-rep slot check, find_available_rep_for_slot, 4 tests

---

## Phase 4 — No-show handling

**Changes:**
- Added `POST /dashboard/leads/{lead_id}/mark-showed` endpoint → calls `mark_showed()`
- Added `POST /dashboard/leads/{lead_id}/mark-no-show` endpoint → calls `mark_no_show()`
- Added `_run_no_show_nudge_session()` to `app/scheduler.py` — finds appointments >2h past still "set", sends Telegram nudge, records `LeadEvent(type='no_show_nudge')` to prevent double-nudge
- Wired into scheduler as 15-min interval job

**Tests (`tests/test_no_show.py`, 7 tests):**
- Dashboard mark-showed updates appointment + lead state
- Dashboard mark-no-show updates appointment status
- Scheduler nudge sends for overdue appointment
- Nudge sends exactly once (double-run test)
- No nudge for recent appointment (< 2h)
- Telegram "showed" reply marks appointment showed
- Telegram "no show" reply marks appointment no_show

`pytest tests/ -q` → 307 passed (+7), 4 failed (pre-existing)

**Commit:**
- `8610e1d` Phase 4: no-show handling — dashboard buttons, scheduler nudge, Telegram replies, 7 tests

---

## Phase 5 — Cross-system consistency

**Tests (`tests/test_cross_system.py`, 3 tests):**
- Lead created via Telegram appears on /dashboard/leads
- Availability window set via Telegram respected by `find_available_rep_for_slot`
- No-show marked via Telegram reflected on /dashboard/appointments

`pytest tests/ -q` → 310 passed (+3), 4 failed (pre-existing)

**Commit:**
- `b9cfe57` Phase 5: cross-system consistency verification tests (3)

---

## Final counts

**Baseline → Final:** 275 → 310 passed (+35 new tests), 4 failed (pre-existing, unchanged)
**New files tracked:** app/telegram_free_text.py, tests/test_rep_availability.py, tests/test_telegram_free_text.py, tests/test_smart_booking.py, tests/test_no_show.py, tests/test_cross_system.py
**Total commits this session:** 8
