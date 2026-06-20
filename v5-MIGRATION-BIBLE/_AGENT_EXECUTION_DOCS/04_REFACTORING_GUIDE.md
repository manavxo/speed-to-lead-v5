# Speed to Lead v5 — Refactoring Guide for AI Agents

> **For:** AI agents executing refactoring on the new PC
> **Prerequisite:** Read `CODEBASE_AUDIT.md` first, then `TESTING_STRATEGY.md`
> **State:** Based on LIVE GitHub codebase (commit c4ca0ff)
> **Purpose:** Precise, ordered instructions for fixing what's broken
> **No v6 will be built. v5 goes to market. Every phase must ship quality.**

---

## How to Use This Document

Each task has:
- **WHAT** — what's wrong
- **WHERE** — exact file and line range
- **FIX** — what to do (not suggestions — instructions)
- **VERIFY** — how to confirm it's done right
- **DEPENDS** — what must be done first
- **TESTS** — what test to write first (RED), step by step

Tasks are ordered by dependency. Do them in sequence. Never skip a phase.

---

## The Execution Contract

Before starting ANY phase, the agent MUST:

1. **Read `TESTING_STRATEGY.md` in full** — this is embedded in agent memory
2. **Run the full test suite** — `pytest -x --tb=short` — all 130+ tests must pass before touching any code
3. **Identify the EXACT file + line number** for every change — no guessing
4. **Write the RED test first** — prove the bug exists before fixing it
5. **Run only the new test** — confirm it FAILS (RED)
6. **Implement the fix**
7. **Run the new test only** — confirm it PASSES (GREEN)
8. **Run the full test suite** — confirm no regressions
9. **Commit** — `git add -A && git commit -m "Phase X.Y: description"`

If any step in this contract fails, STOP and report. Do not skip, do not fabricate, do not assume.

---

## The Zero-Rework Doctrine

These are the failure modes discovered across ALL previous sessions. Every one has caused real rework. Every one is now guarded against.

### Failure Mode 1: Hallucinated Dependencies

| Symptom | Real example from this project | Protection |
|---------|-------------------------------|-----------|
| Agent adds a package that doesn't exist | Adding imaginary npm packages for the demo site | Run `pip install <package>` or `npm install <package>` BEFORE committing to code. If it fails, find an alternative. Never write code that imports a package you haven't verified exists. |
| Agent calls an API endpoint that doesn't exist | AI called `inventory.sync()` before the function was written | Every function call in a PR must have been verified by reading the source file. If you call a function you haven't read, you're hallucinating. |
| Agent references a config field that isn't in the YAML | `dealers/premier-auto.yaml` referenced `telegram_chat_id` before it was added | Every new config field must be added to the test fixture YAML AND the actual dealer YAML before being referenced in code. |

**Guard:** Before writing ANY line of code, the agent must:
1. Read the source file it's about to change
2. Verify every import it wants to use actually exists
3. Verify every function it calls actually exists
4. Verify every config field it references actually exists in the YAML
5. If the agent can't find the file — it doesn't exist. Do NOT create it unless the task explicitly says "Create new file."

### Failure Mode 2: Silent State Corruption

| Symptom | Real example | Protection |
|---------|-------------|-----------|
| Direct state assignment bypasses lifecycle | `lead.state = LeadState.ASSIGNED` instead of `transition(lead, LeadState.ASSIGNED)` | Every state change must go through `transition()`. The RED test explicitly checks for a corresponding LeadEvent entry. |
| Partial transaction commits a half-broken lead | Webform creates a lead, auto-reply succeeds, AI follow-up fails — lead is stuck in AUTO_REPLIED | The entire `ingest_lead()` pipeline is wrapped in a single transaction. If any step fails, the entire lead creation rolls back. Test: verify with intentional AI failure. |
| Runtime attribute that disappears on session refresh | `lead.pass_count` was set with `getattr()` and lost on DB reconnect | Every runtime attribute must be a proper DB column with a default. Test: create a lead, set attribute, close session, reopen, verify attribute persists. |

**Guard:** After every state mutation, commit the session and re-read the data from the database. Compare before/after. If the two don't match, the mutation isn't persisting.

### Failure Mode 3: Copy-Paste Multiplication

| Symptom | Real example | Protection |
|---------|-------------|-----------|
| Same function duplicated in multiple files | `_normalize_db_url()` in both `app/db.py` and `app/scheduler.py` | Before creating a new function, search the codebase for existing functions that do the same thing. `search_files(pattern="def .*normalize")`. If found, import and reuse. Do NOT duplicate. |
| Same logic duplicated in test handler and real handler | `_handle_customer_whatsapp_test()` was 180 lines of production code in a test route | Before creating a test handler, check if the existing handler can be extended. If adding a feature that already exists in the test handler, migrate it to the real handler and delete the test duplication. |
| Same YAML structure repeated across multiple dealer configs without a shared schema | Each dealer's config had slightly different field names | Every dealer config must match exactly one schema. Use the `demo-dealer.yaml` fixture as the canonical reference. If the schema changes, update the fixture AND all real dealer configs. |

**Guard:** Before writing ANY new code, search the codebase for something similar. If it exists:
- **Reuse it** — import and call the existing function
- **Extend it** — add an optional parameter rather than creating a new function
- **Move it** — if you find it in the wrong place, move it to the right place, don't duplicate it

### Failure Mode 4: Interface Drift

