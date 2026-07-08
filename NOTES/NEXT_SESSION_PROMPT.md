# Next-Session Prompt

> **How to use this:** Open a new terminal. Paste the entire `=== COPY FROM HERE ===` block at the end of this file into the new session. The new agent will pick up the v5 build from where this session left off.
>
> **Last updated:** 2026-06-12 (post-5-refactor-passes). Previous version was written 2026-06-11 after Task 1.3; the v5 state, test count, and "what's done" table are now stale — see "v5 state" for current.

---

**What this session is about:** You're picking up the Speed to Lead v5 build. Phase 0 (P0-01) is done. Phase 1 Step 1 (Tasks 1.1, 1.2, 1.3) is done: `notify_rep()` chokepoint, real Twilio WhatsApp+SMS transports, state machine notifications on APPT_SET/ESCALATED/SOLD. Then 5 refactor passes landed in one burst: `route_lead` fresh_session hack killed, 5 cron jobs in `scheduler.py` split into session-parameter variants, `main.py` background task split, plus test fixes. Test suite is 69/69 green (1 skipped = real Twilio).

**Wall we hit:** 30+ FastAPI routes in `app/dashboard/__init__.py`, `app/admin/__init__.py`, `app/main.py` still use the old `_get_session()` + `try/finally` pattern. Four script-based refactor attempts failed. The user has NOT approved moving on to 1.4/1.5/1.6. Recommended next move is Option C (5-line conftest monkey-patch, no source changes) — see the "Refactor wall" section below. **Do not auto-pick 1.4/1.5/1.6.**

---

## Project context

