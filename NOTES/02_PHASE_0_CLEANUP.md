# Phase 0: Cleanup

## Task 0.1: Remove AI agent scaffolding ✅

**What was done:**
- Deleted `.claude/` — AI agent swarm coordination, agent configs, SPARC methodology files (~25 files)
- Deleted `.claude-flow/` — swarm metrics, audit logs, config (~7 files)
- Deleted `.mcp.json` — MCP server config for Claude Flow ruflo
- Deleted `HTTP` — empty file (0 bytes)
- Updated `.gitignore` with scaffolding patterns so they can't be re-introduced

**Why:**
These were dev-only scaffolding added by previous AI agent sessions. Not product code. Shipping them would be production drift.

**Verification:**
- `pytest tests/ -x --tb=short` → 128 passed, 1 skipped (same as baseline, no regressions)
- `git status` shows no scaffolding files remaining
- `.gitignore` now blocks: `.claude/`, `.claude-flow/`, `.mcp.json`, `HTTP`, `.mimocode/`, `MIMO_CONTEXT_PASTE.txt`, `MIMO_HANDOFF.md`

**Files changed:**
- `.gitignore` — added 7 new patterns for scaffolding

## Task 0.2: Remove test-mode WhatsApp handler 🔲

**Not started.** This is the 180-line `_handle_customer_whatsapp_test()` function in `app/main.py` at line 781. It duplicates logic from the SMS handler.

**Target:** Delete the function and its route. WhatsApp messages would route through the normal SMS handler instead.

## Test suite after Phase 0

Same as baseline:
- 128 passed, 1 skipped
- 0 failures, 0 errors
- 1 benign SAWarning
