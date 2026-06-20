# Where to Resume Next

## Current Phase: Phase 1 — Critical Bugs

**Just completed:** Task 1.2 (fix greeting_only lifecycle bypass)

**Next up:** Task 1.3 — Fix pass_count persistence

`pass_count` is set as a runtime attribute via `getattr(lead, "pass_count", 0) + 1` in `app/engine/router.py`. May be lost on session refresh. Needs to be a proper DB column.

**After 1.3:** Task 1.4 → 1.5 (in order)

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