| Symptom | Real example | Protection |
|---------|-------------|-----------|
| Function signature changes but callers aren't updated | `send_sms()` signature changed, `route_lead.py` still calls old signature | After changing ANY function signature, run the full test suite AND manually trace every call site. `search_files(pattern="send_sms")` to find all callers. |
| Return type changes but assertions don't | Function used to return a string, now returns a dict | Every public function should have a return type annotation. Contract tests assert the return shape matches. |
| Error type changes but error handlers don't | Custom exception replaced with ValueError, try/except catches the wrong type | After changing an exception type, update ALL try/except blocks that catch it. Test that the error handler actually triggers. |

**Guard:** After changing any public function:
1. Update the signature
2. Update ALL callers (search the codebase)
3. Update ALL tests that mock or call it
4. Run the full test suite
5. If any test fails, fix the caller, not the signature

### Failure Mode 5: Context Window Amnesia

| Symptom | Real example | Protection |
|---------|-------------|-----------|
| Agent forgets what phase it's on | Stops halfway through Phase 2, starts working on Phase 5 | Every session starts by reading `REFACTORING_GUIDE.md` to confirm the current phase. The `NEXT_SESSION_PROMPT.md` file exists for this exact reason. |
| Agent forgets the testing contract | Writes implementation before the test | The execution contract at the top of this document is non-negotiable. RED before GREEN. If the agent doesn't write a failing test first, the task is not complete. |
| Agent forgets architecture decisions | Re-introduces WhatsApp for dealer notifications after the Telegram-only decision | Every session reads the "Key Decisions" section at the end of this document. No decision is reversed without the user's explicit approval. |

**Guard:** The `NEXT_SESSION_PROMPT.md` file is updated after every session with:
1. What phase was completed
2. What tests were added
3. What the current state of the code is
4. What the next phase is
5. Any sticky decisions that must not be reversed

### Failure Mode 6: The "I'll Add Tests Later" Trap

| Symptom | Real example | Protection |
|---------|-------------|-----------|
| Agent says "the tests pass with current code" | Agent wrote a test that can't fail because it tests the already-fixed code | The RED phase is mandatory. The failing test proves the test can catch the bug. If the test passes on the first run, it's testing the wrong thing. |
| Agent tests the mock, not the real code | `mock_twilio.send()` is tested but the real `send_sms()` is different | Integration tests verify the real function. Unit tests verify specific logic. Both are required. The conftest.py provides `fake_twilio` for unit tests AND a validation path for integration tests. |
| Agent says "covered by existing tests" | A change to `route_lead.py` is claimed to be covered by tests that test `main.py` | Explicit contract tests for every endpoint. If an endpoint doesn't have a contract test, the agent writes one as part of the task. |

**Guard:** Every task in this document has a `TESTS` section that specifies EXACTLY what tests to write and what they must verify. If the agent completes a task without writing the specified tests, the task is incomplete.

### Failure Mode 7: Production Drift

| Symptom | Real example | Protection |
|---------|-------------|-----------|
| Dev/test code shipped to production | WhatsApp test handler was 180 lines of production code running in a "test" route | Phase 0 removes all test-mode code from production paths. New test code goes in `tests/` only, never in `app/`. |
| DRYRUN accidentally disabled | Someone sets `OUTBOUND_ENABLED=true` and forgets | The test suite sets `OUTBOUND_ENABLED=false` by default. The deploy config also defaults to `false`. Real sending requires explicit opt-in per environment. |
| Debug endpoints accessible in production | `/debug/config` exposes API keys | Phase 6 adds a feature flag. Debug endpoints return 404 when `DEBUG_ENDPOINTS_ENABLED=false`. |

**Guard:** Before any deploy:
1. Run `OUTBOUND_ENABLED=true pytest` — confirm tests skip (not fail)
2. Check `/debug/config` returns 404
3. Check no test-mode routes exist in `app/main.py`
4. Check `.env.example` has all required fields with placeholder values

---

## PHASE 0: Cleanup (30 min)

### Task 0.1: Remove .claude/ scaffolding
**WHAT:** The AI agents added 50+ files of swarm coordination scaffolding that isn't part of the product.
**WHERE:** `.claude/`, `.claude-flow/`
**FIX:**
```bash
# Add to .gitignore
echo ".claude/" >> .gitignore
echo ".claude-flow/" >> .gitignore
echo ".mcp.json" >> .gitignore
echo "HTTP" >> .gitignore
echo "*.db" >> .gitignore
```
Or remove entirely:
```bash
rm -rf .claude/ .claude-flow/ .mcp.json HTTP
```
**VERIFY:** `git status` shows no scaffolding files.
**DEPENDS:** None.

### Task 0.2: Remove test-mode WhatsApp handler
**WHAT:** `_handle_customer_whatsapp_test()` in `app/main.py` is ~180 lines of production code in a test-mode handler. Duplicates logic from SMS handler.
**WHERE:** `app/main.py`
**FIX:** Delete the entire `_handle_customer_whatsapp_test()` function and its route. If WhatsApp handling is needed, route through the existing SMS handler or create a shared handler.
**VERIFY:** App starts without errors. WhatsApp messages still work through the normal handler.
**DEPENDS:** None.

---

## PHASE 1: Critical Bugs (1 hour)

