# Hermes Kickoff — Security Cleanup + Repo Hygiene

Paste this to Hermes to start.

---

TASK: Fix the security/hygiene issues found in a code review + repo audit this
session. Read the full spec first: NOTES/HERMES_CLEANUP_SECURITY_SPEC.md —
follow it exactly, in phase order.

Summary:
- Phase 1 (CRITICAL): rotate the Render API key, Twilio auth token, and Postgres
  password that are live in `CLAUDE_CODE_VERIFY_CORE_PIPELINE.txt`, plus the prod
  dashboard session cookie tracked in `cookies.txt`. Untrack both files' secrets.
  STOP before Phase 1b (git history purge) and get explicit go-ahead — that step
  force-pushes and needs coordination.
- Phase 2: confirm the `dealers/premier-auto.yaml` restore is actually committed,
  and add a regression guard so masked/corrupted phone numbers in dealer YAML
  fail loudly instead of silently breaking SMS routing again.
- Phase 3: fix the phantom `v4 archived/Speed to Lead v4` nested-git-dir that
  makes `git status` show a permanently dirty fake submodule.
- Phase 4 (last, lowest urgency): propose a keep/archive/delete table for the
  ~15 loose root-level handoff docs — wait for sign-off before touching any of
  them.

HARD RULES: no force-push without explicit go, small single-concern commits,
run `pytest tests/ -q` before/after every commit, never put a secret's actual
value in a commit/file/NOTES output, don't touch app/engine or tools/ code.

DONE = all four phase checkpoints in the spec are met and recorded in
NOTES/FIX_RECEIPTS.md. manav re-tests personally afterward — Hermes's self-report
is not the final word.
