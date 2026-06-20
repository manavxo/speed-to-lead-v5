# Where to Resume Next

## Current Phase: Phase 3 — Transaction Safety

**Just completed:** Phase 2 (Alembic, pool size, dedup normalize_db_url)

**Next up:** Task 3.1 — Add future-date validation to appointments

`tools/book_appointment.py` can book appointments in the past. Need to add validation that rejects dates before now.

**After 3.1:** Task 3.2 → 3.3

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