### Task 1.1: Fix daily digest crash
**WHAT:** `send_daily_digest()` in `app/scheduler.py` references undefined `dealer` variable at line ~424. Will crash when the job runs.
**WHERE:** `app/scheduler.py` — `send_daily_digest()` function
**FIX:** The function takes `dealer_slug` as a parameter but uses `dealer.id` inside. Fix:
```python
def send_daily_digest(dealer_slug: str):
    # Load the dealer
    dealer = session.query(Dealer).filter(Dealer.slug == dealer_slug).first()
    if not dealer:
        return
    # Now dealer.id is available
    ...
```
**VERIFY:** Call `send_daily_digest("premier-auto-group")` manually. Confirm it doesn't crash.
**DEPENDS:** None.

### Task 1.2: Fix greeting_only mode bypassing lifecycle
**WHAT:** `conversation.py` sets `lead.state = LeadState.ASSIGNED` directly without using `transition()`. Bypasses state change logging.
**WHERE:** `app/engine/conversation.py` — greeting_only mode handling
**FIX:** Replace direct state assignment with lifecycle transition:
```python
# Instead of:
lead.state = LeadState.ASSIGNED

# Use:
from app.engine.lifecycle import transition
transition(lead, LeadState.ASSIGNED, session, reason="greeting_only_mode")
```
**VERIFY:** Trigger greeting_only mode. Check that LeadEvent is created for the state change.
**DEPENDS:** None.

### Task 1.3: Fix pass_count not persisted
**WHAT:** `pass_count` is set as a runtime attribute via `getattr(lead, "pass_count", 0) + 1`. May be lost on session refresh.
**WHERE:** `app/engine/router.py` — `handle_pass()` function
**FIX:** Ensure `pass_count` is a proper column on the Lead model:
```python
# In app/models/__init__.py
class Lead:
    ...
    pass_count: int = Field(default=0)
```
Then in `handle_pass()`:
```python
lead.pass_count = (lead.pass_count or 0) + 1
```
**VERIFY:** Pass a lead 3 times. Query the database directly. Confirm `pass_count` is persisted.
**DEPENDS:** Alembic migration (Phase 2).

### Task 1.4: Fix phone masking in email adapter
**WHAT:** `email_lead.py` masks phone at parse time (line 49). Same bug fixed in `route_lead.py` but missed here.
**WHERE:** `app/adapters/intake/email_lead.py` line 49
**FIX:** Replace `mask_phone(_normalize_phone(...))` with `normalize_phone(...)`. Store unmasked, mask at display time.
**VERIFY:** Parse test email with phone. Confirm stored unmasked in DB.
**DEPENDS:** None.

### Task 1.5: Fix consent=False in email adapter
**WHAT:** `email_lead.py` sets `consent=False` on line 79. Listing site inquiries have implied consent.
**WHERE:** `app/adapters/intake/email_lead.py` line 79
**FIX:** Change `consent=False` to `consent=True`.
**VERIFY:** Parse test email. Confirm `consent=True` in DB.
**DEPENDS:** None.

---

## PHASE 2: Database & Migrations (1 hour)

### Task 2.1: Install Alembic
**WHAT:** No migration tool exists. Schema changes require manual intervention.
**WHERE:** Project root
**FIX:**
```bash
pip install alembic
alembic init alembic
```
Edit `alembic/env.py` to import `app.models` and set `target_metadata`.
Edit `alembic.ini` to use `DATABASE_URL` from env.
**VERIFY:** `alembic revision --autogenerate -m "test"` creates a migration file.
**DEPENDS:** None.

### Task 2.2: Create initial migration
**WHAT:** Need a baseline migration that matches the current schema.
**WHERE:** `alembic/versions/`
**FIX:**
```bash
alembic revision --autogenerate -m "initial_schema"
alembic upgrade head
```
**VERIFY:** Migration creates all tables. `alembic current` shows head.
**DEPENDS:** Task 2.1.

### Task 2.3: Increase connection pool size
**WHAT:** `app/db.py` sets `pool_size=2, max_overflow=2`. Too small for production.
**WHERE:** `app/db.py` — `_pool_kwargs()` function
**FIX:**
```python
def _pool_kwargs(url: str) -> dict:
    if _is_sqlite(url):
        return {}
    return {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
```
**VERIFY:** Monitor connection count under load. Should not see "connection pool exhausted" errors.
**DEPENDS:** None.

### Task 2.4: Remove duplicated `_normalize_db_url`
**WHAT:** Same function in `app/db.py` and `app/scheduler.py`.
**WHERE:** `app/db.py`, `app/scheduler.py`
**FIX:** Keep it in `app/db.py` only. Import from there in `scheduler.py`:
```python
from app.db import _normalize_db_url
```
**VERIFY:** App starts without import errors.
**DEPENDS:** None.

---

## PHASE 3: Transaction Safety (2 hours)

### Task 3.1: Add future-date validation to appointments
**WHAT:** `book_appointment()` can book appointments in the past.
**WHERE:** `tools/book_appointment.py`
**FIX:**
```python
from datetime import datetime, timezone

def book_appointment(lead_id, scheduled_for, ...):
    if scheduled_for < datetime.now(timezone.utc):
        raise ValueError("Cannot book appointment in the past")
    ...
```
**VERIFY:** Try to book an appointment for yesterday. Confirm it raises ValueError.
**DEPENDS:** None.

