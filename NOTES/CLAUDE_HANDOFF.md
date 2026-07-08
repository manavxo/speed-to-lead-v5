# Claude Handoff — Dashboard Fix + Deploy

## How to use this file
- **Option A:** Tell Claude: `Read CLAUDE_HANDOFF.md and execute it step by step.`
- **Option B:** Select-all + paste this entire file as your first prompt.

---

## ROLE
Senior Python/FastAPI engineer and production debugger. You recover from your own errors, run tests before every commit, and never pester the user. You are working in **git-bash on Windows** (not PowerShell).

## GOAL
Take the finished but untested + unpushed dashboard changes (D1–D9) and deliver them to production:
1. Fix the broken `bash` tool (shell startup error)
2. Run `pytest tests/` — make it green
3. Fix any regressions found
4. Commit and push to `main` to trigger Render auto-deploy

**Reuse what exists. Do not rewrite working code.**

## CONTEXT — What's been done

D1–D9 code changes are fully implemented in the working tree. The spec lives at `NOTES/DASHBOARD_FIX_SPEC.md` (read it for the authoritative detail).

### Files changed:
| File | What changed |
|------|-------------|
| `app/dashboard/__init__.py` | Logger, `_base_context` helper, `_check_lead_access` rep-scoping, all page routes pass base context, role guards on team/settings, rep-scoped stats, scoped appointments, scoped leads_partial, New Lead POST route, legal status dropdown, toast-standardized responses, try/except on notify_rep |
| `app/dashboard/templates/base.html` | Team/Settings nav gated by `user_role` in sidebar + mobile bar, Logout button in sidebar + mobile bar, improved `htmx:responseError` handler |
| `app/dashboard/templates/leads.html` | New Lead button opens modal, modal form posts to `/dashboard/leads/new`, reloads list on success |
| `app/dashboard/templates/lead_detail.html` | Status dropdown shows only legal next-states, all inline `onclick="showToast()"` removed |
| `tests/test_dashboard_pages.py` | 13 new tests: page loads for manager/rep, lead scoping, new lead creation, logout |
| `tests/e2e/` | Playwright harness (package.json, config, seed script, 18 E2E tests) |

### The bottleneck (unresolved)
The `bash` tool in the Mimo environment is **completely broken**. Every command — including `echo hello` — fails with:
```
undefined is not a function (near '...$.nothrow().quiet`rtk rewrite ${output.args.command}`...')
```
This appears to be a JavaScript error in the shell's prompt customization (oh-my-posh / starship), not a shell PATH or Python issue. You must diagnose and fix this before any other work.

**Do not skip this.** You cannot run `pytest`, `git`, `node`, or anything else until bash works.

## FILL THIS IN ONCE

```python
# Already set in .env / Render env vars:
#   DATABASE_URL=postgresql://...  (Render provides this)
#   DASHBOARD_SECRET=...
#   DASHBOARD_PASSWORD_HASH=...
#   OUTBOUND_ENABLED=false
#   QUIET_HOURS_DISABLED=true

# Test dealer (auto-provisioned on first startup):
#   dealers/premier-auto.yaml
#   Manager PIN: 1234
#   Rep "Helly" PIN: 7721
#   Rep "Vishva" PIN: 4826

# Baseline test count (before your changes): 184 passed, 1 skipped
```

## HARD RULES
1. **Small commits, one per fix.** `git add` specific files, never `git add -A`.
2. **Run `pytest tests/ -x -q` before every commit.** Never commit red.
3. **Additive & reversible.** Never delete working code.
4. **No secrets in code.** `.env`, credentials never committed.
5. **Gate external side effects** behind `OUTBOUND_ENABLED=false` (already set in dev).
6. **Self-sufficient.** Decide → record in DECISIONS.md → continue. Batch blockers at the end.

## PHASED PLAN

### Phase 0 — Fix bash
1. Identify the shell startup file causing the error (`~/.bashrc`, `~/.bash_profile`, `~/.profile`, `~/.config/powershell/Microsoft.PowerShell_profile.ps1`)
2. Check if oh-my-posh or starship is the culprit (the error mentions `rtk rewrite` which is a posh prompt function)
3. Temporarily rename the startup file or comment out the prompt line
4. Verify with `echo hello` and `pytest --version`

### Phase 1 — Test + fix
1. Run `pytest tests/ -x -q`
2. Fix any failures (likely import issues, template variable gaps, or DB setup)
3. Run full suite — target ≥185 passed (baseline 184 + new tests)
4. If critical path tests pass, you're good

### Phase 2 — Git commit
```bash
git add app/dashboard/__init__.py app/dashboard/templates/base.html app/dashboard/templates/leads.html app/dashboard/templates/lead_detail.html tests/test_dashboard_pages.py tests/e2e/
git commit -m "Dashboard: role split, lead scoping, logout, new-lead form, legal status dropdown, toast standardization, Playwright harness"
```

### Phase 3 — Push to deploy
```bash
git push
```
Render auto-deploys `main` → https://speed-to-lead-v5.onrender.com

## KNOWN-FAILURE RUNBOOK (this project)
| Symptom | Cause | Fix |
|---------|-------|-----|
| `logger` NameError in dashboard | Missing `logger = logging.getLogger(...)` at module top | Already fixed (D1) |
| User shows "John Doe" | `user_name`/`user_role`/`user_initials` not passed to template | Already fixed (D1) |
| 500 on /stats, /team, /settings | Missing context vars in route | Already fixed (D1, but verify with TestClient) |
| "Can't move a NEW lead to SOLD" | Transition not in `TRANSITIONS` dict | D7 adds dropdown of only legal states |
| Double toast on mark-lost | Inline `onclick` + route 303 → HTMX error | Already fixed (D8) |
| Reps see all leads | Query had `OR assigned_rep IS NULL` | Already fixed (D4) |

## DEFINITION OF DONE
- `pytest tests/` green (≥185 passed)
- Code pushed to `main` on GitHub
- Render auto-deploy triggers
- Live dashboard: rep sees only own leads, no Team/Settings, working logout, correct name, single toasts, working New Lead form, legal-only status options; manager full access

## WHEN DONE GIVE ME
1. Per-file summary of any additional changes you made
2. Test output (`pytest tests/ -v` summary)
3. Git log of the new commits
4. Link to the Render deploy log (or confirmation that push went through)
5. A single-line summary: everything green + URL
