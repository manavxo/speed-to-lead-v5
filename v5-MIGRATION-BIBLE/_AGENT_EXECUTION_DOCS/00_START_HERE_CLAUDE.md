# Speed to Lead v5

## Architecture
- FastAPI + SQLAlchemy + PostgreSQL (Render hosted)
- Twilio for SMS/WhatsApp/Voice (customer-facing ONLY)
- DeepSeek V4 Flash for AI conversation (direct API, not OpenRouter)
- Telegram Bot API for dealer notifications (ONLY dealer channel)
- Deployed: https://speed-to-lead-v5.onrender.com

## Key Documents (read in this order)
0. **`../PRD_HUMAN.md`** — THE NORTH STAR. What the world actually expects. Overrides all other docs on conflict.
1. **`../PRD_AGENT.md`** — autonomy framework + 8 real-world tests. You CAN override the bible when UX demands it.
2. `../RE-ALIGNMENT_PROMPT.md` — run AFTER EVERY PHASE. Keeps work anchored to reality.
3. `VISION.md` — business context, 6 core promises, decisions that supersede the PRDs, pitfall catalog
4. `ARCHITECTURE.md` — vision, principles, channel architecture, roles, UI standard
5. `CODEBASE_AUDIT.md` — current state of the codebase, what's broken
6. `TESTING_STRATEGY.md` — 3-layer testing framework, per-phase test requirements
7. `REFACTORING_GUIDE.md` — THE executable plan: 12 phases, ~35.5 hours, zero-rework doctrine
8. `VERIFICATION_PROTOCOL.md` — 5-point verification checklist run after EVERY phase
9. `EMAIL_STRATEGY.md` — email lead handling detailed design
10. `PHASE_LOG.md` — execution log of completed phases and verification results

## Key Commands
- `uvicorn app.main:app --reload` — dev server
- `pytest -x --tb=short` — run full test suite (stop on first failure)
- `pytest tests/test_<file>.py -x --tb=short` — run single test file
- `python -c "from app.config import settings; print(settings)"` — check config
- `alembic upgrade head` — apply migrations
- `git add -A && git commit -m "Phase X.Y: description"` — commit pattern

## Execution Contract (every session)
1. Read `PHASE_LOG.md` to confirm current state and next phase
2. Read `REFACTORING_GUIDE.md` to confirm current phase tasks
3. Read `TESTING_STRATEGY.md` to confirm testing protocol
4. Run full test suite — ALL tests must pass before touching code
5. Identify exact file + line for the task
6. Write RED test first — confirm it FAILS
7. Implement minimum code to pass
8. Confirm test PASSES (GREEN)
9. Run full test suite — no regressions
10. Commit: `git commit -m "Phase X.Y: description"`
11. **RUN VERIFICATION_PROTOCOL.md** — 5-point checklist against VISION.md
12. Update `PHASE_LOG.md` with verification results
13. Update `NEXT_SESSION_PROMPT.md` for next session handoff

## Key Decisions (non-negotiable — do NOT reverse)
- **Telegram is the ONLY dealer notification channel.** No WhatsApp fallback for dealers.
- **Twilio is customer-facing ONLY.** Never used for dealer-side notifications.
- **Rep assignment is DEFERRED to appointment booking.** Do NOT change this.
- **Email is CAPTURE, not conversation.** One follow-up email, then rep handoff. AI does NOT continue email conversations.
- **Transport abstraction is mandatory.** Do NOT hardcode Twilio outside app/transports/.
- **One transaction per lead ingestion.** No partial commits.
- **TDD is mandatory.** RED before GREEN. Every task.
- **No v6.** The only path to v6 is a customer requesting exclusive features.

## The 6 Core Promises (from VISION.md — check alignment after every phase)
1. Instant response on every channel (under 60 seconds)
2. A real conversation, not a robot (inventory-aware, persona-matched)
3. A test drive booked over text (AI offers specific time slots)
4. The customer is always in control (STOP/START, quiet hours, CASL)
5. Their data is private (PIPA-BC, 7-year retention)
6. One customer, one conversation across channels (cross-day dedup)

## The Pitfall Catalog (from VISION.md — check after every task)
1. Phone format mismatch → use `normalize_phone()` everywhere
2. Config dict vs DB column lag → dual-source fallback
3. Quiet hours block testing → `QUIET_HOURS_DISABLED=true` or per-dealer override
4. Twilio sandbox 24h expiry → re-join sandbox
5. Business-initiated WhatsApp needs template → pre-approved template SID
6. Render cold start → cron ping or upgrade plan
7. Missing PUBLIC_BASE_URL → MUST be set to full Render URL
8. Idempotency in testing → unique SIDs in tests
9. Missing import → silent empty TwiML → check imports
10. Test-mode WhatsApp handler in production → remove before production

## Zero-Rework Doctrine (7 failure modes to guard against)
1. **Hallucinated dependencies** — verify imports/functions/config exist before writing code
2. **Silent state corruption** — every state change through transition(), verify DB persistence
3. **Copy-paste multiplication** — search before creating, reuse before extend
4. **Interface drift** — update ALL callers + ALL tests after signature change
5. **Context window amnesia** — read REFACTORING_GUIDE.md every session
6. **"I'll add tests later" trap** — RED phase mandatory, contract tests for every endpoint
7. **Production drift** — test code never in app/, DRYRUN default enforced

## PRD Status
- `PRD_HUMAN.md` — HISTORICAL. Superseded by VISION.md + ARCHITECTURE.md.
- `PRD_AGENT.md` — HISTORICAL. Superseded by VISION.md + ARCHITECTURE.md + REFACTORING_GUIDE.md.
- Do NOT use PRDs as source of truth. Use VISION.md → "Decisions That Supersede the PRDs" for current direction.
- Business context from PRDs has been preserved in VISION.md.

## Shell
Use bash syntax (git-bash/MSYS on Windows). NOT PowerShell.
