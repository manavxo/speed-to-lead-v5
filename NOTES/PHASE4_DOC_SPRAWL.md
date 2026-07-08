# Phase 4 — Root-Level Doc Sprawl: Inventory & Proposal

**Date:** 2026-07-07
**Context:** NOTES/HERMES_CLEANUP_SECURITY_SPEC.md — Phase 4

---

## Current doc homes

| Location | Count | Role |
|----------|-------|------|
| `./` (root) | 18 loose files | Handoffs, specs, agents, build plans |
| `NOTES/` | 23 files + 1 PDF | Session notes, build logs, specs, receipts |
| `docs/` | 3 files | Technical reference |
| `.herpes/` | 1 file (duplicate) | Dupe of root spec |
| `v5-MIGRATION-BIBLE/` | 6 files | PRD, alignment docs, setup docs |

---

## Root-level proposals

| # | File | Last Modified | Purpose | Proposed Action |
|---|------|--------------|---------|-----------------|
| 1 | `CLAUDE.md` | Jun 27 | Agent project context (always loaded) | **Keep at root** — essential, loaded every session |
| 2 | `CLAUDE_CODE_VERIFY_CORE_PIPELINE.txt` | Jul 7 (now sanitized) | Pipeline verification runbook | **Keep at root** — still useful as runbook (env-var driven now) |
| 3 | `CLAUDE_CODE_VERIFY_CORE_PIPELINE.sh` | Jun 20 | Shell version of above | **Delete** — superseded by .txt (same content, never used) |
| 4 | `CLAUDE_HANDOFF.md` | Jun 27 | Session handoff | **Move to NOTES/** |
| 5 | `HERMES_CODEBASE_REVIEW_AND_MIMO_EXECUTION_SPEC.md` | Jun 27 | Full codebase review spec | **Move to NOTES/** (has duplicate in .herpes/) |
| 6 | `MIMO_CONTEXT_PASTE.txt` | Jun 18 | Context paste for Mimo sessions | **Move to NOTES/** |
| 7 | `MIMO_HANDOFF.md` | Jun 18 | Mimo-to-Hermes handoff | **Move to NOTES/** |
| 8 | `NEXT_SESSION_PROMPT.md` | Jun 12 | Prompt for next session | **Move to NOTES/** or delete if superseded |
| 9 | `PROMPT_FOR_CLAUDE_CODE.md` | Jun 20 | Prompt for Claude Code sessions | **Move to NOTES/** |
| 10 | `README.md` | Jun 9 | Project readme | **Keep at root** — standard for any repo |
| 11 | `requirements.txt` | Jun 21 | Python dependencies | **Keep at root** — needed for install/build |
| 12 | `V5_BUILD_PLAN.md` | Jun 9 | Build plan | **Move to NOTES/** |
| 13 | `V5_MIGRATION_LOG.md` | Jun 9 | Migration log | **Move to NOTES/** |
| 14 | `V5_SESSION_DECISIONS.md` | Jun 9 | Session decisions log | **Move to NOTES/** |
| 15 | `WHATSAPP_FIX_PROMPT.md` | Jun 17 | WhatsApp fix prompt | **Move to NOTES/** |
| — | `cookies.txt` | Jun 19 | Session cookie (untracked) | **Delete** — no longer tracked, safe to remove from disk |

## Other observations

| Item | Observation | Proposed Action |
|------|-------------|-----------------|
| `.herpes/review-and-mimo-spec.md` | Identical to `HERMES_CODEBASE_REVIEW_AND_MIMO_EXECUTION_SPEC.md` (both 405 lines) | **Delete duplicate**; keep the root copy for now (or move both to NOTES/) |
| `v5-MIGRATION-BIBLE/` | 6 files, 2 hidden dirs | **Already organized** — leave as-is unless you want to flatten into NOTES/ |
| `setup pics/` | Screenshots | Already in `.gitignore` territory — leave alone |

## Summary

- **Keep at root:** CLAUDE.md, README.md, requirements.txt (3)
- **Move to NOTES/:** CLAUDE_HANDOFF.md, HERMES_CODEBASE_REVIEW_AND_MIMO_EXECUTION_SPEC.md, MIMO_CONTEXT_PASTE.txt, MIMO_HANDOFF.md, NEXT_SESSION_PROMPT.md, PROMPT_FOR_CLAUDE_CODE.md, V5_BUILD_PLAN.md, V5_MIGRATION_LOG.md, V5_SESSION_DECISIONS.md, WHATSAPP_FIX_PROMPT.md (10)
- **Delete or archive:** CLAUDE_CODE_VERIFY_CORE_PIPELINE.sh, cookies.txt (2)
- **Delete duplicate:** `.herpes/review-and-mimo-spec.md` (1)
