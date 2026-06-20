# Where to Resume Next

## Current Phase: Phase 1 — Critical Bugs

**Just completed:** Task 1.3 (fix pass_count persistence)

**Next up:** Task 1.4 — Fix phone masking in email adapter

`app/adapters/intake/email_lead.py` masks phone at parse time (line 49). Same bug that was fixed in `route_lead.py` but missed here. Phone should be stored unmasked, masked only at display time.

**After 1.4:** Task 1.5 (consent=False in email adapter)

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
