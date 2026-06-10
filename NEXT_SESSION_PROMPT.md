# Next-Session Prompt

> **How to use this:** Open a new terminal. Paste the entire `=== COPY FROM HERE ===` block at the end of this file into the new session. The new agent will pick up the v5 build at Task 0.1.

---

**What this session is about:** You're picking up the Speed to Lead v5 build. The v5 directory was created 2026-06-09 by migrating reusable code from v4, applying 3 P0 safety fixes, and writing the implementation plan. Your job is to execute the plan, starting with the Twilio signature validation fix (P0-01) and then building the `notify_rep` abstraction with Twilio WhatsApp as the default.

---

## Project context

- **Project:** Speed to Lead v5 — a speed-to-lead SMS engine for small BC used-car dealerships
- **Location:** `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/`
- **v5 state:** 65 files, commit `6bdac8d`. Engine migrated from v4. 3 of 9 P0 fixes already applied (P0-03 OpenAI singleton, P0-09 readyz 503, P0-10 TwiML escape). 6 P0 fixes still pending.
- **Implementation plan:** `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/V5_BUILD_PLAN.md` (read this FIRST, end to end)
- **Spec (what v4's review said to build):** `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/docs/PIPELINE_REVIEW.md`
- **Migration log (what was kept from v4, what was cut, why):** `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/V5_MIGRATION_LOG.md`

## v5 hard rules (NEVER VIOLATE)

1. **DRYRUN default.** `OUTBOUND_ENABLED=false` in `.env.example`. Real SMS / WhatsApp only when user explicitly says "enable live" AND sets `OUTBOUND_ENABLED=true`. Twilio credits burned in v4 by automated tests. Never again.
2. **TDD discipline.** Every code change has a failing test first. The test runs and FAILS, then the implementation, then the test runs and PASSES, then commit. No "I'll add tests later."
3. **One commit per task.** Frequent commits with clear messages. No big-bang commits at the end.
4. **No fabricated results.** If a tool call fails or a test fails for an unexpected reason, say so directly. Don't make up API responses or claim a test passed when it didn't. The user explicitly forbids this.
5. **Polished output.** Progress bars, banners, no raw terminal spam. The user is recording a video of this build.

## The user's 5 design directives (locked in for this build)

These were confirmed in a session on 2026-06-09. They're not negotiable without re-confirming.

1. **Render tier strategy:** free tier for dev. $14/mo Starter tier for production (when the first real dealer goes live). VPS not now.
2. **Dealer-side comms = WhatsApp, NOT SMS.** Build the `notify_rep()` abstraction. Default backend = Twilio WhatsApp. Fallback = SMS. Phase 2 = email / dashboard.
3. **Bypass Twilio for dealer-side if possible (don't force it).** The `notify_rep()` abstraction IS the bypass. Swapping backends later doesn't require touching callers. Don't add Meta Cloud API in Phase 1.
4. **Phase 2 provisions in Phase 1 architecture.** Channel enum, free-form dealer config, LeadEvent table, notify_rep chokepoint, Message.recipient_role field. Don't undo any of these.
5. **Testing split:** User tests AI persona tone + dashboard UX manually. Automate state machine, API contracts, compliance gates, tool calling, P0 regression tests.

See `docs/PIPELINE_REVIEW.md` Section H for the full decision log.

## Your first task: Task 0.1 — Twilio signature validation (P0-01)

This is a non-negotiable prerequisite for the WhatsApp feature. We're about to add more Twilio surface area (WhatsApp templates), so the signature bypass has to be closed first. Without it, any attacker who knows the webhook URL can fake both customer SMS and WhatsApp messages.

**The full task with TDD steps, code examples, and verification is in `V5_BUILD_PLAN.md` Section "Task 0.1: Twilio signature validation (P0-01)". Read it end to end before starting.**

The task is bite-sized (2-5 min if you go fast, 15-30 min if you read every line). It produces:
- 5 new tests in `tests/test_webhook_security.py`
- `_validate_twilio_signature()` in `app/main.py`
- Signature check applied to all 3 Twilio webhooks (sms, voice, whatsapp)
- `make_signed_twilio_request` fixture added to `tests/conftest.py`
- Existing webhook tests updated to use the new fixture
- One commit: `fix: P0-01 Twilio signature validation`

## After Task 0.1

Stop and report. Don't auto-proceed to Task 1.1. The user wants to confirm Task 0.1 worked before moving on.

**Report format:**
- Task name (e.g., "Task 0.1: Twilio signature validation")
- Files changed (with line counts)
- Test results (pytest summary: X passed, Y failed, Z skipped)
- Git commit hash
- Any discrepancies with the plan
- Any "I noticed X while doing this" observations

Wait for the user to say "next task" before proceeding.

## After Task 1.1 + Task 1.2 (the WhatsApp feature)

Stop. The user will want to manually test the WhatsApp feature end-to-end before continuing. They will:
1. Set `OUTBOUND_ENABLED=true` in `.env`
2. Set Twilio WhatsApp creds
3. Run the integration test (opt-in via `RUN_TWILIO_INTEGRATION=true`)
4. Confirm the WhatsApp arrives on their phone
5. Tell you to proceed

## What NOT to do

- **Don't run the v5 app** (no `uvicorn`).
- **Don't install dependencies** (no `pip install`). v5 already has the right deps in `requirements.txt`. Install happens in the user's session, not yours.
- **Don't apply the OTHER 5 P0 fixes** (P0-02, P0-04, P0-05, P0-06, P0-08). They are deferred to later sessions. The build plan is focused.
- **Don't add new features** beyond what's in `V5_BUILD_PLAN.md`. No "while I'm at it" additions.
- **Don't delete or modify v4.** v4 is dead. v5 is the only thing that moves.
- **Don't change the v5 hard rules** (DRYRUN default, TDD, one commit per task, etc.) without the user explicitly saying so.
- **Don't use git commands that affect v4.** The v4 directory has its own git history; leave it alone.

## When something breaks

1. Read the full error. Don't skim.
2. Try the obvious fix (typo, missing import, wrong path).
3. If the fix isn't obvious, search the v5 codebase for the answer.
4. If still stuck, ask the user. Be specific about what you tried.

The user has the "figure it out" mandate. They want you to exhaust options before asking. But they also want you to ask when you're truly stuck — don't sit silently for 30 minutes trying things.

## When you finish a task

Always:
1. Run `pytest tests/ -v` and confirm no regressions
2. Run `git status` and confirm only the expected files changed
3. Run `git diff --staged --stat` for the staged changes summary
4. Commit with a clear message
5. Run `git log --oneline -1` to get the commit hash
6. Report the 6 items above to the user

Then wait.

---

## === COPY FROM HERE — paste this into the new session ===

You are picking up the Speed to Lead v5 build session. Read this prompt fully before acting.

**Project context:**
- Project: Speed to Lead v5 — a speed-to-lead SMS engine for small BC used-car dealerships
- Location: `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/`
- v5 state: 65 files, commit `6bdac8d`. Engine migrated from v4. 3 of 9 P0 fixes already applied (P0-03 OpenAI singleton, P0-09 readyz 503, P0-10 TwiML escape). 6 P0 fixes still pending.
- Implementation plan: `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/V5_BUILD_PLAN.md` (READ THIS FIRST, END TO END)
- Spec: `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/docs/PIPELINE_REVIEW.md`
- Migration log: `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/V5_MIGRATION_LOG.md`

**v5 hard rules (NEVER VIOLATE):**
1. **DRYRUN default.** `OUTBOUND_ENABLED=false`. Real SMS / WhatsApp only when user explicitly says "enable live." Twilio credits burned in v4 by automated tests — never again.
2. **TDD discipline.** Failing test first, then implementation, then verify, then commit. No "I'll add tests later."
3. **One commit per task.** Clear commit messages. No big-bang commits.
4. **No fabricated results.** If a tool call fails, say so. Don't make up API responses or claim success when there was failure.
5. **Polished output.** Progress bars, banners, no raw terminal spam. The user is recording a video.

**The user's 5 design directives (locked in 2026-06-09):**
1. **Render tier:** free for dev, $14/mo Starter for production. VPS not now.
2. **Dealer-side comms = WhatsApp, NOT SMS.** Build `notify_rep()` abstraction. Default = Twilio WhatsApp. Fallback = SMS. Phase 2 = email/dashboard.
3. **Bypass Twilio for dealer-side if possible (don't force it).** The abstraction IS the bypass. Don't add Meta Cloud API in Phase 1.
4. **Phase 2 provisions in Phase 1 architecture.** Channel enum, free-form dealer config, LeadEvent table, notify_rep chokepoint, Message.recipient_role. Don't undo any of these.
5. **Testing split:** User tests AI persona tone + dashboard UX manually. Automate state machine, API contracts, compliance gates, tool calling, P0 regression tests.

**Your first task: Task 0.1 — Twilio signature validation (P0-01)**

Read `V5_BUILD_PLAN.md` Section "Task 0.1" end to end. It has the TDD steps, code examples, file paths, and verification commands. Execute it bite-by-bite.

After Task 0.1, **stop and report**:
- Task name
- Files changed (with line counts)
- Test results (pytest summary)
- Git commit hash
- Any discrepancies with the plan
- Any observations ("I noticed X while doing this")

Then wait for the user to say "next task" before proceeding to Task 1.1.

**What NOT to do:**
- Don't run the v5 app (no `uvicorn`).
- Don't install dependencies (no `pip install`).
- Don't apply the OTHER 5 P0 fixes — they're deferred.
- Don't add features beyond what's in `V5_BUILD_PLAN.md`.
- Don't touch v4.
- Don't change the v5 hard rules without the user explicitly saying so.

**When you finish a task, always:**
1. Run `pytest tests/ -v` — confirm no regressions
2. Run `git status` — confirm only expected files changed
3. Run `git diff --staged --stat` — get the staged changes summary
4. Commit with a clear message
5. Run `git log --oneline -1` — get the commit hash
6. Report the 6 items above to the user

Then wait for "next task".

Begin by reading `V5_BUILD_PLAN.md` end to end. Then execute Task 0.1.

## === END COPY — paste the above into the new session ===
