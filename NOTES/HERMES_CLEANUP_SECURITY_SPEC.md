# Hermes Execution Spec — Security Cleanup + Repo Hygiene

> **Date:** 2026-07-07
> **Written by:** Claude (session with manav), following a code review of uncommitted
> working-tree state + a repo hygiene pass
> **Status:** Not started — handoff spec only, nothing below has been executed by Hermes yet
> **Re-test after:** manav runs the app + pytest + engine_test_harness personally before calling this done

---

## ROLE

Senior engineer doing a security + hygiene pass on a live, deployed FastAPI app
(Speed to Lead v5, Render-hosted, real Twilio number, real dealer). You are
working in **git-bash on Windows** (not PowerShell). Nothing here touches the
conversation engine, routing logic, or any application code — this is entirely
credentials, git state, and file organization.

## GOAL

Fix, in priority order:
1. Live credentials committed to git history (the only genuinely dangerous item)
2. A config-corruption bug that already happened once (dealer phone numbers got
   asterisk-masked in the working tree, breaking SMS routing) — add a guard so it
   can't happen silently again
3. A phantom broken git submodule
4. Root-level doc sprawl

**Do not touch application code paths** (`app/engine/`, `tools/`, `app/main.py`
webhook handlers) as part of this spec — that's out of scope. If you find
something there, log it in a new NOTES file and stop; don't fix it inline.

---

## HARD RULES

1. **No force-push, no history rewrite, without manav explicitly saying "go" on that specific step.** Rewriting git history invalidates every existing clone and needs coordination — do Phase 1 (rotation) fully, confirm rotation worked, THEN ask before Phase 1b (purge).
2. **Small commits, one concern per commit.** Never `git add -A`.
3. **Run `pytest tests/ -q` before and after every commit** that touches tracked files. Record the before/after pass count in `NOTES/FIX_RECEIPTS.md`-style output.
4. **Never delete a file you haven't listed by name and gotten a decision on.** For the doc-sprawl phase, propose a keep/archive/delete mapping and get sign-off before deleting anything — several of these root docs may still be referenced by memory or habit.
5. **No secrets in anything you write** — new files, commit messages, NOTES output. If you need to reference a rotated key, reference it by name (`RENDER_API_KEY`) never by value.
6. **Self-sufficient. Batch questions at the end** in a `DECISIONS.md`-style block rather than stopping mid-phase, except for the force-push gate in rule 1, which is a hard stop.

---

## PHASE 1 — Rotate exposed credentials (CRITICAL, do first)

### What's exposed
Two tracked files carry live secrets, confirmed already present in `git show HEAD:<file>` (i.e., already in history, not just working tree):

| File | Contains | Impact if used by an attacker |
|---|---|---|
| `CLAUDE_CODE_VERIFY_CORE_PIPELINE.txt` | `RENDER_API_KEY=rnd_...`, full Postgres `DATABASE_URL` with plaintext password, Twilio Account SID + Auth Token | Full Render service control, full prod DB read/write, send/receive SMS + drain Twilio balance |
| `cookies.txt` | A live `HttpOnly` session cookie for `speed-to-lead-v5.onrender.com` | Walk into the prod dashboard as a logged-in manager without a PIN |

### Steps
1. **Rotate the Render API key** — Render dashboard → Account Settings → API Keys → revoke the exposed one, generate a new one. Update it wherever it's actually needed (local `.env`, any CI secret) — do NOT put it back in a tracked file.
2. **Rotate the Twilio Auth Token** — Twilio Console → Account → API keys & tokens → regenerate the Auth Token for the account SID in the exposed file. Update `.env` / Render env vars (`TWILIO_AUTH_TOKEN`). This will briefly interrupt SMS sending until the new token is deployed — do it in a maintenance window, not mid-conversation with a real lead.
3. **Rotate the Postgres password** — Render dashboard → the Postgres instance → reset password (or recreate the DB user). Update `DATABASE_URL` in Render env vars and local `.env`. Confirm the app still connects (`python -c "from app.config import settings; print(settings)"` and a live health check) before moving on.
4. **Invalidate the leaked dashboard session** — rotate `DASHBOARD_SECRET` (forces all existing sessions, including the one in `cookies.txt`, to log out). Confirm by trying the old cookie against `/dashboard/leads` and getting redirected to login.
5. **Stop tracking the files, without deleting their useful content:**
   - `cookies.txt` → `git rm --cached cookies.txt`, add `cookies.txt` to `.gitignore`. Also check `v4 archived/dr_cookies.txt` — same treatment, or confirm the `v4 archived` tree is being handled in Phase 3 instead.
   - `CLAUDE_CODE_VERIFY_CORE_PIPELINE.txt` → replace every literal secret with an env-var placeholder (`RENDER_API_KEY=${RENDER_API_KEY}` style) so the runbook is still usable, then commit that as a normal file (it's fine to keep tracked once it has no live values).
6. Record what was rotated and when in `NOTES/FIX_RECEIPTS.md` (new section, no values — just "rotated Render API key, Twilio auth token, DB password, dashboard secret — 2026-07-07").

**Checkpoint — stop here and confirm with manav before Phase 1b.**

### Phase 1b — Purge from git history (only after explicit go-ahead)
The secrets remain readable in every prior commit even after Phase 1's edits land on top. If manav wants them actually gone from history (recommended, since rotation alone doesn't un-expose the old values to anyone who already has a clone):
1. Use `git filter-repo` (not `filter-branch`, not BFG unless already installed) to strip the two files' secret-bearing history, or rewrite just the offending blobs.
2. This rewrites every commit SHA after the earliest touched commit — **anyone with an existing clone must re-clone**, and any open branches/PRs need to be redone.
3. Force-push only after manav confirms no one else has a clone that matters, or after coordinating a re-clone.
4. This step needs an explicit "go" — do not run `filter-repo` or any force-push as part of an unattended pass.