### Task 3.2: Fix handle_claim to verify rep identity
**WHAT:** Any rep can claim any ASSIGNED lead, not just the assigned one.
**WHERE:** `app/engine/router.py` — `handle_claim()` function
**FIX:**
```python
def handle_claim(lead, rep_name, session):
    if lead.assigned_rep and lead.assigned_rep != rep_name:
        raise ValueError(f"Lead is assigned to {lead.assigned_rep}, not {rep_name}")
    lead.assigned_rep = rep_name
    transition(lead, LeadState.CLAIMED, session, reason="rep_claimed")
```
**VERIFY:** Try to claim a lead assigned to another rep. Confirm it raises ValueError.
**DEPENDS:** None.

### Task 3.3: Wrap `ingest_lead()` in a single transaction
**WHAT:** If AI proactive follow-up fails after lead is committed, lead is stuck in AUTO_REPLIED with no follow-up.
**WHERE:** `tools/route_lead.py` — `ingest_lead()` function
**FIX:** Ensure the entire pipeline (dedup → persist → auto-reply → AI follow-up → ENGAGED) is in a single transaction. If any step fails, roll back everything.
```python
def ingest_lead(...):
    try:
        # All steps
        session.commit()
    except Exception:
        session.rollback()
        raise
```
**VERIFY:** Write a test that simulates AI follow-up failure. Confirm lead is NOT in database after rollback.
**DEPENDS:** None.

---

## PHASE 4: Transport Abstraction (2 hours)

### Task 4.1: Create transport interface
**WHAT:** Twilio is hardcoded as the only SMS/WhatsApp transport.
**WHERE:** `tools/send_sms.py`, `app/transports/twilio.py`
**FIX:**
```python
# app/transports/base.py
from abc import ABC, abstractmethod

class Transport(ABC):
    @abstractmethod
    def send_sms(self, to: str, body: str, from_number: str) -> str:
        pass
    
    @abstractmethod
    def send_whatsapp(self, to: str, body: str, from_number: str, template_sid: str = None) -> str:
        pass
```
**VERIFY:** `send_sms.py` imports and uses `Transport` interface.
**DEPENDS:** None.

### Task 4.2: Add Telegram transport
**WHAT:** Architecture decision: Telegram = dealer-facing. Never built.
**WHERE:** New file `app/transports/telegram.py`
**FIX:**
```python
# app/transports/telegram.py
import httpx

class TelegramTransport:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
    
    async def send_message(self, chat_id: str, text: str, parse_mode: str = "Markdown"):
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/sendMessage", json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode
            })
            return resp.json()
```
Add `telegram_chat_id` to dealer YAML config (sales_team entries).
**VERIFY:** Send a test notification to your own Telegram.
**DEPENDS:** Task 4.1.

### Task 4.3: Wire Telegram into `notify_rep.py`
**WHAT:** `notify_rep.py` currently only supports WhatsApp. Replace with Telegram-only. Twilio is customer-facing ONLY — never used for dealer notifications.
**WHERE:** `tools/notify_rep.py`
**FIX:** Remove all WhatsApp dealer notification code. Telegram is the ONLY dealer channel:
```python
def notify_rep(lead, dealer_config, message):
    # Telegram is the ONLY dealer notification channel
    chat_id = dealer_config["sales_team"][lead.assigned_rep]["telegram_chat_id"]
    telegram_transport.send_message(chat_id, message)
```
**VERIFY:** Trigger appointment. Confirm Telegram notification arrives. Confirm no WhatsApp message is sent to dealer.
**DEPENDS:** Task 4.2.

---

## PHASE 5: Fix Stubs (2 hours)

### Task 5.1: Wire email intake to a provider
**WHAT:** `email_lead.py` adapter exists but isn't connected to any email provider.
**WHERE:** `app/adapters/intake/email_lead.py`
**FIX:** Start with IMAP polling:
```python
# In scheduler.py
scheduler.add_job(poll_inbox, 'interval', minutes=5, args=[dealer_config])
```
**VERIFY:** Send AutoTrader-style email to test inbox. Confirm lead is created.
**DEPENDS:** None.

### Task 5.2: Fix settings save buttons
**WHAT:** `settings.html` buttons call `showToast()` but don't persist.
**WHERE:** `app/dashboard/templates/settings.html`, `app/dashboard/__init__.py`
**FIX:** Wire save buttons to POST endpoints:
```python
@router.post("/dashboard/settings/business")
async def save_business_info(request: Request, ...):
    # Update dealer config
    pass
```
**VERIFY:** Change business name in settings. Reload page. Confirm it persists.
**DEPENDS:** None.

### Task 5.3: Fix hardcoded WhatsApp template SID
**WHAT:** Different dealers need different templates.
**WHERE:** `tools/route_lead.py`
**FIX:** Move to dealer config:
```yaml
channels:
  whatsapp:
    auto_reply_template: "HX4ec87aebc636f28e34c42d57e3112320"
```
**VERIFY:** Change template SID in config. Trigger WhatsApp lead. Confirm new template is used.
**DEPENDS:** None.

---

## PHASE 6: Rate Limiting & Auth (30 min)

### Task 6.1: Add rate limiting to webhook endpoints
**WHAT:** Only admin login is rate-limited. Webhook endpoints are unprotected.
**WHERE:** `app/main.py` — all webhook routes
**FIX:**
```bash
pip install slowapi
```
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/webhook/sms/inbound")
@limiter.limit("10/minute")
async def sms_inbound(request: Request, ...):
    pass
