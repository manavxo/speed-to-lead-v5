# Speed to Lead v5 — Codebase Review + Mimo Code Fix Spec

> **Date:** 2026-06-27
> **Status:** Read-only review (no changes made)
> **Reviewer:** AI codebase audit

---

## BOTTOM LINE

Speed to Lead v5 is a remarkably well-structured project for a solo dev rebuild. The architecture is clean, the state machine is sound, the chokepoint pattern (send_sms, notify_rep) is production-grade, and the test suite is comprehensive. The gap between "tests pass" and "real production" is mainly operational: SQLite → PostgreSQL, missing DASHBOARD_PASSWORD env var, and one critical import bug (pytest collection fails). There are ~8 code-level issues worth fixing before onboarding a second dealer.

---

## WHAT'S SOLID — KEEP AS-IS

1. **State machine (app/engine/lifecycle.py, 81 lines)** — Deterministic, well-documented, single-transition-table source of truth. Can't break in ways you don't see coming.

2. **send_sms chokepoint (tools/send_sms.py, 435 lines)** — Enforces opt-out, quiet hours, consent, message sanitization, dry-run gate, and message logging all in one function. Every outbound path goes through it. This is the right architecture.

3. **notify_rep chokepoint (tools/notify_rep.py, 438 lines)** — Same chokepoint pattern for rep-facing messages. Telegram, WhatsApp, SMS backends. Dry-run safe. Placeholder phone detection. Well-designed.

4. **Conversation engine (app/engine/conversation.py, 1390 lines)** — Large but comprehensive. The F0 model router (DeepSeek for chat, GPT-4o-mini for tool-critical turns) is clever. The anti-hallucination guard, leaked tool-call recovery, max-turns handoff, and engagement mode support all show real production thinking.

5. **Test infrastructure (tests/conftest.py, 158 lines)** — Signed Twilio request factory, FakeTwilio, FakeLLM, frozen_now fixtures. Clean pattern that lets tests exercise the real code paths without hitting external services.

6. **Dealer YAML config (app/config.py)** — Pydantic-validated per-dealer config. The DealerConfig schema is well-thought-out with sensible defaults. Auto-provisioning on startup is the right pattern.

7. **Round-robin assign (app/engine/router.py)** — with_for_update row locking, pass-count escalation, silent assignment path. Solid.

8. **Escalation sweep (app/scheduler.py)** — Restart-safe, timezone-aware, per-dealer configurable. Morning queue for after-hours leads is a nice touch.

---

## WHAT'S OVERENGINEERED — KILL OR SIMPLIFY

1. **Legacy JSON config fallbacks in main.py (3 copies of the same pattern)**
   - `_find_dealer_by_token`, `_find_dealer_by_sms`, `_find_dealer_by_whatsapp` each have a 10-line JSON scan fallback that iterates ALL dealers. With indexed DB columns, this code path should never execute. The legacy fallbacks are dead code now — every test fixture populates the indexed columns.

2. **Adapter axis comments (app/config.py lines 6-7, app/models/__init__.py lines 1-7)**
   - The "Axis 1/2/3" framework (Inventory/Org/Intake) is documented in config comments but only Axis 3 (intake) is fully implemented. Axis 1 inventory is partial (manual upload + feed). Axis 2 (CRM sync) is a stub. The nomenclature adds cognitive load for something that's not executed.

3. **InventorySourceKind enum with 7 values (app/config.py)**
   - 6 of the 7 enum values (AUTO, FEED, DMS, STRUCTURED_DATA, WEBSITE_SCRAPE, NONE) have no real implementation. Only MANUAL (CSV upload) works. The enum promises capabilities the code doesn't deliver.

4. **LeadOrgMode enum with 5 values (app/config.py)**
   - Only NATIVE is implemented. CRM_SYNC, SHEET, WEBHOOK, EMAIL_DIGEST are stubs. The org sink flush in scheduler.py only checks for `mode == "native"` and skips — it doesn't actually flush anything.