---

## PHASE 2 — Guard against the dealer-config corruption class of bug

**Context:** `dealers/premier-auto.yaml` was found with `main_phone`, `sms_number`,
`whatsapp_sender`, `manager_phone`, and 2 of 5 `sales_team` phone numbers replaced
with asterisk-masked strings (`+177****3122`), and 2 `sales_team` entries (Dana,
Sarah) deleted outright — all in the uncommitted working tree. Root cause unknown
(not investigated — could be a redaction tool, an editor autocomplete/paste
mangling, or manual edit). It's already restored from `git show HEAD` and the
restore is committed... check that it actually got committed as part of this spec,
don't assume.

1. Confirm `git diff HEAD -- dealers/premier-auto.yaml` is empty (i.e. the restore from the prior session is actually committed, not just sitting in the working tree again).
2. Add a cheap regression guard — either a pytest test or a startup check in `app/config.py`'s dealer-YAML loader — that fails loudly if `sms_number`, `whatsapp_sender`, `main_phone`, or any `sales_team[*].phone` doesn't match `^\+\d{10,15}$` (a real E.164 shape). This should catch masked/corrupted numbers the next time this happens, before it reaches prod.
3. Do not add retroactive validation anywhere else — scope this to the dealer YAML loader only.

---

## PHASE 3 — Fix the phantom git submodule

`v4 archived/Speed to Lead v4` has its own `.git` directory but no entry in
`.gitmodules`, so `git status` reports a permanently-dirty submodule-shaped line
(`m "v4 archived/Speed to Lead v4"`) that isn't actually manageable via normal
submodule commands.

1. Decide (ask manav if unclear): is `v4 archived/` meant to be a live submodule (pinned to a commit, updatable), or just archived static files that happen to have a `.git` folder in them?
2. If archived/static (likely, given the name): `rm -rf "v4 archived/Speed to Lead v4/.git"` so it's absorbed as normal tracked files in the parent repo, then commit.
3. If it should stay a real submodule: add the proper `.gitmodules` entry instead.
4. Either way, `git status` should stop showing that phantom `m` line afterward.

---

## PHASE 4 — Root-level doc sprawl (do last, lowest risk / lowest urgency)

Root currently has ~15 loose `.md`/`.txt` handoff/notes files, plus four separate
doc homes: `NOTES/`, `docs/`, `v5-MIGRATION-BIBLE/`, `.herpes/`.

1. **Don't delete anything yet.** First produce a table: file → last modified → one-line guess at purpose → proposed action (keep at root / move to NOTES/archive / delete).
2. Candidates that are probably safe to archive (session-specific, superseded by newer handoffs): `MIMO_CONTEXT_PASTE.txt`, `NEXT_SESSION_PROMPT.md`, `PROMPT_FOR_CLAUDE_CODE.md`, `WHATSAPP_FIX_PROMPT.md`, `CLAUDE_CODE_VERIFY_CORE_PIPELINE.sh`/`.txt` (once Phase 1 is done) — but confirm none of these are things manav still pastes into new sessions before moving them.
3. Present the table to manav and wait for sign-off on the mapping before moving/deleting a single file.
4. `.herpes/review-and-mimo-spec.md` looks like a duplicate of `HERMES_CODEBASE_REVIEW_AND_MIMO_EXECUTION_SPEC.md` at root — diff the two and confirm before treating either as disposable.

---

## DONE =

- Phase 1: all four credentials rotated, `cookies.txt` untracked + gitignored, `CLAUDE_CODE_VERIFY_CORE_PIPELINE.txt` has no live secrets, app confirmed still working against the new DB password (health check + one real webhook round-trip).
- Phase 2: `git diff HEAD -- dealers/premier-auto.yaml` clean, new E.164 guard test passes and fails correctly against a deliberately-masked number (write the negative test).
- Phase 3: `git status` no longer shows the phantom submodule line.
- Phase 4: only after manav signs off on the keep/archive/delete table.
- `pytest tests/ -q` pass count is equal to or better than the baseline at the start of this spec (record both counts in `NOTES/FIX_RECEIPTS.md`).

**Re-test loop:** once Hermes reports done, manav runs the app locally, hits the
real dashboard, and re-runs `scripts/engine_test_harness.py` + `pytest` personally
before treating any phase as verified — this spec's "done" is Hermes's self-report,
not the final word.
