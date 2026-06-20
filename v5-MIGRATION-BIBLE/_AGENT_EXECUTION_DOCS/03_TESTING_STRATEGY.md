# Speed to Lead v5 — Testing Strategy for AI-Assisted Refactoring

> **Purpose:** Define how the AI agent tests every change so the system ships with minimum rework and maximum confidence.
> **Target:** AI agents executing the 11-phase refactoring + Phase 12 (dealership demo site).
> **Principle:** A fix you didn't test is not a fix. A feature you didn't verify is not done.

---

## 1. The Problem with AI-Generated Code

AI agents produce code at high speed but with systematic blind spots:

| AI Weakness | How It Manifests | Cost |
|---|---|---|
| **Halos** (invented APIs) | Calls a function that doesn't exist yet | Runtime crash |
| **Broken assumptions** | Assumes Twilio returns a field that was removed in v2 | Silent failure |
| **State blindness** | Doesn't understand lead lifecycle transitions | Corrupt data |
| **Copy-paste rot** | Duplicates logic instead of reusing | Maintenance nightmare |
| **Interface drift** | Changes a function signature, forgets to update callers | Broken imports |
| **Edge case amnesia** | Handles the happy path, ignores the 5 error states | Production crashes |
| **Test blindness** | Writes a test that passes but tests nothing meaningful | False confidence |

Every one of these has bitten this codebase. The testing strategy is designed to catch every single one before you see it.

---

## 2. The Testing Pyramid (This Project's Version)

```
         ┌──────────┐
         │ E2E      │  ← Few: 1 per pipeline flow (webform → lead → auto-reply → appt)
         │ (2-3)    │    Slow, expensive, confidence-boosting
        ┌┴──────────┴┐
        │ Integration │ ← Some: 1 per API endpoint + 1 per notification channel
        │ (20-30)    │    Test that components actually wire together
       ┌┴─────────────┴┐
       │  Unit Tests   │ ← Many: 1 per function, 1 per edge case, 1 per state transition
       │  (200+)       │    Fast, cheap, catch 80% of bugs
      ┌┴────────────────┴┐
      │ Contract Tests   │ ← Every: API response shape, DB model fields, env config
      │ (per endpoint)   │    Catch interface drift instantly
     ┌┴───────────────────┴┐
     │ Compliance Gates    │ ← Always: consent, opt-out, PIPA/CASL, DRYRUN safety
     │ (per lead flow)     │    Legal protection, not just code quality
```

### What This Means for Every Phase

Phase 0-2 (bugs):     Start with a failing test that reproduces the bug, THEN fix.
Phase 3-8 (features): Write the contract test first, then the unit test, then the implementation.
Phase 9-11 (UI/roles): Integration tests for auth gating + browser tests for UI layout.
Phase 12 (demo site):  E2E tests for the full webform → lead → AI → appointment loop.

---

## 3. The 3-Layer Test Commandment

### Layer 1: RED Before GREEN (Non-Negotiable)

Before ANY code change, the AI agent writes a test that proves the bug or missing feature:

```
# BAD (agent fixes the bug, then writes a test that passes):
  def test_fix():
      result = my_function()      # Function is already fixed
      assert result == expected   # Test can't fail

# GOOD (agent writes a test against the BROKEN code first):
  # Step 1: Write this, run it, watch it FAIL (RED)
  def test_bug():
      result = my_function()      # Function is still broken
      assert result == expected   # This MUST fail

  # Step 2: Fix the function
  # Step 3: Run again, watch it PASS (GREEN)
  # Step 4: Commit
```

**Why this matters for AI:** Without the RED phase, the AI can write a test that accidentally tests the wrong thing. The RED phase proves the test can actually detect the bug.

### Layer 2: The 3-Pass Rule

Every feature test must verify three things:

1. **Happy path** — It works with perfect inputs
2. **Guard path** — It rejects or handles bad inputs gracefully  
3. **Idempotency** — Running it twice doesn't corrupt state

Example for webform intake:
```python
# HAPPY: Valid webform creates lead + auto-reply
def test_webform_creates_lead_and_reply(db_session):
    ...

# GUARD: Missing phone returns validation error
def test_webform_missing_phone_returns_error(client):
    ...

# IDEMPOTENT: Same payload twice doesn't create duplicate leads
def test_webform_idempotent_prevents_duplicate(db_session):
    ...
```

### Layer 3: The MUST-FAIL Check

Every new test file must have at least one `@pytest.mark.xfail` test that deliberately tests an unimplemented boundary condition:

```python
@pytest.mark.xfail(reason="Future: email intakes not wired for IMAP yet")
def test_email_poll_persists_new_lead():
    ...
```

This documents what's NOT done yet and prevents the AI from silently claiming completeness.

---

## 4. Test Infrastructure (Already Built)

### Fixtures (in `tests/conftest.py`)
| Fixture | Purpose | External Dependencies |
|---|---|---|
| `db_engine` | In-memory SQLite, fresh schema per test | None |
| `db_session` | SQLAlchemy session per test | None |
| `fake_twilio` | Records outbound messages instead of sending | None |
| `fake_llm` | Returns scripted responses instead of calling API | None |
| `frozen_now` | Fixed datetime for deterministic time-based tests | None |
| `auth_cookies` | Valid session cookie for dashboard tests | None |

