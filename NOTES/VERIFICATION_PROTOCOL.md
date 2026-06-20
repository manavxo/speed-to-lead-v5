# Speed to Lead v5 — Verification Protocol

> **Run after EVERY phase. Do not start the next phase until this is complete.**
> **Purpose:** Prevent "tests pass but nothing works" — independent QA from a subagent.

## How it works

After every phase, spawn a **QA subagent** using `delegate_task()`. Its ONLY job is to verify the work. It does NOT write features. It does NOT fix bugs — it reports them.

## QA Agent Prompt Template

```
You are a QA subagent for Speed to Lead v5. Your ONLY job is to verify.
Do NOT write feature code. Do NOT fix bugs. Inspect, test, and report.

PROJECT ROOT: C:\Speed to Lead v5
TEST COMMAND: cd /c/Speed\ to\ Lead\ v5 && pytest tests/ -x --tb=short

PHASE JUST COMPLETED: [Phase X.Y — description]
FILES CHANGED:
- [file1]
- [file2]
- [file3]

TESTS ADDED/MODIFIED:
- [test1]
- [test2]

KNOWN GAPS (don't flag these):
- [gap1 — intentional]
- [gap2 — deferred to later phase]

RUN THESE CHECKS:

## 1. Static Analysis
- Do all changed files parse without syntax errors?
- Do all imports resolve? (python -c "from <module> import <thing>")
- No undefined variables in changed functions?

## 2. Test Suite
- Run the FULL test suite: pytest tests/ -x --tb=short
- Run any new test files specifically: pytest tests/test_<new_file>.py -v
- Confirm each new test actually tests something meaningful (not tautological)

## 3. Import Health
- Can the app's modules be imported? (python -c "from app.models import Lead")
- Can the config be loaded? (python -c "from app.config import settings")

## 4. Edge Cases
- What happens with empty/null inputs for the changed functions?
- What happens with duplicate calls?
- What happens when external services are down?

## 5. Integration Integrity
- Do the changed files still work with their callers? (grep for imports)
- Are there any references to deleted functions/variables?

Return your verdict in this format:

VERDICT: PASS | WARN | FAIL
BLOCKING ISSUES: [list or "none"]
NON-BLOCKING ISSUES: [list or "none"]
TESTS: X passed, Y failed, Z skipped
READY FOR NEXT PHASE: yes | no | with caveats
```

## Required Checks Per Phase (not exhaustive — add as you discover)

### Phase 0-2 (infrastructure)
- [ ] All existing tests still pass
- [ ] New tests actually test something (not tautological)
- [ ] No dead code left behind
- [ ] Deleted functions not referenced elsewhere

### Phase 3-5 (business logic)
- [ ] Transaction rollback works (intentional failure test)
- [ ] State transitions are logged
- [ ] Future-dates validated, past-dates rejected
- [ ] Rep identity verified on claim
- [ ] New transport abstraction doesn't break existing callers

### Phase 6-8 (additive)
- [ ] Rate limits actually work (test with 11 requests)
- [ ] Debug endpoints return 404 when disabled
- [ ] Conversation summarization actually reduces tokens

### Phase 9-12 (user-facing)
- [ ] Email parsing extracts all fields correctly
- [ ] Role-based access works (rep vs manager)
- [ ] UI loads under 1 second
- [ ] Mobile-responsive (no horizontal scroll at 375px)
- [ ] Full E2E pipeline: form → lead → AI → appointment

## Pitfalls (from real QA sessions)

1. **Cross-cutting changes need exhaustive path enumeration** — If a change touches "all X paths" (e.g., phone masking), list EVERY file explicitly in the QA context.
2. **Windows paths with spaces** — Project root is `C:\Speed to Lead v5`. Quote paths in shell commands.
3. **Pytest assertions that look identical but aren't** — If `assert 'X' == 'X'` fails, check with `repr()` for hidden encoding differences.
4. **Env var changes that derive secrets** — If 6+ auth tests fail after adding an env var, check serializer/cookie mismatch first.
