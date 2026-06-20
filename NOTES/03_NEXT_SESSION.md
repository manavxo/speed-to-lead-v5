# Where to Resume Next

## Current Phase: Phase 1 — Critical Bugs

**Just completed:** Phase 0 (cleanup)
- Task 0.1: Removed .claude scaffolding ✅
- Task 0.2: Removed test-mode WhatsApp handler ✅

**Next up:** Task 1.1 — Fix daily digest crash (CRITICAL)

The `send_daily_digest()` function in `app/scheduler.py` references an undefined `dealer` variable. Will crash when the job runs. This is the #1 priority because it will hit production.

**After 1.1:** Task 1.2 → 1.3 → 1.4 → 1.5 (in order)

## Execution contract reminder

Before every phase:
1. Read REFACTORING_GUIDE.md to confirm current phase
2. Run full test suite — all must pass before touching code
3. Write RED test first → confirm it FAILS
4. Implement fix
5. Confirm GREEN
6. Run full suite → no regressions
7. Commit: `git commit -m "Phase X.Y: description"`

## Key decisions (non-negotiable)

- Telegram = ONLY dealer notification channel. No WhatsApp for dealers.
- Twilio = customer-facing ONLY. Never for dealer notifications.
- Rep assignment = DEFERRED to appointment booking. Don't change.
- Transport abstraction = mandatory. Don't hardcode Twilio outside app/transports/.
- One transaction per lead ingestion. No partial commits.
- TDD mandatory. RED before GREEN.
- No v6. v5 ships to market.