```
**VERIFY:** Send 11 requests in 1 minute. 11th should return 429.
**DEPENDS:** None.

### Task 6.2: Add expiry to debug endpoints
**WHAT:** Debug endpoints have no removal mechanism.
**WHERE:** `app/main.py` — `/debug/config`, `/debug/dealer/{slug}`
**FIX:** Add a feature flag:
```python
if not settings.debug_endpoints_enabled:
    raise HTTPException(404)
```
Set `DEBUG_ENDPOINTS_ENABLED=false` in production.
**VERIFY:** Debug endpoints return 404 when flag is false.
**DEPENDS:** None.

---

## PHASE 7: Conversation Memory (1 hour)

### Task 7.1: Add conversation summarization
**WHAT:** Long conversations will hit API token limits.
**WHERE:** `app/engine/conversation.py`
**FIX:** When message count > 20, summarize older messages:
```python
def get_conversation_history(lead_id, session, max_messages=10):
    messages = session.query(Message).filter(
        Message.lead_id == lead_id
    ).order_by(Message.created_at.desc()).limit(max_messages).all()
    
    if len(messages) >= max_messages:
        older = session.query(Message).filter(
            Message.lead_id == lead_id,
            Message.id < messages[-1].id
        ).all()
        summary = summarize_messages(older)
        return [{"role": "system", "content": f"Previous summary: {summary}"}] + messages
    
    return messages
```
**VERIFY:** Create lead with 30+ messages. Confirm API call stays under token limit.
**DEPENDS:** None.

---

## PHASE 8: Testing (ongoing)

### Task 8.1: Add integration tests for transaction safety
**WHERE:** `tests/test_transaction_safety.py` (new)
**FIX:**
```python
def test_ingest_lead_rolls_back_on_ai_followup_failure():
    """If AI follow-up fails, lead should NOT be in database."""
    pass

def test_dedup_resends_stale_dryrun():
    """Stale DRYRUN leads should be re-sent."""
    pass
```
**VERIFY:** `pytest tests/test_transaction_safety.py` passes.
**DEPENDS:** Task 3.3.

### Task 8.2: Add test for Telegram notifications
**WHERE:** `tests/test_telegram.py` (new)
**FIX:**
```python
def test_telegram_send_message():
    transport = TelegramTransport(bot_token="test")
    with mock.patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = Mock(json=lambda: {"ok": True})
        result = transport.send_message("123", "test")
        assert result["ok"]
