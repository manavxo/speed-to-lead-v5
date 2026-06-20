# Where to Resume Next

## Current Phase: Phase 2 — Database & Migrations

**Just completed:** Phase 1 (all 5 critical bugs)

**Next up:** Task 2.1 — Install Alembic, Task 2.2 — Create initial migration, Task 2.3 — Increase connection pool size, Task 2.4 — Remove duplicated _normalize_db_url

**After Phase 2:** Phase 3 — Transaction Safety

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