- **Project:** Speed to Lead v5 — a speed-to-lead SMS engine for small BC used-car dealerships
- **Location:** `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/`
- **v5 state (2026-06-12):** 9 commits ahead of v5 migration. Latest commit: `8c5d59f`. Tasks 0.1, 1.1, 1.2, 1.3 done. Then 5 refactor passes (cfc473e, 8e322b2, 132f7df, 4e2e0c4, 8c5d59f) cleaned up engine + scheduler + main. 3 Phase 1 Step 2 tasks (1.4, 1.5, 1.6) still open but the user has said NOT to start them yet. 5 P0 fixes deferred (P0-02, P0-04, P0-05, P0-06, P0-08).
- **Test status:** 69 passed, 0 failed, 1 skipped. The skipped test is `tests/test_notify_rep_real.py` and requires real Twilio credentials. The earlier 9 failures (SQLite `max_overflow` kwarg + v4 field names in tests) have all been fixed.
- **Implementation plan:** `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/V5_BUILD_PLAN.md` (read this FIRST, end to end — it has the TDD steps, code examples, file paths, and verification commands for every task)
- **Spec (what v4's review said to build):** `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/docs/PIPELINE_REVIEW.md`
- **Migration log (what was kept from v4, what was cut, why):** `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/V5_MIGRATION_LOG.md`
- **Session decisions (5 directives, hard rules):** `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/V5_SESSION_DECISIONS.md`

## v5 hard rules (NEVER VIOLATE)

1. **DRYRUN default.** `OUTBOUND_ENABLED=false` in `.env.example`. Real SMS / WhatsApp only when user explicitly says "enable live" AND sets `OUTBOUND_ENABLED=true`. Twilio credits burned in v4 by automated tests. Never again.
2. **TDD discipline.** Every code change has a failing test first. The test runs and FAILS, then the implementation, then the test runs and PASSES, then commit. No "I'll add tests later."
3. **One commit per task.** Frequent commits with clear messages. No big-bang commits at the end.
4. **No fabricated results.** If a tool call fails or a test fails for an unexpected reason, say so directly. Don't make up API responses or claim a test passed when it didn't.
5. **Polished output.** Progress bars, banners, no raw terminal spam.

## The user's 5 design directives (locked in 2026-06-09)

These were confirmed in the 2026-06-09 session. They're not negotiable without re-confirming.

1. **Render tier strategy:** free tier for dev. $14/mo Starter tier for production. VPS not now.
2. **Dealer-side comms = WhatsApp, NOT SMS.** `notify_rep()` chokepoint is in place. Default backend = Twilio WhatsApp. Fallback = SMS. Phase 2 = email / dashboard.
3. **Bypass Twilio for dealer-side if possible (don't force it).** The `notify_rep()` abstraction IS the bypass. Swapping backends later doesn't require touching callers. Do NOT add Meta Cloud API in Phase 1.
4. **Phase 2 provisions in Phase 1 architecture.** Channel enum, free-form dealer config, LeadEvent table, notify_rep chokepoint, Message.recipient_role field. Don't undo any of these.
5. **Testing split:** User tests AI persona tone + dashboard UX manually. Automate state machine, API contracts, compliance gates, tool calling, P0 regression tests.

See `docs/PIPELINE_REVIEW.md` Section H for the full decision log.

## What's done — do not redo

| Task | Commit | What it landed |
|---|---|---|
| 0.1 (P0-01) | `8a07013` | Twilio signature validation on all 3 webhooks + `make_signed_twilio_request` fixture |
| 1.1 | `3882f72` | `tools/notify_rep.py` chokepoint (4 backends), `Message.recipient_role` field, router repointed |
| 1.2 | `6065d82` | Real Twilio WhatsApp + SMS transports (replaced stubs), 4 unit + 1 opt-in live test |
| 1.3 | `a2f0530` | State machine: notify_rep on APPT_SET, ESCALATED, SOLD. `mark_sold()` added. "sale" body template. |
| refactor | `cfc473e` | Killed `fresh_session` hack in `tools/route_lead.py:ingest_lead`. Caller's session + `expire_all()`. |
| refactor | `8e322b2` | Split `_handle_followup` into entry point + `_handle_followup_session(session, ...)` testable variant. |
| test | `132f7df` | P0-11 history assertion fix: expect 11 messages (10 history + 1 current), not 10. |
| refactor | `4e2e0c4` | Split 4 more cron jobs (`escalation_sweep`, `inventory_sync`, `org_sink_flush`, `stuck_lead_sweep`, `daily_digest_for_all_dealers`) into entry point + session variant. |
| refactor | `8c5d59f` | Split `webhook_twilio_sms` background task: `_process_and_send_sync(session, ...)` helper + async entry. |

## The refactor wall (READ THIS before doing route work)

**Problem:** ~30 FastAPI route handlers in 3 files still use the old `_get_session()` + `try/finally` pattern:
- `app/dashboard/__init__.py` (1616 lines, 18 occurrences)
- `app/admin/__init__.py` (1135 lines, 14 occurrences)
- `app/main.py` (904 lines, 8 occurrences, AFTER the webhook split)

**Target pattern (BEFORE → AFTER):**
```python
# BEFORE
@router.get("/some-route")
def some_route(request: Request, _auth: None = Depends(require_auth)):
    session = _get_session()
    try:
        # work using session
    finally:
        session.close()

# AFTER
@router.get("/some-route")
def some_route(
    request: Request,
    _auth: None = Depends(require_auth),
    session: Session = Depends(get_session),
):
    # work using session (FastAPI auto-closes)
```

**Why we stopped:** Four script-based refactor attempts failed in a row — regex dedent doesn't handle multi-line def signatures, nested except blocks, or `try/except/finally` with response objects. The 5 refactor passes that DID land (the engine + scheduler + main) were all single-purpose — this route batch is uniform but the file structure isn't.

**Three options the user was offered (no decision yet):**
- **Option A** — manual patches, one route at a time, ~30-45 min. Most thorough, leaves the codebase fully clean.
- **Option B** — AST-based Python script (not regex), ~45 min. Safer than regex but needs care.
- **Option C** — 5-line conftest monkey-patch so test fixtures' SQLite engine is what `_get_session()` returns. Zero source changes, 5-10 min. Leaves the routes' pattern as-is, but makes future dashboard tests work.

**Assistant's recommendation from prior session:** Option C. The 5 engine/scheduler/main refactors are the actual bug fixes. The route batch is defense-in-depth, not bug fixing. The user did not pick — they said "open a new session and you can get to it." **Ask the user which option before doing route work.** Do not start 1.4/1.5/1.6.

**What NOT to do on the route refactor:**
- Don't try a 5th script without AST-level parsing. Regex is exhausted.
- Don't do batch commits. Per-route or per-file commit, with pytest in between.
- Don't assume Postgres in tests — they use `sqlite:///:memory:`.

## What's still open — pick ONE (only after the route refactor is resolved)

| Task | Why it matters | Scope |
|---|---|---|
| **1.4** Real Twilio WhatsApp inbound webhook | Closes the loop on rep "1" claim, rep "2" pass, customer-initiated WhatsApp. The demo flow. | Verify + fix `/webhook/twilio/whatsapp` to handle the full message lifecycle. Plan: `V5_BUILD_PLAN.md` Step 2 item 1. |
| **1.5** Auto-creating WhatsApp templates in Twilio | Production needs the `HXxxxxxx` content template actually registered. Current `dealers/example-dealer.yaml` has the `'HX_replace_with_real_sid'` placeholder. | A setup script that uses Twilio's Content API to create the template. |
| **1.6** Missed-call handoff decision rule | `/webhook/twilio/voice` doesn't yet decide when to hand the call to a human vs let AI continue. Spec: `PIPELINE_REVIEW.md` Section C3. | Add the decision rule + tests. |
| **0.2** P0-08 CSRF on dashboard login | Security — small, isolated, no engine impact. | Dashboard session cookie needs a CSRF token. |
| **0.3–0.7** P0-02, P0-04, P0-05, P0-06 | Lower priority. P0-02 (normalize_db_url) is the smallest. | See `docs/PIPELINE_REVIEW.md` for what each one fixes. |

The user picks. Do not auto-proceed.

## Deviations from the plan (worth knowing)

- The build plan said "tools/route_lead.py and app/engine/router.py" for state-machine notifications, but APPT_SET actually lives in `tools/book_appointment.py` (Task 1.3 commit message explains why). Future state-machine work should check `book_appointment.py` first, not just router/route_lead.
- The old `_notify_rep_of_appointment` used a multi-line SMS body with emojis. The refactor in Task 1.3 swapped it for the terse `_build_body` template. The dealership loses the rich format but gains the abstraction. If richer WhatsApp templates are wanted later, land them in `_build_body` (one file) — not in `book_appointment.py`.

## What NOT to do

- **Don't run the v5 app** (no `uvicorn`).
- **Don't install dependencies** (no `pip install`). v5 already has the right deps in `requirements.txt`.
- **Don't auto-pick a task.** Ask the user. The exception is if they say "go" / "next" / "lets go" with a clear target.
- **Don't apply deferred P0s** without the user explicitly saying so. The plan defers them; respect it.
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
1. Run `pytest tests/ -v` and confirm no regressions (baseline = 60 passed, 9 pre-existing failed, 1 skipped)
2. Run `git status` and confirm only the expected files changed
3. Run `git diff --staged --stat` for the staged changes summary
4. Commit with a clear message
5. Run `git log --oneline -1` to get the commit hash
6. Report the 6 items above to the user

Then wait for "next task."

---

## === COPY FROM HERE — paste this into the new session ===

You are picking up the Speed to Lead v5 build session. Read this prompt fully before acting.

**Project context:**
- Project: Speed to Lead v5 — speed-to-lead SMS engine for small BC used-car dealerships
- Location: `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/`
**v5 state (2026-06-12):** 9 commits ahead of v5 migration. Latest commit: `8c5d59f`. Tasks 0.1, 1.1, 1.2, 1.3 done. Then 5 refactor passes cleaned up the engine + scheduler + main. Test status: 69 passed, 0 failed, 1 skipped. 3 Phase 1 Step 2 tasks (1.4, 1.5, 1.6) still open but the user has explicitly said NOT to start them yet. 5 P0 fixes deferred.
**Test status:** 69 passed, 0 failed, 1 skipped. The skipped test is `tests/test_notify_rep_real.py` and requires real Twilio credentials.
- Implementation plan: `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/V5_BUILD_PLAN.md` (READ THIS FIRST, END TO END)
- Spec: `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/docs/PIPELINE_REVIEW.md`
- Migration log: `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/V5_MIGRATION_LOG.md`
- Session decisions: `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/V5_SESSION_DECISIONS.md`

**v5 hard rules (NEVER VIOLATE):**
1. **DRYRUN default.** `OUTBOUND_ENABLED=false`. Real SMS / WhatsApp only when user explicitly says "enable live." Twilio credits burned in v4 by automated tests — never again.
2. **TDD discipline.** Failing test first, then implementation, then verify, then commit.
3. **One commit per task.** Clear commit messages. No big-bang commits.
4. **No fabricated results.** If a tool call fails, say so. Don't make up API responses.
5. **Polished output.** Progress bars, banners, no raw terminal spam.

**The user's 5 design directives (locked in 2026-06-09):**
1. Render tier: free for dev, $14/mo Starter for production. VPS not now.
2. Dealer-side comms = WhatsApp, NOT SMS. `notify_rep()` chokepoint in place. Default = Twilio WhatsApp. Fallback = SMS. Phase 2 = email/dashboard.
3. Bypass Twilio for dealer-side. The abstraction IS the bypass. Do NOT add Meta Cloud API in Phase 1.
4. Phase 2 provisions in Phase 1 architecture. Don't undo any of them.
5. Testing split: User tests AI persona tone + dashboard UX manually. Automate state machine, API contracts, compliance gates, tool calling, P0 regression tests.

**What's done (do not redo):**
- Task 0.1 (P0-01): Twilio signature validation — `8a07013`
- Task 1.1: notify_rep() chokepoint — `3882f72`
- Task 1.2: Real Twilio WhatsApp + SMS transports — `6065d82`
- Task 1.3: State machine notify on APPT_SET, ESCALATED, SOLD — `a2f0530`
- Refactor: killed `fresh_session` hack in `route_lead.py` — `cfc473e`
- Refactor: split `_handle_followup` into entry + session variant — `8e322b2`
- Test: P0-11 history assertion fix — `132f7df`
- Refactor: split 4 more cron jobs (escalation, inventory, org_sink, stuck_lead, daily_digest) — `4e2e0c4`
- Refactor: split `webhook_twilio_sms` background task — `8c5d59f`

**THE ROUTE REFACTOR WALL (do this FIRST, before anything else):**
~30 FastAPI routes in `app/dashboard/__init__.py`, `app/admin/__init__.py`, `app/main.py` still use `_get_session()` + `try/finally`. Four prior script attempts failed. Three options the user has NOT yet chosen between:
- **Option A** — manual patches, ~30-45 min, most thorough
- **Option B** — AST-based Python script, ~45 min, safer than regex
- **Option C** — 5-line conftest monkey-patch, 5-10 min, zero source changes (prior assistant's recommendation)

**Ask the user which option BEFORE doing any work on the routes.** Do not auto-pick. Do not try a 5th script without AST-level parsing.

**Do NOT start 1.4/1.5/1.6.** The user explicitly said "I dont want you to start building or executing the 1.4, 1.5, 1.6 right away." This applies to the entire session. Even after the route refactor is resolved, do not auto-pick 1.4/1.5/1.6.

**Deviations from plan worth knowing:**
- State-machine notifications live in `tools/book_appointment.py` for APPT_SET/SOLD (not router/route_lead as the plan says). Task 1.3 commit message documents this.
- The old `_notify_rep_of_appointment` multi-line SMS body is gone; the new chokepoint uses terse `_build_body` templates. If richer WhatsApp templates are wanted, land them in `tools/notify_rep.py` — not in `book_appointment.py`.

**What NOT to do:**
- Don't run the v5 app (no `uvicorn`).
- Don't install dependencies (no `pip install`).
- Don't auto-pick a task. Ask the user.
- Don't apply deferred P0s without the user explicitly saying so.
- Don't add features beyond what's in `V5_BUILD_PLAN.md`.
- Don't touch v4.
- Don't change the v5 hard rules without the user explicitly saying so.

**When you finish a task, always:**
1. Run `pytest tests/ -v` — confirm no regressions (baseline = 69 passed, 0 failed, 1 skipped)
2. Run `git status` — confirm only expected files changed
3. Run `git diff --staged --stat` — get the staged changes summary
4. Commit with a clear message
5. Run `git log --oneline -1` — get the commit hash
6. Report the 6 items above to the user

Then wait for direction.

Begin by reading `V5_BUILD_PLAN.md` end to end. Then read the "Refactor wall" section in the project-context part of this prompt. Then ask the user: "Route refactor — A (manual, 30-45 min), B (AST script, 45 min), or C (conftest monkey-patch, 5-10 min)?" Do NOT start 1.4/1.5/1.6 in this session.

## === END COPY — paste the above into the new session ===