### What Must NOT Change
- No test may hit a real external service (Twilio API, OpenAI, DeepSeek, etc.)
- All tests use SQLite `:memory:` — never Postgres or file-backed DB
- `OUTBOUND_ENABLED` is always `false` in test env
- Tests must run without any `.env` file present (env defaults set in conftest.py)

### What to Add

For Phase 12 (demo site), add browser-based test fixtures:

```python
@fixture
def browser_client():
    """Playwright browser fixture for dealership site UI tests."""
    # Launches headless Chromium, navigates to demo site
    # Returns page object for interaction

@fixture  
def demo_site_vehicle_data():
    """20 vehicles matching the dealership demo site YAML inventory."""
    # Used by both backend (e2e) and frontend (browser) tests
```

---

## 5. Per-Phase Testing Requirements

### Phase 0: Cleanup — Regression Tests Only
```
Task 0.1 (remove scaffolding):    Run ALL existing tests → must still pass
Task 0.2 (remove test handler):   Verify route 404s + existing tests still pass
```

### Phase 1: Critical Bugs — RED Tests First
```
Task 1.1 (digest crash):          
  RED:   Call send_daily_digest() with valid dealer → MUST crash
  GREEN: Fix the undefined dealer var → MUST pass
  VERIFY: Dealer.id is accessible inside the function

Task 1.2 (greeting_only lifecycle):
  RED:   Trigger greeting_only → confirm no LeadEvent created
  GREEN: Wire through transition() → LeadEvent created
  VERIFY: LeadEvent has correct reason="greeting_only_mode"

Task 1.3 (pass_count persistence):
  RED:   Pass a lead 3 times, close session, reopen → pass_count = 0
  GREEN: Add pass_count column, implement correctly → pass_count = 3
  VERIFY: DB query confirms persisted value
```

### Phase 2: Data Integrity — 3-Pass Required
```
Task 2.1 (phone masking):         
  HAPPY:  Customer phone stored as-is
  GUARD:  10-digit, 11-digit, E.164 all normalize correctly
  IDEMP:  Same number normalized twice produces same result

Task 2.2 (consent flag):          
  HAPPY:  Listing site leads have consent=True
  GUARD:  STOP command sets consent=False
  IDEMP:  Double-consent doesn't create duplicate ConsentLog
```

### Phases 3-8: Feature Implementation — Contract + Unit + Integration
```
Every new endpoint needs:
  CONTRACT: Response shape matches OpenAPI spec (fields exist, types correct)
  UNIT:     Business logic handles edge cases
  INTEG:    Database writes are persisted and rollback-safe

Every new transport needs:
  UNIT:     Chokepoint dispatches to correct backend
  INTEG:    Transport can be injected via fixture
  LIVE:     (Optional) hermes doctor verifies credentials exist
```

### Phase 9: Email Channel — Cascade Timing Tests
```
HAPPY:  Lead with phone → SMS/WhatsApp within 60s
GUARD:  Lead without phone → email follow-up within 24h
IDEMP:  Same lead captured twice via email → dedup
EDGE:   Email with unparseable format → LLM fallback
EDGE:   Email reply → Telegram notification (🔵 triage)
```

### Phase 10: Manager vs Rep Roles — Auth Gating
```
HAPPY:  Rep sees own leads + unassigned
GUARD:  Rep cannot see other reps' leads (403)
HAPPY:  Manager sees all leads with filter
GUARD:  Manager can reassign, rep cannot
IDEMP:  Transfer logged once in LeadEvent
```

### Phase 11: UI Redesign — Browser-Level Tests
```
Dashboard pages load under 1s:
  Agent measures with requests.get() + timing

All states have visual distinction:
  Agent checks CSS classes for color coding

Mobile-responsive:
  Agent resizes viewport, confirms no horizontal scroll

Login flow:
  Agent fills form, submits, confirms session cookie set
```

### Phase 12: Dealership Demo Site — Full E2E + Visual
```
Inventory browsing:
  Browser: Navigate to Inventory, filter by type, verify results

Vehicle detail page (VDP):
  Browser: Click a vehicle → detail loads with price, specs, photos
  Backend: GET /api/vehicles/{id} returns correct JSON

Webform → Lead pipeline:
  E2E: Fill form → POST → Lead created → Auto-reply sent → AI engages
  
Financing page:
  Browser: Financing page loads with pre-approval form
  Backend: Form POST creates lead with special tag "financing"

Trade-in page:
  Browser: Trade-in form loads
  Backend: Form POST creates lead with tag "trade-in"

Consent checkbox compliance:
  E2E: Unchecked consent → 400 error
  E2E: Checked consent → lead created with consent_logged=true

Mobile responsiveness:
  Browser: 3 viewport sizes (mobile/tablet/desktop) → no broken layout
```

---

## 6. The Testing Sequence (How the Agent Executes)

