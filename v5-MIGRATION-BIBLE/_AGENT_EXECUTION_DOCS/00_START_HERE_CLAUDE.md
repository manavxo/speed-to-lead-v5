# Speed to Lead v5

## Architecture
- FastAPI + SQLAlchemy + PostgreSQL (Render hosted)
- Twilio for SMS/WhatsApp/Voice (customer-facing ONLY)
- DeepSeek V4 Flash for AI conversation (direct API, not OpenRouter)
- Telegram Bot API for dealer notifications (ONLY dealer channel)
- Deployed: https://speed-to-lead-v5.onrender.com

## Key Documents (read in this order)
1. `ARCHITECTURE.md` — vision, principles, channel architecture, roles
2. `CODEBASE_AUDIT.md` — current state of the codebase, what's broken
3. `REFACTORING_GUIDE.md` — THE executable plan: 12 phases, ~35.5 hours
4. `TESTING_STRATEGY.md` — 3-layer testing framework
5. `EMAIL_STRATEGY.md` — email lead handling detailed design
6. `DESKTOP_SETUP.md` — DeepSeek + compression config for desktop machine

## Key Commands
- `uvicorn app.main:app --reload` — dev server
- `pytest -x --tb=short` — run full test suite (stop on first failure)
- `pytest tests/test_<file>.py -x --tb=short` — run single test file
- `python -c "from app.config import settings; print(settings)"` — check config
- `alembic upgrade head` — apply migrations
- `git add -A && git commit -m "Phase X.Y: description"` — commit pattern

## Execution Contract (every session)
1. Read `REFACTORING_GUIDE.md` to confirm current phase
2. Read `TESTING_STRATEGY.md` to confirm testing protocol
3. Run full test suite — ALL tests must pass before touching code
4. Identify exact file + line for the task
5. Write RED test first — confirm it FAILS
6. Implement minimum code to pass
7. Confirm test PASSES (GREEN)
8. Run full test suite — no regressions
9. Update `NEXT_SESSION_PROMPT.md`
10. Commit: `git commit -m "Phase X.Y: description"`

## Key Decisions (non-negotiable — do NOT reverse)
- **Telegram is the ONLY dealer notification channel.** No WhatsApp fallback for dealers.
- **Twilio is customer-facing ONLY.** Never used for dealer-side notifications.
- **Rep assignment is DEFERRED to appointment booking.** Do NOT change this.
- **Transport abstraction is mandatory.** Do NOT hardcode Twilio outside app/transports/.
- **One transaction per lead ingestion.** No partial commits.
- **TDD is mandatory.** RED before GREEN. Every task.
- **No v6.** The only path to v6 is a customer requesting exclusive features.

## Zero-Rework Doctrine (7 failure modes to guard against)
1. **Hallucinated dependencies** — verify imports/functions/config exist before writing code
2. **Silent state corruption** — every state change through transition(), verify DB persistence
3. **Copy-paste multiplication** — search before creating, reuse before extend
4. **Interface drift** — update ALL callers + ALL tests after signature change
5. **Context window amnesia** — read REFACTORING_GUIDE.md every session
6. **"I'll add tests later" trap** — RED phase mandatory, contract tests for every endpoint
7. **Production drift** — test code never in app/, DRYRUN default enforced

## Shell
Use bash syntax (git-bash/MSYS on Windows). NOT PowerShell.