```
**VERIFY:** `pytest tests/test_telegram.py` passes.
**DEPENDS:** Task 4.2.

---

## PHASE 9: Email Channel Strategy

Full strategy documented in `EMAIL_STRATEGY.md`. Key decisions:
- Email leads captured via IMAP polling, then routed through SMS/WhatsApp pipeline when phone exists
- No-phone email leads get ONE AI follow-up email + rep handoff (AI done)
- Email replies trigger Telegram notification to rep (different framing than hot leads — 🔵 triage vs 🟢 hot)
- Rep handles email conversation manually via dashboard
- Cascade timing is longer for email leads (24h vs 5min for SMS/WhatsApp)

Read `EMAIL_STRATEGY.md` before implementing any email features.

---

## PHASE 10: Manager vs Rep Roles (3 hours)

Two distinct roles with different dashboards and access levels. Full spec in `ARCHITECTURE.md` under "Roles: Manager vs Rep."

### Task 10.1: Add role to session/auth
**WHAT:** Session stores `{dealer_slug, rep_name, role}` where role = "rep" or "manager".
**WHERE:** `app/admin/` auth module
**FIX:** Manager login uses a separate PIN (configured in dealer YAML under `manager_pin`). Login page shows rep dropdown + PIN field. Manager gets `role="manager"`, reps get `role="rep"`.
**VERIFY:** Log in as manager. Confirm session has `role="manager"`. Log in as rep. Confirm `role="rep"`.
**DEPENDS:** None.

### Task 10.2: Rep-scoped dashboard
**WHAT:** Reps see only their assigned leads + unassigned leads. Cannot see other reps' leads.
**WHERE:** `app/dashboard/`
**FIX:** Add query filter: `if session.role == "rep": query = query.filter(Lead.assigned_rep == session.rep_name or Lead.assigned_rep == None)`. URL guard: `/dashboard/leads/{id}` returns 403 if lead not assigned to logged-in rep.
**VERIFY:** Log in as Rep A. Confirm Rep B's leads are not visible. Confirm lead detail returns 403 for Rep B's leads.
**DEPENDS:** Task 10.1.

### Task 10.3: Manager dashboard with team visibility
**WHAT:** Manager sees ALL leads with rep filter dropdown. Can reassign, approve transfers, see team stats.
**WHERE:** `app/dashboard/`
**FIX:** Add "Team Leads" tab with rep filter. Add reassign action (with reason field + audit trail in LeadEvent). Add transfer approval flow.
**VERIFY:** Log in as manager. Filter by rep. Reassign a lead. Confirm LeadEvent logs the reassignment with reason.
**DEPENDS:** Task 10.1.

### Task 10.4: Lead transfer workflow
**WHAT:** Rep can request transfer (goes to manager). Manager can reassign directly.
**WHERE:** `app/engine/router.py`, `app/dashboard/`
**FIX:** Mode A: Manager reassigns (existing — add reason + audit). Mode B: Rep requests transfer → manager gets Telegram notification → approves/rejects. All transfers logged in LeadEvent.
**VERIFY:** Rep requests transfer. Manager gets Telegram ping. Manager approves. Confirm both events in LeadEvent.
**DEPENDS:** Task 10.3.

---

## PHASE 11: UI Redesign (4 hours)

Full spec in `ARCHITECTURE.md` under "UI/UX Standard." Core principle: utility first, modern aesthetic, premium feel.

### Task 11.1: Design system foundation
**WHAT:** Establish consistent typography, colors, spacing, and component styles.
**WHERE:** `app/dashboard/static/css/` or inline in base.html
**FIX:** Create a design system: Inter font, neutral base (white/gray-50), one accent color (dealer-configurable via YAML), semantic colors (green=warm, blue=cold, red=dead, yellow=attention), 4px spacing grid, subtle card shadows (8px radius), consistent button styles (primary/secondary/danger).
**VERIFY:** All pages use consistent styles. No Bootstrap-looking generic elements.
**DEPENDS:** None.

### Task 11.2: Leads list page redesign
**WHAT:** Current leads list is a basic table. Needs to be information-dense but scannable.
**WHERE:** `app/dashboard/templates/leads.html`
**FIX:** Lead cards or improved table with: customer name, phone, vehicle, state badge (color-coded), time since last activity, source icon (SMS/WhatsApp/Email/Webform). Sortable columns. Filters: by state, by source, by rep (manager only). Sticky header. Zebra striping.
**VERIFY:** Page loads under 1 second. All key info visible at a glance. Filters work. Mobile-responsive.
**DEPENDS:** Task 11.1.

### Task 11.3: Lead detail page redesign
**WHAT:** Current lead detail is basic. Needs conversation thread, vehicle info, actions.
**WHERE:** `app/dashboard/templates/lead_detail.html`
**FIX:** Layout: left panel = conversation thread (SMS/WhatsApp messages + email replies), right panel = lead info (name, phone, email, vehicle, state, assigned rep, timeline). Action buttons: Book Appointment, Transfer, Mark Sold/Lost. Mobile: stack panels vertically.
**VERIFY:** Conversation thread is readable. All lead info visible. Actions work. Mobile layout is usable.
**DEPENDS:** Task 11.1.

### Task 11.4: Sidebar navigation
**WHAT:** Dashboard needs a proper navigation structure.
**WHERE:** `app/dashboard/templates/base.html`
**FIX:** Left sidebar with: Dashboard (home), Leads, Appointments, Inventory, Settings (manager only). Active page highlighted. Collapsible on mobile. Rep sees: Dashboard, Leads, Appointments. Manager sees all + Settings, Team Stats.
**VERIFY:** Navigation works across all pages. Active page is highlighted. Mobile collapses to hamburger menu.
**DEPENDS:** Task 11.1.

### Task 11.5: Login page
**WHAT:** Login needs to be clean and professional.
**WHERE:** `app/dashboard/templates/login.html`
**FIX:** Dealer dropdown (auto-detected from URL or manual selection), rep/manager dropdown, PIN input. Clean centered card layout. Dealer logo if configured.
**VERIFY:** Login flow works for both rep and manager. Page looks professional.
**DEPENDS:** Task 11.1.

### Task 11.6: Dashboard home page
**WHAT:** Landing page after login. Shows what needs attention.
**WHERE:** `app/dashboard/templates/dashboard.html`
**FIX:** Rep view: my leads summary (by state), today's appointments, attention widget (stale leads, no activity). Manager view: team overview, rep comparison, pipeline health, lead source breakdown.
**VERIFY:** Page loads fast. All widgets show real data. Manager and rep see different views.
**DEPENDS:** Task 11.1, Task 10.1.

---

## PHASE 12: Premier Auto Group Dealership Demo Site (8 hours)

> **Goal:** A production-quality dealership demo site that you can interact with to test the full system. Not a static template — a working, interactive site that creates real leads in v5.

### Task 12.1: Research real dealership sites
**WHAT:** Before designing, study the market leaders to understand what real dealership sites do.
**WHERE:** Browser research
**FIX:** Browse 3-5 top dealership sites (OpenRoad, Richmond Auto Mall, or similar BC dealers). Document:
- What pages they have (Inventory, VDP, Financing, Trade-In, About, Contact)
- What forms they use (contact, pre-approval, trade-in value)
- How they display inventory (filters, sorting, photos, pricing)
- What trust signals they show (Carfax, financing partners, reviews)
- How mobile-responsive they are
**VERIFY:** Notes file exists with documented patterns.

### Task 12.2: Vehicle inventory page with filtering
**WHAT:** Replace the current generic inventory grid with a real, interactive inventory page.
**WHERE:** Demo site frontend (Vercel/Next.js or static HTML)
**FIX:** Create a VDP (Vehicle Detail Page) system:
```
/inventory          → Grid of all vehicles with filters (make, model, year, price range)
/inventory/{id}     → Vehicle detail page with: photos, specs, price, features, options, Carfax badge
```
Filters: make, model, body type (Sedan/SUV/Truck/Coupe), price range, year range. Each filter updates the URL params so the state is shareable.

**Requirements:**
- Real photos (not stock images — use placeholder car images with a clear note "Photo Coming Soon" or real stock from inventory YAML)
- Price prominently displayed
- Monthly payment estimate (default: 7% APR, 72 months — note: "estimate only, see finance for details")
- "Get Pre-Approved" CTA on every vehicle card
- "Book Test Drive" button on VDP

**VERIFY:** Navigate to /inventory. Filter by SUV. Confirm only SUVs show. Click a vehicle. VDP loads with specs and pricing.
**DEPENDS:** None.

### Task 12.3: Financing page with pre-approval form
**WHAT:** A full financing page that looks like what real dealerships offer.
**WHERE:** Site frontend, `/financing`
**FIX:** Create a financing page with:
- Financing options overview (bank financing, dealer financing, lease options)
- Monthly payment calculator (loan amount, APR, term → monthly payment)
- Pre-approval form (name, phone, email, desired vehicle, budget, employment info)
- Credit application CTA (note: "pre-approval = soft credit check")
- Lease vs buy comparison

**Backend integration:**
- Pre-approval form POST → `/webhook/form/{token}` → creates lead with tag `"financing"`
- Lead state goes through the full AI pipeline (auto-reply, qualify, book appointment)
- AI is primed with financing knowledge from the AI persona

**VERIFY:** Fill pre-approval form. Submit. Confirm lead is created with tag "financing" in the database.
**DEPENDS:** Task 12.2.

### Task 12.4: Trade-in valuation form
**WHAT:** A trade-in page where customers can get a preliminary valuation.
**WHERE:** Site frontend, `/trade-in`
**FIX:** Create a trade-in page with:
- Trade-in form (year, make, model, trim, mileage, condition, name, phone, email)
- Value estimate display (range based on KBB/Canadian Black Book averages — note this is an estimate, final value after inspection)
- "Get Firm Offer" CTA (schedules in-person appraisal)

**Backend integration:**
- Trade-in form POST → `/webhook/form/{token}` → creates lead with tag `"trade-in"`
- Rep gets Telegram notification with trade-in details
- Lead state: NEW → AUTO_REPLIED → ASSIGNED (rep handles trade-in manually)

**VERIFY:** Fill trade-in form. Submit. Confirm lead is created with tag "trade-in".
**DEPENDS:** Task 12.3.

### Task 12.5: Interactive contact form with full validation
**WHAT:** The existing contact form works but needs to feel like a real dealership experience.
**WHERE:** Site frontend, contact form on all pages
**FIX:** Enhance the contact form with:
- Full field validation: phone format, email format, required fields
- Vehicle of Interest dropdown auto-populated from inventory YAML
- SMS consent checkbox (default unchecked, required to submit)
- Real-time validation errors (not just on submit)
- Success state with expected response time ("We'll respond within 60 seconds")
- CASL-compliant consent text
- Hidden field: `inquiry_type` (general, financing, trade-in, service) — auto-set based on which page submitted from

**POST body format:**
```json
{
  "name": "John Smith",
  "phone": "+16045551234",
  "email": "john@example.com",
  "vehicle_of_interest": "PAG001",
  "message": "I'm interested in the Civic",
  "consent": true,
  "inquiry_type": "general",
  "referrer": "premier-auto-group"
}
```

**VERIFY:** Submit form with invalid phone → error message. Submit with valid data → success state. Check DB for lead.
**DEPENDS:** Task 12.2.

### Task 12.6: Full E2E pipeline test
**WHAT:** Verify that the demo site → v5 backend → AI → appointment pipeline works end-to-end.
**WHERE:** `tests/test_demo_site_e2e.py` (new)
**FIX:**
```python
@pytest.mark.e2e
def test_demo_site_full_pipeline():
    """
    1. Submit webform from demo site with vehicle interest
    2. Verify lead created in DB with correct dealer
    3. Verify auto-reply sent (Message table)
    4. Simulate customer reply to AI
    5. Verify AI qualifies (state = ENGAGED)
    6. Book appointment
    7. Verify state = APPT_SET
    8. Verify Telegram notification sent (not Twilio)
    """
    pass