Every phase follows this exact sequence. No shortcuts.

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 0: Read this document + the REFACTORING_GUIDE task     │
├─────────────────────────────────────────────────────────────┤
│ STEP 1: Review existing tests for the area being changed    │
│         - "tests/test_pipeline_e2e.py" for pipeline changes │
│         - "tests/test_lifecycle.py" for state machine       │
│         - "tests/test_notify_rep.py" for notification       │
│         Run them first — they must pass before touch        │
├─────────────────────────────────────────────────────────────┤
│ STEP 2: Write the RED test (failing test for the bug/feature)│
│         Include all 3 passes (happy + guard + idempotent)   │
│         Run it → confirm it FAILS                           │
├─────────────────────────────────────────────────────────────┤
│ STEP 3: Implement the fix/feature                           │
│         Minimum code to pass the test                       │
├─────────────────────────────────────────────────────────────┤
│ STEP 4: Run the test → confirm it PASSES (GREEN)            │
├─────────────────────────────────────────────────────────────┤
│ STEP 5: Run the FULL test suite → confirm no regressions    │
│         pytest -x --tb=short → all pass                     │
├─────────────────────────────────────────────────────────────┤
│ STEP 6: Commit                                              │
│         git add -A && git commit -m "Phase X.Y: description"│
├─────────────────────────────────────────────────────────────┤
│ STEP 7: If UI/dealer site change → browser verification     │
│         Take screenshot, confirm non-broken layout          │
├─────────────────────────────────────────────────────────────┤
│ STEP 8: Check regression coverage                           │
│         "Would a new developer changing this code break it?" │
│         If yes → add one more test to prevent regression    │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. The MUST-FAIL Manifesto

| Situation | What the agent does |
|---|---|
| Bug reported with no test | Writes RED test reproducing the bug before any fix |
| Feature requested with existing tests | Runs existing tests first (they must pass) |
| Feature with NO existing tests in the area | Writes 3-pass test suite before implementation |
| AI suggests an optimization | Writes a benchmark test + optimization + verification |
| Edge case identified during code review | Writes a test for it immediately |
| Something breaks the test suite | Stops, reports which test broke, fixes before proceeding |
| UI change | Screenshots before + after + mobile check |
| Database schema change | Migration test + rollback test + data integrity test |
| External API integration | Unit test with fakes + integration test with recorded responses |

---

## 8. Verification Checklist (For You — Human in the Loop)

Before signing off any phase:

- [ ] Agent showed the RED test failing before the fix
- [ ] All 3 passes (happy + guard + idempotent) are covered
- [ ] Full test suite passes (no regressions)
- [ ] At least one xfail test documents what's NOT done
- [ ] New tests use existing fixtures (fake_twilio, fake_llm, db_session)
- [ ] No test hits a real external service
- [ ] Tests run without .env file
- [ ] Commit message references the phase number

---

## 9. Cost-Aware Testing (Because DeepSeek Costs Money)

| Test Type | Token Cost | Run Frequency |
|---|---|---|
| Unit tests (pytest -x) | ~2K tokens | Every commit |
| Full suite (pytest) | ~5K tokens | Before every push |
| E2E pipeline test | ~3K tokens | Once per phase |
| Browser verification | ~10K tokens (vision) | Once per UI change |
| Live Twilio test | SKIP (costs real money) | Only when asked |

**Efficiency rule:** Don't run the full suite after every line change. Run the single test file first, then the full suite only before commit. The agent reports which command it ran.

---

## 10. Dashboard + Demo Site Testing (Phase 11-12)

These phases need a special approach because they're visual:

### Automated (Backend)
- All API endpoints return correct JSON shapes (contract tests)
- Auth gating works (403 for unauthorized, 200 for authorized)
- Database queries return correct data (unit tests)
- Webform submissions create leads correctly (E2E)

### Manual-Verified (You Check)
- Page looks professional (you look at screenshot)
- Mobile layout doesn't break (you open on phone)
- Colors match dealership branding (you confirm)
- Animation/transition feels smooth (you watch)
- Form works end-to-end (you submit)

### AI-Verified (Browser Tool)
- Page loads under 1 second (agent measures)
- No JS console errors (agent checks)
- Form validation works (agent fills invalid data, confirms error message)
- All links resolve to 200 (agent crawls site)
- No horizontal scroll at 375px width (agent checks)

---

## 11. What Happens When a Test Fails Unexpectedly

```
1. Agent reads the full error and traceback
2. Agent identifies root cause (not just symptom)
3. If the test itself is wrong → fix the test
4. If the implementation is wrong → fix the code
5. NEVER "skip failing test for now" — that's tech debt
6. NEVER mock around the failure — that's hiding the bug
7. If the fix needs a real API call → use fake, not real
8. Commit the fix with "test: " prefix so the changelog is clear
```

---

*This document was generated after analyzing the full codebase, existing 130+ test suite, conftest infrastructure, REFACTORING_GUIDE phases, and the specific testing gaps for AI-assisted coding workflows. All 11 phases of the refactoring now have explicit testing requirements.*