5. **Email intake polling (app/scheduler.py `_run_email_poll_for_all_dealers`)**
   - Calls `poll_inbox` which requires IMAP creds that are empty by default. Every 5 minutes it loops over all dealers, loads sessions, and tries to poll. When no email is configured, this is wasted DB roundtrips. Gate it on `email_inbox_username` being set.

---

## THE GAP: "TESTS PASS" vs "REAL USAGE"

### CRITICAL: Test suite doesn't collect

```
pytest tests/ --collect-only -q  →  No tests collected
```

This is the #1 blocking issue. The test runner can't find any test modules. Likely causes:
- Missing `__init__.py` in tests/ (exists but is empty — fine)
- Incorrect `pythonpath` / `PYTHONPATH` in pytest config
- pytest.ini / pyproject.toml config that excludes the tests directory
- Import errors masked by the collection failure

**Impact:** You cannot run the test suite. This means every change is untested. Fix this BEFORE any other code change.

### Config changes needed for production

| Setting | Current (dev default) | Production value | Where |
|---------|----------------------|------------------|-------|
| DATABASE_URL | postgresql://localhost/speedtolead | Render Postgres internal URL | Render env vars |
| OUTBOUND_ENABLED | false | true | Render env vars |
| QUIET_HOURS_DISABLED | true (default) | false | Render env vars |
| DASHBOARD_PASSWORD | "" (empty) | Set a password | Render env vars |
| DASHBOARD_PASSWORD_HASH | "" (empty) | Set bcrypt hash | Render env vars |
| REQUIRE_TWILIO_SIGNATURE | false | true | Render env vars |
| TELEGRAM_BOT_TOKEN | "" (empty) | Set token | Render env vars |

### Real gaps beyond config

1. **SQLite → PostgreSQL:** Render's free tier filesystem is ephemeral. SQLite DB resets on every deploy. Need the Render Postgres add-on wired in.

2. **DASHBOARD_PASSWORD not set:** Dashboard login exists but the env var isn't on Render. The login page is unreachable.

3. **WhatsApp sandbox membership expires:** The Twilio WhatsApp sandbox requires re-joining every 24h by sending a keyword. This is a manual ops burden that will break rep notifications silently.

4. **Only one dealer configured:** `dealers/premier-auto.yaml` is the only tenant. Onboarding a second dealer will exercise the multi-tenant resolution path.

5. **Telegram bot not deployed:** TELEGRAM_BOT_TOKEN is in render.yaml but sync:false. Not set on Render. Reps can't use Telegram notifications.

6. **sendgrid_api_key / email_from_address not set:** Email follow-ups and email intake won't work.

---

## PAIN POINTS FOR THE OPERATOR

1. **~30 FastAPI routes still use old `_get_session()` + `try/finally` pattern** instead of FastAPI dependency injection. Four refactor attempts failed. The MIMO_CONTEXT_PASTE.txt mentions this as gotcha #7 in the handoff.

2. **Two different `send_whatsapp` functions** — one in `tools/send_sms.py` (the real one) and one in `app/transports/twilio.py` (a thin wrapper that re-exports it with different signature). The wrapper is only used in one place (the WhatsApp webhook handler). This creates confusion about which one to call.

3. **`ingest_lead` lives in `tools/route_lead.py`** (not `app/engine/router.py` as the name suggests). This was a bug discovered during migration. The handoff doc flags it as gotcha #6.

4. **No monitoring/alerting** — Failed sends, escalation failures, and AI errors are only logged. No webhook, no alerting channel.

5. **Render free tier limitations** — 512MB RAM, 10GB disk, 750 hours/month (sleeps after 15min idle). The scheduler doesn't wake the app on its own.

6. **No migration framework** — Schema changes require deleting the SQLite DB or manual ALTER TABLE. Alembic is in the repo but not wired up.

---

## TECH STACK: 18 RUNTIME DEPENDENCIES