```
**VERIFY:** `pytest tests/test_demo_site_e2e.py -x --tb=short` passes.
**DEPENDS:** Task 12.5, Phase 4 (transport abstraction).

### Task 12.7: Mobile-responsive design check
**WHAT:** The site must look professional on mobile. Customers browse dealerships on their phone.
**WHERE:** Site frontend, all pages
**FIX:** After building all pages, verify at 3 viewport sizes:
- 375px (iPhone) — no horizontal scroll, readable text, usable forms
- 768px (iPad) — grid adjusts to 2 columns, sidebar collapses
- 1440px (Desktop) — full layout

Use responsive breakpoints: `@media (max-width: 768px)` and `@media (max-width: 480px)`.

**VERIFY:** Load each page at each viewport. Screenshot and confirm no broken layout.
**DEPENDS:** Task 12.5.

---

## Execution Order

```
Phase 0  (Cleanup) ────────────────────────────────── 30 min
Phase 1  (Critical Bugs) ──────────────────────────── 1.5 hours
Phase 2  (Database) ───────────────────────────────── 1 hour
Phase 3  (Transaction Safety) ─────────────────────── 2 hours
Phase 4  (Transport Abstraction) ──────────────────── 2 hours
Phase 5  (Fix Stubs) ──────────────────────────────── 2 hours
Phase 6  (Rate Limiting) ──────────────────────────── 30 min
Phase 7  (Conversation Memory) ────────────────────── 1 hour
Phase 8  (Testing) ────────────────────────────────── ongoing
Phase 9  (Email Channel Strategy) ─────────────────── 10 hours
Phase 10 (Manager/Rep Roles) ──────────────────────── 3 hours
Phase 11 (UI Redesign) ────────────────────────────── 4 hours
Phase 12 (Dealership Demo Site) ───────────────────── 8 hours
                                                    ─────────────
                                                   Total: ~35.5 hours
