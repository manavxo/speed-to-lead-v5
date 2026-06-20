# Where to Resume Next

## Current Phase: Phase 0 — Cleanup

**Just completed:** Task 0.1 (remove scaffolding)

**Next up:** Task 0.2 — Remove test-mode WhatsApp handler (`_handle_customer_whatsapp_test` at `app/main.py:781`)

This is ~180 lines of production logic running inside a "test" handler. It duplicates the SMS conversation flow. Delete the function and the route that calls it. Make sure WhatsApp messages still work after (they'd route through the normal handler — need to verify).

**After Phase 0:** Phase 1 — Critical bugs. Priority order:
1. Fix daily digest crash (CRITICAL — will hit production)
2. Fix greeting_only lifecycle bypass
3. Fix pass_count persistence
4. Fix phone masking in email adapter
5. Fix consent=False in email adapter

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