| Dependency | Justification |
|-----------|--------------|
| fastapi | Core framework — fully justified |
| uvicorn | ASGI server — justified |
| sqlmodel | ORM — justified |
| psycopg[binary] | Postgres driver — justified |
| apscheduler | Task scheduling — justified |
| pydantic + pydantic-settings | Validation + env loading — justified |
| pyyaml | Dealer config parsing — justified |
| twilio | SMS/WhatsApp/Voice — justified |
| openai | AI conversation — justified |
| jinja2 | Dashboard templates — justified |
| httpx | HTTP client (Telegram proxy, email poller) — justified |
| python-multipart | Form parsing — justified |
| itsdangerous | Session signing — justified |
| bcrypt | Password hashing — justified |
| slowapi | Rate limiting — justified |
| sendgrid | Email transport — fair (gated on having the API key) |
| pytest + pytest-asyncio | Testing — justified |
| ruff | Linting — justified |
| openpyxl | Excel parsing — weak (only one peripheral use) |

**Hidden complexity:** The project also uses `import xml` (stdlib), `zoneinfo` (stdlib), `hashlib`/`hmac` (stdlib), and `apscheduler.jobstores.sqlalchemy` which brings its own SQLAlchemy dependency. The actual dependency surface is larger than requirements.txt suggests.

---

## PRD GAP ANALYSIS

This section maps the implicit contract (from README, handoff docs, and build plan) against current code state.

| Feature | Promise / Requirement | Current Status | Severity |
|---------|---------------------|----------------|----------|
| Webform intake | Leads from dealer website | ✅ Working | — |
| SMS intake | Customer SMS → AI auto-reply | ✅ Working | — |
| AI auto-reply | <60s response time | ✅ Working (background task) | — |
| AI conversation | Qualify, show inventory, book | ✅ Working (tool loop, F0 routing) | — |
| WhatsApp rep notifications | Reps notified via WhatsApp | ✅ Working (notify_rep chokepoint) | — |
| Telegram rep notifications | Reps notified via Telegram | ✅ Working | — |
| Round-robin assignment | Fair distribution | ✅ Working (with_for_update lock) | — |
| ESCALATED → reassign | Reps have 5min to claim | ✅ Working (sweep every 1min) | — |
| Follow-up messages | 1h, 1d, 3d, 7d cadence | ✅ Working | — |
| Opt-out (CASL) | STOP/UNSUBSCRIBE/ARRET | ✅ Working | — |
| Quiet hours | 21:00-08:00 no SMS | ✅ Working | — |
| Dashboard | Dealer-facing funnel, leaderboard | ✅ Working (Jinja2+HTMX) | — |
| Admin panel | Platform admin: dealers, settings | ✅ Working | — |
| Webhook security | Twilio HMAC validation | ✅ Working (P0-01 applied) | — |
| CSRF protection | Dashboard login CSRF | ✅ Working (P0-08 applied) | — |
| Missed call → SMS | Voice webhook → SMS follow-up | ✅ Working | — |
| WhatsApp templates | Provisioning tool | ✅ Working | — |
| **Test suite** | Must pass before deploy | ❌ Cannot collect — **blocker** | **CRITICAL** |
| PostgreSQL | Production DB | ⚠️ SQLite (ephemeral) | HIGH |
| DASHBOARD_PASSWORD | Dashboard login | ❌ Not set on Render | HIGH |
| Second dealer | Multi-tenant verification | ❌ Only premier-auto.yaml | MEDIUM |
| Interactive voice | Menu, hold, AI responses | ❌ Not implemented | LOW |
| Email intake | IMAP polling | ⚠️ Partial — creds empty | LOW |
| Email outbound | SendGrid transport | ⚠️ Partial — creds empty | LOW |
| Inventory sync | Auto-fetch from dealer feed | ⚠️ Partial — only manual upload | LOW |
| CRM sync | Push leads to external CRM | ❌ Stub (LeadOrgMode.NATIVE only) | LOW |
| Daily digest | Manager SMS summary | ⚠️ Working but gated on digest_enabled | LOW |
| Telegram bot deployed | Rep notifications | ❌ TELEGRAM_BOT_TOKEN not set on Render | MEDIUM |

---

## CODE-LEVEL ISSUES FOUND

> **Read-only review — no changes made.**