```

**Critical path:** Phases 0 → 1 → 2 → 3 → 4 → 5 → 12
**Parallel path:** Phases 6, 7, 8 (run alongside any phase after 5)
**New feature:** Phase 9 (email leads) — depends on Phases 0-5 being done first
**New feature:** Phase 10 (manager/rep roles) — depends on Phase 0-1
**New feature:** Phase 11 (UI redesign) — can run in parallel with Phase 10
**New feature:** Phase 12 (dealership demo site) — depends on Phase 5

---

## Key Decisions for the Agent

1. **PostgreSQL is already deployed.** Don't touch the DB migration — it's done.
2. **Telegram is the ONLY dealer notification channel.** No WhatsApp fallback for dealers. Twilio is customer-facing ONLY.
3. **Rep assignment is DEFERRED.** Don't change this — it's a deliberate design choice.
4. **Transport abstraction is mandatory.** Don't hardcode Twilio anywhere except `app/transports/twilio.py`.
5. **One transaction per lead ingestion.** No partial commits.
6. **TDD is mandatory.** Every task: write failing test FIRST (RED), write minimum code to pass (GREEN), refactor (REFACTOR). No fabricated test results. One commit per task.
7. **The daily digest crash is the #1 priority.** It will hit production.
8. **No v6.** The only reason for a v6 is a customer requesting exclusive features. Never because v5 wasn't production-ready.
9. **Before any code change, run the full test suite.** If it doesn't pass, fix the regression before writing new code.
10. **Before creating a new function, search the codebase for existing ones.** Don't duplicate. `search_files(pattern="def your_function_name")`.
11. **Every new config field must exist in BOTH the test fixture AND the real dealer YAML.** Before referencing it in code.
12. **Every import must be verified to exist.** Before writing code that imports it.

---

## Files to Create

| File | Purpose |
|------|---------|
| `alembic/` | Migration infrastructure |
| `app/transports/base.py` | Transport interface |
| `app/transports/telegram.py` | Telegram Bot API wrapper |
| `tests/test_transaction_safety.py` | Transaction safety tests |
| `tests/test_telegram.py` | Telegram transport tests |
| `tests/test_demo_site_e2e.py` | Full E2E pipeline test for demo site |
| Demo site frontend (`/inventory`, `/financing`, `/trade-in`) | Dealership demo site pages |
| `TESTING_STRATEGY.md` | Testing strategy document (reference only, lives at AGENTIC WORKFLOWS/TESTING_STRATEGY.md) |

## Files to Modify

| File | What Changes |
|------|-------------|
| `app/scheduler.py` | Fix daily digest crash, remove duplicate `_normalize_db_url` |
| `app/engine/conversation.py` | Fix greeting_only lifecycle bypass, add conversation summarization |
| `app/engine/router.py` | Fix handle_claim rep verification, persist pass_count |
| `app/models/__init__.py` | Add `pass_count` column to Lead |
| `app/db.py` | Increase pool size |
| `tools/route_lead.py` | Single transaction, fix hardcoded template SID |
| `tools/send_sms.py` | Use transport interface |
| `tools/notify_rep.py` | Replace WhatsApp with Telegram-only (remove all WhatsApp dealer notification code) |
| `tools/book_appointment.py` | Add future-date validation |
| `app/main.py` | Remove test-mode handler, add rate limiting, add debug flag |
| `app/dashboard/templates/settings.html` | Wire save buttons |
| `dealers/premier-auto.yaml` | Add telegram config |
| `.gitignore` | Add .claude/, .claude-flow/, *.db, .env |
| `app/adapters/intake/email_lead.py` | Fix phone masking (line 49), fix consent=False (line 79) |
| `tools/route_lead.py` | Add email routing fork (phone vs no-phone branch) |
| `app/transports/email.py` | NEW — outbound email via SendGrid/Mailgun |
| `app/adapters/intake/email_parsers/` | NEW — site-specific parsers (AutoTrader, CarGurus, Kijiji) |

---

## Execution Contract (Copy for every session)

```
Before coding:
  [ ] Read TESTING_STRATEGY.md
  [ ] Read this REFACTORING_GUIDE.md
  [ ] Run full test suite → all pass
  [ ] Identify exact file + line for this task
  [ ] Verify imports/functions/config fields exist (search the codebase)

During coding:
  [ ] Write RED test first → confirm it FAILS
  [ ] Write minimum code to pass
  [ ] Run RED/GREEN → confirm it PASSES
  [ ] Run full test suite → no regressions
  [ ] Verify all 3-passes (happy, guard, idempotent)

After coding:
  [ ] Commit with message "Phase X.Y: description"
  [ ] Update NEXT_SESSION_PROMPT.md with current state
  [ ] Report: what passed, what tests were added, what's next
```

---

*Last updated: 2026-06-19. Based on live GitHub codebase (origin/main, commit c4ca0ff).*
*Testing strategy: `AGENTIC WORKFLOWS/TESTING_STRATEGY.md`*
*Desktop setup: `AGENTIC WORKFLOWS/DESKTOP_SETUP.md`*
*Master doctrine: `CLAUDE.md` in AGENTIC WORKFLOWS root*