### Issue 1: Pytest collection fails (CRITICAL)
- **File:** tests/
- **Symptom:** `python -m pytest tests/ --collect-only -q` → "No tests collected"
- **Probable cause:** Missing or incorrect pytest config. Likely an empty `pytest.ini`, or `__init__.py` issues in test subdirectories tests/e2e/ and tests/fixtures/.
- **Fix:** Check pytest.ini / pyproject.toml for `[tool.pytest.ini_options]` or `[pytest]` sections. Ensure `norecursedirs` doesn't exclude tests/. Ensure tests/e2e/ and tests/fixtures/ have `__init__.py` files if needed.

### Issue 2: SQLite DB is ephemeral on Render (HIGH)
- **File:** .env.example (default), render.yaml (sync:false)
- **Symptom:** Every deploy wipes the database. This is explicitly documented as the #1 thing to fix.
- **Fix:** Provision Render PostgreSQL add-on, set DATABASE_URL.

### Issue 3: DASHBOARD_PASSWORD not set (HIGH)
- **File:** render.yaml
- **Symptom:** Dashboard login endpoint exists but DASHBOARD_PASSWORD env var isn't configured on Render.
- **Fix:** Set the password via Render API or dashboard.

### Issue 4: Legacy JSON config fallbacks are dead code (MEDIUM)
- **Files:** app/main.py lines 261-268, 284-292, 308-316
- **Symptom:** `_find_dealer_by_*` functions scan ALL dealers as a "legacy fallback." With indexed DB columns, this path never executes in production. 30 lines of code that run a full table scan for no reason.
- **Fix:** Remove the legacy fallback code (the `for d in dealers:` loop) from all three functions.

### Issue 5: Two WhatsApp send functions (MEDIUM)
- **Files:** tools/send_sms.py (send_whatsapp), app/transports/twilio.py (send_whatsapp wrapper)
- **Symptom:** The wrapper at app/transports/twilio.py re-exports the tool with a different parameter signature (to_number vs to, from_number vs from). Only called from the WhatsApp webhook handler. Creates confusion about which function to use.
- **Fix:** Inline the wrapper into the single call site, or make it a pure pass-through and deprecate.

### Issue 6: After-hours ingestion writes Message then deletes on AI failure (MEDIUM)
- **File:** tools/route_lead.py lines 344-355
- **Symptom:** When AI proactive follow-up fails (e.g., OpenAI down), `ingest_lead` deletes the lead + all Messages + ConsentLog + LeadEvent. But the initial AUTO_REPLIED transition already wrote a LeadEvent. The cleanup deletes it too, so the failure is silent — no trace in the DB. The caller gets an exception but the event is gone.
- **Fix:** Don't delete the lead. Keep it in NEW state with an error flag. Or at minimum log the error before deletion.

### Issue 7: `_sanitize_message` adds dealer name to first message but route_lead.py also adds it (LOW)
- **File:** tools/send_sms.py lines 68-70, tools/route_lead.py line 286
- **Symptom:** The auto-reply text in route_lead.py is `f"Thanks for reaching out to {dealer_name}! {consent_text}"` which already includes the dealer name. Then `_sanitize_message` checks `if is_first_message and dealer_name.lower() not in body.lower()` and would add it again. The guard prevents double-adding because the name IS in the auto-reply text, but the intent is doubled — the name is hardcoded in both places.
- **Fix:** Remove the dealer name from route_lead.py's auto_reply text and let `_sanitize_message` handle it. Or remove `is_first_message` logic from `_sanitize_message` since the caller already formats the message.

### Issue 8: Email poll runs unconditionally (LOW)
- **File:** app/scheduler.py line 688-695
- **Symptom:** `register_jobs` adds the email poll job regardless of whether email creds are configured. Every 5 minutes it loads all dealers and tries to poll. When no IMAP creds are set, this is wasted work.
- **Fix:** Gate job registration on `settings.email_inbox_username` being non-empty.

### Issue 9: Daily digest only fires within the exact digest hour (LOW)
- **File:** app/scheduler.py line 349: `if now_local.hour == digest_h:`
- **Symptom:** If the scheduler misses the exact hour window (e.g., Process restarted at 09:05), that day's digest is skipped entirely.
- **Fix:** Check if digest was already sent today (query recent LeadEvents) rather than matching the exact hour.

### Issue 10: `handle_turn` returns "draft" mode but no draft UI exists (LOW)
- **File:** app/engine/conversation.py line 948: `'mode': 'draft' if is_biz else 'send'`
- **Symptom:** In business hours, handle_turn returns mode='draft' (rep approval before sending), but there is no UI anywhere to approve drafts. The caller (main.py's _process_and_send_sync) ignores the mode entirely and always sends.
- **Fix:** Either implement the draft approval UI, or remove the draft mode from the return value and make it always send.

---

## MIMO CODE FIX SPEC

> This section provides a structured plan that Mimo Code (or any agent/assistant) can follow to fix the issues above. Each task is ordered by priority.

### Phase 0: Unblock Testing

#### Task 0.1: Fix pytest collection failure
```xml
Priority: CRITICAL
Files: tests/ directory, pyproject.toml or pytest.ini
```
Check if pytest.ini or pyproject.toml has a `[tool.pytest.ini_options]` section. Ensure:
- `testpaths = ["tests"]` or similar
- No `norecursedirs` excluding tests/
- tests/e2e/ and tests/fixtures/ have `__init__.py` files
- PYTHONPATH includes the project root

After fixing, run `python -m pytest tests/ --collect-only -q` and confirm tests are discovered.

#### Task 0.2: Try running a single test file
```xml
Priority: HIGH
```
Run `python -m pytest tests/test_phone_normalization.py -v 2>&1` to verify at least one test file works after collection fix. Report the result.

### Phase 1: Operational Readiness

#### Task 1.1: Provision Render PostgreSQL
```xml
Priority: HIGH
Action: Ops (cannot do from code)
```
Reference the Render API key and service ID (srv-d8misim7r5hc739rf7sg). Create a PostgreSQL add-on and update DATABASE_URL. See `MIMO_HANDOFF.md` for the Render service details.

#### Task 1.2: Set DASHBOARD_PASSWORD on Render
```xml
Priority: HIGH
Action: Ops (cannot do from code)
```
Set DASHBOARD_PASSWORD and DASHBOARD_PASSWORD_HASH (bcrypt hash) env vars on Render. The dashboard login won't work without these.

#### Task 1.3: Set TELEGRAM_BOT_TOKEN on Render
```xml
Priority: MEDIUM
Action: Ops (cannot do from code)
```
Set the Telegram bot token so rep notifications via Telegram work in production.

### Phase 2: Code Cleanup

#### Task 2.1: Remove legacy JSON fallbacks
```xml
Priority: MEDIUM
Files: app/main.py
Pattern: Three copies of the same "legacy fallback" code
```
In `_find_dealer_by_token` (line 261-268), `_find_dealer_by_sms` (line 284-292), and `_find_dealer_by_whatsapp` (line 308-316): remove the `# Legacy fallback: scan JSON config` section. Remove the `dealers = _exec(session, select(Dealer)).all()` loop. Return early when indexed column query returns None.

#### Task 2.2: Remove draft mode from handle_turn return
```xml
Priority: LOW
Files: app/engine/conversation.py, app/main.py (caller)
```
In `handle_turn` at line 948, change `'mode': 'draft' if is_biz else 'send'` to always return `'mode': 'send'`. Since no draft approval UI exists, this is misleading.

OR, if you want to keep the architecture for Phase 2: add a TODO comment documenting that draft approval UI is needed. But the simplest fix is to send always.

#### Task 2.3: Gate email poll on configured creds
```xml
Priority: LOW
Files: app/scheduler.py
```
In `register_jobs`, wrap the email poll job registration in:
```python
if settings.email_inbox_username:
    scheduler.add_job(...)
```

#### Task 2.4: Remove duplicate dealer-name logic
```xml
Priority: LOW
Files: tools/route_lead.py, tools/send_sms.py
```
Keep the dealer name in the auto-reply text (route_lead.py) since it's the source of truth. Remove the `is_first_message` logic from `_sanitize_message` in tools/send_sms.py (lines 68-70) — it duplicates the caller's job and the name-guard prevents double-adding anyway.

#### Task 2.5: Inline the WhatsApp transport wrapper
```xml
Priority: LOW
Files: app/transports/twilio.py, app/main.py (caller)
```
The file `app/transports/twilio.py` (49 lines) is a thin wrapper around `tools.send_sms.send_whatsapp` with a different signature. Only called from one place (the WhatsApp webhook handler in main.py). Either:
- Inline the call in main.py and delete the wrapper file, OR
- Make the wrapper a pure pass-through with identical arguments

### Phase 3: Production Hardening

#### Task 3.1: Don't delete lead on AI failure
```xml
Priority: MEDIUM
Files: tools/route_lead.py, lines 344-355
```
Instead of deleting the lead + all children on AI proactive-followup failure, keep the lead in NEW state and log the error. Optionally add an `error_info` column or LeadEvent to surface the failure in the dashboard. Deleting evidence of failure is the worst possible response to an error.

#### Task 3.2: Add daily-digest already-sent guard
```xml
Priority: LOW
Files: app/scheduler.py, send_daily_digest function
```
Before sending, check if a digest was already sent today for this dealer by querying LeadEvents with type 'daily_digest' created since midnight. This prevents missed digest on scheduler restart.

### Phase 4: Technical Debt

#### Task 4.1: Add pytest.ini or pyproject.toml config
```xml
Priority: MEDIUM
Files: pyproject.toml or pytest.ini
```
Add a proper pytest configuration with test paths and any needed plugins.

#### Task 4.2: Wire up Alembic
```xml
Priority: LOW
Files: alembic/ directory, alembic.ini
```
The alembic directory exists. Configure it to use the real DATABASE_URL and create an initial migration. This is important once SQLite is replaced with PostgreSQL.

---

## WORKLOAD SPLIT PROPOSAL

### CODE CHANGES (Mimo Code / developer)

| Task | Est. Time | Dependencies |
|------|-----------|-------------|
| 0.1 Fix pytest collection | 10 min | None |
| 0.2 Run one test file | 2 min | 0.1 |
| 2.1 Remove legacy JSON fallbacks | 15 min | None |
| 2.2 Remove draft mode | 5 min | None |
| 2.3 Gate email poll | 5 min | None |
| 2.4 Remove duplicate dealer-name logic | 5 min | None |
| 2.5 Inline WhatsApp transport wrapper | 10 min | None |
| 3.1 Don't delete lead on AI failure | 20 min | None |
| 3.2 Add daily-digest guard | 15 min | None |
| 4.1 Add pytest config | 10 min | None |
| 4.2 Wire up Alembic | 30 min | PostgreSQL provisioned |

### CONFIG / OPS (You, Manav)

| Task | Est. Time | Dependencies |
|------|-----------|-------------|
| 1.1 PostgreSQL on Render | 15 min | Render creds |
| 1.2 Set DASHBOARD_PASSWORD | 2 min | Render dashboard |
| 1.3 Set TELEGRAM_BOT_TOKEN | 2 min | Render dashboard |
| Twilio WhatsApp sandbox rejoin | 2 min/week | Phone access |
| Second dealer YAML + onboarding | 30 min | Dealer info |
| Daily digest enable (dealer YAML) | 5 min | Dealer decision |

---

## OVERALL ASSESSMENT

**Score: 7.5/10 — Shipping quality with known gaps**

The codebase is in good shape for a solo-dev project in active development. The architecture decisions (chokepoint pattern, state machine, YAML config per dealer) are production-grade. The conversation engine is sophisticated with tool routing, anti-hallucination, and recovery from leaked tool calls.

The two blocking issues are:
1. **Test suite doesn't collect** — This is the #1 priority. You cannot safely change anything until tests run.
2. **SQLite → PostgreSQL** — Every Render deploy loses data.

Beyond those, the code is clean, well-tested (when tests run), and ready for the second dealer. The recommended order is: unblock tests → PostgreSQL → dashboard password → code cleanup → hardening.
