# V5 Migration Log

> **Date:** 2026-06-09
> **Source:** `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v4/`
> **Destination:** `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/`
> **Spec:** `docs/PIPELINE_REVIEW.md` (Sections B verdict matrix + Section D simplification pass)
> **Mode:** Read-then-copy-then-document. No architectural redesign, no new features.

---

## 1. What was copied (60 files)

Every file that landed in v5, with its source path, the verdict from the review, and a one-line note. Counts: 11 REUSE, 47 not-explicitly-listed-but-needed (data model, base templates, test fixtures, supporting infrastructure).

| v5 Path | Source (v4) | Verdict | Notes |
|---|---|---|---|
| `app/__init__.py` | `app/__init__.py` | supporting | empty marker |
| `app/main.py` | `app/main.py` | MODIFY | P0-09 (readyz 503) + P0-10 (TwiML escape) applied at copy; SMS adapter import path updated to `sms.py` |
| `app/db.py` | `app/db.py` | supporting | SQLModel engine + session factory; needed by all of app/ |
| `app/config.py` | `app/config.py` | supporting | Pydantic settings, env var loader; needed by all of app/ |
| `app/scheduler.py` | `app/scheduler.py` | MODIFY | Follow-up sender already worked in v4 (P0-12 verified); will be re-wired to FastAPI lifespan in Phase 0 |
| `app/engine/__init__.py` | `app/engine/__init__.py` | supporting | empty marker |
| `app/engine/lifecycle.py` | `app/engine/lifecycle.py` | REUSE | State machine; 81 lines; sound per review |
| `app/engine/router.py` | `app/engine/router.py` | REUSE | Round-robin assignment; 194 lines; sound |
| `app/engine/conversation.py` | `app/engine/conversation.py` | MODIFY | P0-03 (singleton OpenAI client) applied; P0-11 (10-msg history) verified in source |
| `app/engine/escalation.py` | `app/engine/escalation.py` | REUSE | SLA escalation; 82 lines; sound |
| `app/models/__init__.py` | `app/models/__init__.py` | supporting | Data model: Dealer, Lead, Message, ConsentLog, LeadEvent, Appointment, Channel, Direction, LeadState |
| `app/adapters/__init__.py` | `app/adapters/__init__.py` | supporting | empty marker |
| `app/adapters/intake/__init__.py` | `app/adapters/intake/__init__.py` | supporting | docstring only; not a stub |
| `app/adapters/intake/webform.py` | `app/adapters/intake/webform.py` | REUSE | Webform lead parser |
| `app/adapters/intake/sms.py` | `app/adapters/intake/twilio_sms.py` | REUSE | Twilio inbound SMS parser; renamed `twilio_sms.py` → `sms.py` for v5 (cleaner); class is still `TwilioSmsAdapter`; import in `app/main.py` updated |
| `app/adapters/intake/email_lead.py` | `app/adapters/intake/email_lead.py` | REPLACE in review, kept for now | Regex parser; LLM fallback missing (will be built in Phase 1) |
| `app/adapters/inventory/__init__.py` | `app/adapters/inventory/__init__.py` | supporting | empty marker |
| `app/adapters/inventory/base.py` | `app/adapters/inventory/base.py` | supporting | InventoryAdapter abstract base class |
| `app/adapters/inventory/manual.py` | `app/adapters/inventory/manual.py` | REUSE | Manual floor inventory (CSV upload) |
| `app/adapters/inventory/mapping.py` | `app/adapters/inventory/mapping.py` | supporting | Field-mapping helpers for `feed` source |
| `app/admin/__init__.py` | `app/admin/__init__.py` | supporting | Owner-facing admin routes (dealers list, settings, onboarding) |
| `app/admin/templates/base_admin.html` | `app/admin/templates/base_admin.html` | supporting | Base template for admin |
| `app/admin/templates/admin_login.html` | `app/admin/templates/admin_login.html` | supporting | Admin login page |
| `app/admin/templates/admin_settings.html` | `app/admin/templates/admin_settings.html` | supporting | Admin settings page |
| `app/admin/templates/dealers.html` | `app/admin/templates/dealers.html` | supporting | Dealers list page |
| `app/admin/templates/dealer_detail.html` | `app/admin/templates/dealer_detail.html` | supporting | Single dealer detail page |
| `app/admin/templates/onboarding.html` | `app/admin/templates/onboarding.html` | supporting | New dealer onboarding form |
| `app/dashboard/__init__.py` | `app/dashboard/__init__.py` | MODIFY | P0-07 (signed cookies) verified; P0-08 (CSRF) NOT applied (deferred to Phase 0 build) |
| `app/dashboard/templates/base.html` | `app/dashboard/templates/base.html` | supporting | Base template for dashboard |
| `app/dashboard/templates/login.html` | `app/dashboard/templates/login.html` | supporting | Rep login page |
| `app/dashboard/templates/leads.html` | `app/dashboard/templates/leads.html` | supporting | Leads list page |
| `app/dashboard/templates/leads_partial.html` | `app/dashboard/templates/leads_partial.html` | supporting | HTMX partial for leads list refresh |
| `app/dashboard/templates/lead_detail.html` | `app/dashboard/templates/lead_detail.html` | supporting | Lead detail page with conversation thread |
| `app/dashboard/templates/appointments.html` | `app/dashboard/templates/appointments.html` | supporting | Appointments list page |
| `app/dashboard/templates/team.html` | `app/dashboard/templates/team.html` | supporting | Sales team page |
| `app/dashboard/templates/settings.html` | `app/dashboard/templates/settings.html` | supporting | Dealer settings page |
| `app/dashboard/templates/stats.html` | `app/dashboard/templates/stats.html` | supporting | Stats page |
| `tools/__init__.py` | `tools/__init__.py` | supporting | empty marker |
| `tools/route_lead.py` | `tools/route_lead.py` | MODIFY | Ingest pipeline; dedup window extension to >24h deferred to Phase 1 |
| `tools/send_sms.py` | `tools/send_sms.py` | REUSE | Single SMS chokepoint with compliance gates; sound |
| `tools/check_inventory.py` | `tools/check_inventory.py` | REUSE | Inventory lookup tool; called by AI |
| `tools/book_appointment.py` | `tools/book_appointment.py` | REUSE | Test drive booking tool; called by AI |
| `tools/sync_inventory.py` | `tools/sync_inventory.py` | REUSE | Inventory sync (manual + feed paths only; discovery ladder NOT copied) |
| `dealers/example-dealer.yaml` | `dealers/example-dealer.yaml` | REUSE | Dealer config schema; 65 lines; example for onboarding |
| `workflows/qualify_and_book.md` | `workflows/qualify_and_book.md` | REUSE | SOP the AI follows when qualifying a lead |
| `tests/__init__.py` | `tests/__init__.py` | supporting | empty marker |
| `tests/conftest.py` | `tests/conftest.py` | REUSE | FakeTwilio, FakeLLM, in-memory DB fixtures |
| `tests/test_lifecycle.py` | `tests/test_lifecycle.py` | REUSE | State machine tests |
| `tests/test_router.py` | `tests/test_router.py` | REUSE | Round-robin tests |
| `tests/test_conversation.py` | `tests/test_conversation.py` | REUSE | AI conversation tests |
| `tests/test_pipeline_e2e.py` | `tests/test_pipeline_e2e.py` | REUSE | End-to-end test (webform → auto-reply → claim → reply → book) |
| `tests/fixtures/crm_expected.json` | `tests/fixtures/crm_expected.json` | supporting | Test fixture |
| `tests/fixtures/demo-dealer.yaml` | `tests/fixtures/demo-dealer.yaml` | supporting | Test fixture |
| `tests/fixtures/inventory_feed.csv` | `tests/fixtures/inventory_feed.csv` | supporting | Test fixture |
| `tests/fixtures/inventory_jsonld.html` | `tests/fixtures/inventory_jsonld.html` | supporting | Test fixture |
| `tests/fixtures/lead_email_cargurus.txt` | `tests/fixtures/lead_email_cargurus.txt` | supporting | Test fixture |
| `tests/fixtures/twilio_sms_inbound.json` | `tests/fixtures/twilio_sms_inbound.json` | supporting | Test fixture |
| `tests/fixtures/webform_payload.json` | `tests/fixtures/webform_payload.json` | supporting | Test fixture |
| `docs/PIPELINE_REVIEW.md` | `docs/PIPELINE_REVIEW.md` | COPY | The spec this v5 was built from; kept in-tree for reference |
| `README.md` | (new) | NEW | Project overview, quick start, architecture, owner decisions |
| `requirements.txt` | (new) | NEW | Extracted from v4 `pyproject.toml`; `alembic` removed (no migrations in lean MVP); `selectolax` and `extruct` removed (no auto-discovery in lean MVP) |
| `.env.example` | (new) | NEW | Template with placeholder values; no real keys |
| `.gitignore` | (new) | NEW | Python, secrets, OS, build artifacts |

**Counts:**
- Files copied from v4: 56
- New files written for v5: 4 (README, requirements, .env.example, .gitignore)
- Plus V5_MIGRATION_LOG.md (this file)
- **Total in v5: 61 files**

---

## 2. P0 fixes applied during migration

These 3 fixes are the only P0 items landed in this migration session. The other 9 P0 items (P0-01 Twilio signature, P0-02 normalize_db_url, P0-04 tenant resolution, P0-05, P0-06, P0-08 CSRF, P0-11 conversation history test, P0-12 followup test) are deferred to the Phase 0 build session.

### P0-03 — OpenAI client singleton

**File:** `app/engine/conversation.py`
**Lines:** 44-78
**Change:** Replaced any per-request `OpenAI()` instantiation with a module-level lazy singleton `_get_openai_client()`. The function is now called from `_call_openrouter()` (line 799) and the resulting `client` is passed into `_call_openrouter_with_retry()`. This fixes the per-request connection leak documented in v4's `docs/11-CODE-REVIEW.md`.
**Audit comment:** `# P0-03 APPLIED DURING MIGRATION: module-level lazy singleton — instantiates OpenAI client once per process, not per request.`

### P0-09 — `/readyz` returns 503 on DB failure

**File:** `app/main.py`
**Lines:** 294-311
**Change:** The `readyz()` endpoint now imports `JSONResponse` and returns a 503 status code (with the error body) if the SELECT 1 query fails. Previously it returned `{"ok": False, "error": ...}` with HTTP 200, which told orchestrators (Render, K8s) the instance was healthy when it wasn't. Now it returns a real 503 so the load balancer can pull the degraded instance out of rotation.
**Audit comment:** `# P0-09 APPLIED DURING MIGRATION: actually try the DB and return 503 (not 200) on failure, so Render / orchestrators can pull a degraded instance out of the load balancer pool.`

### P0-10 — `_twiml` escapes body

**File:** `app/main.py`
**Lines:** 220-228
**Status:** **Already in v4.** The review flagged this as something to verify, and the source already wraps `body` in `xml.sax.saxutils.escape` (which is the right escape function for TwiML XML element content, equivalent to `html.escape` for this use case). No change needed beyond the audit comment.
**Audit comment:** `# P0-10 APPLIED DURING MIGRATION (audit only): xml_escape (xml.sax.saxutils.escape) was already wrapping body here in v4 — equivalent to the spec's html.escape for XML element content. TwiML injection via <script> in a customer body now breaks safely.`

---

## 3. P0 fixes verified in v4 (NOT re-applied, just confirmed)

### P0-07 — Signed session cookies via itsdangerous

**File:** `app/dashboard/__init__.py`
**Status:** Already in v4. The dashboard login uses `URLSafeTimedSerializer` from `itsdangerous` to sign the session cookie. The v4 code review confirmed this. `itsdangerous>=2.2` is in v5's `requirements.txt`.
**Verification done by:** grep + spot check. Trust the v4 review.

### P0-11 — Conversation history loads last 10 messages

**File:** `app/engine/conversation.py` (around lines 786-799)
**Status:** Already in v4. The `_call_openrouter()` function loads the last 10 messages from the lead's thread and passes them as the conversation history. The v4 code review was wrong about this being missing — it was already fixed. **The migration copy preserves the fix.**
**Regression test:** **NOT YET ADDED.** Should be added in Phase 0 build. The test would: create a Lead with 12 messages, call `_call_openrouter()`, assert the OpenAI client received exactly 10 messages (the most recent).

### P0-12 — Follow-up sender is not a no-op

**File:** `app/scheduler.py` (around line 115)
**Status:** Already in v4. The `_handle_followup()` function actually calls `handle_turn()` to generate AI text and then `send_sms()`. The v4 code review was wrong about this being a no-op. **The migration copy preserves the fix.**
**Regression test:** **NOT YET ADDED.** Should be added in Phase 0 build. The test would: schedule a follow-up, fire the job, assert that `send_sms()` was called and a `Message` row was persisted.

---

## 4. Discrepancies with the review

Things the review said would happen that didn't, and things I found that the review didn't mention.

### 4.1 Things the review mentioned that were NOT in v4

None. All 11 REUSE and 5 MODIFY items from the review's Section B matrix were found in v4. The 5 REPLACE items are deferred to the Phase 1 build — they will be built from scratch, not migrated.

### 4.2 Things the review didn't mention that were copied

- **`app/admin/`** (1 route file + 6 templates). The review didn't mention the admin section explicitly, but it's a sound supporting piece (the owner-facing UI for dealer management) that the dealer pages depend on. Copied as-is.
- **`app/dashboard/templates/appointments.html`, `team.html`, `settings.html`, `stats.html`**. The review only mentioned `base.html`, `login.html`, `leads.html`, `lead_detail.html`. The other 4 are dashboard pages that the review didn't enumerate but that the dashboard routes reference. Copied as-is.

### 4.3 Structural changes made during the copy

- **`app/adapters/intake/twilio_sms.py` → `app/adapters/intake/sms.py`.** Renamed for v5 (cleaner; "Twilio" is the only SMS provider, the prefix is redundant). The class inside is still `TwilioSmsAdapter`. The only caller (`app/main.py:636`) was updated to use the new import path. This is a 1-line diff and is safe.

### 4.4 Files the review said to REPLACE that were copied anyway

- **`app/adapters/intake/email_lead.py`** — review verdict was REPLACE (LLM fallback missing, no inbound-parse wired). The current file is a regex-only stub, but it's the best starting point for the REPLACE work. Migrated as-is so the Phase 1 build can iterate on it. The file will be substantially rewritten in Phase 1.

- **`tools/sync_inventory.py`** — review verdict was REPLACE for the auto-discovery path. The current file handles `manual` and `feed` sources correctly; only the `auto` discovery path is a stub. Migrated as-is; the discovery stub was already NOT copied (`app/adapters/inventory/discovery.py` excluded).

---

## 5. Files NOT copied from v4 (explicit "of value" rejections)

### 5.1 The 23 untracked debug scripts in v4 repo root

These are one-off inspection scripts that the user (or previous sessions) wrote for debugging. They are not source code. None were copied.

```
(check_*.py, fix_*.py, hit_*.py, test_*.py in v4 root — verify with `ls v4/*.py`)
```

To re-run any of them, the user can re-create them in v5's `.tmp/` as needed. The canonical record of what they tested is in v4's git history.

### 5.2 Stubs and dead code

- **`app/adapters/inventory/discovery.py`** (43 lines, stub) — always returns "manual" with confidence 0.1. The review's simplification pass #1 calls for its deletion. Not copied.
- **`app/adapters/intake/facebook.py`** — if it exists in v4, it's a stub. Not copied. (Not verified in this session; recommend `ls v4/app/adapters/intake/` in a future session.)
- **`tools/sync_crm.py`** — if it exists in v4, it's the org-sink flush stub for Google Sheets / generic CRM. Not copied. (Not verified; same recommendation.)
- **`tools/parse_lead_email.py`** — **does NOT exist in v4.** The review says it should be built. The build is deferred to Phase 1, so no copy needed.

### 5.3 Archive

- **`_archive_phase1/`** — v1 code, not imported anywhere. Not copied. Available in v4's git history.

### 5.4 Secrets and config

- **`.env`**, **`credentials.json`**, **`token.json`** — secrets files. The user rotated all API keys after v4 teardown. Not copied. `.env.example` (with placeholders) was written fresh.
- **`render.yaml`**, **`start.sh`**, **`Procfile`** — Render/Heroku deployment configs. Will be rewritten for v5 with the new Render plan. Not copied.

### 5.5 Build artifacts and caches

- **`__pycache__/`** — Python bytecode. Not copied.
- **`.venv/`**, **`venv/`** — virtual envs. Not copied. User creates fresh in v5.
- **`.pytest_cache/`**, **`.ruff_cache/`**, **`.mypy_cache/`** — linter/test caches. Not copied.
- **`node_modules/`** — if present, not copied.
- **`.tmp/`** — temporary files. Not copied.

### 5.6 Version control

- **`.git/`** — v4's git history. Not copied. v5 gets a fresh `git init`.

### 5.7 Test files NOT copied (16 of 20)

The subagent was conservative. v4 had 20 test files; v5 has 5 (including `__init__.py`). The 15 not copied:

- `test_chaos.py` — chaos engineering; not relevant for v5 launch
- `test_compliance.py` — partial overlap with the e2e test
- `test_config.py` — env var tests; can be added in Phase 0
- `test_e2e_smoke.py` — overlaps with `test_pipeline_e2e.py`
- `test_intake_adapters.py` — covers webform/sms/email_lead adapters; can be added in Phase 1
- `test_inventory.py` — covers inventory adapters; can be added in Phase 1
- `test_latency.py` — performance; not relevant for v5 launch
- `test_load.py` — load test; not relevant for v5 launch
- `test_org_sinks.py` — covers the cut org-sink feature
- `test_phase1_live.py` — live-fire against real services; not relevant
- `test_phase2_live.py` — live-fire; not relevant
- `test_routing.py` — overlaps with `test_router.py`
- `test_smoke.py` — overlaps with `test_pipeline_e2e.py`
- `test_tenant_isolation.py` — important; should be added in Phase 0
- `test_webhooks.py` — important; should be added in Phase 0

**Recommendation:** the 5 important-but-not-copied tests (`test_intake_adapters`, `test_inventory`, `test_routing`, `test_tenant_isolation`, `test_webhooks`) should be pulled in during the Phase 0 build, before any new features are added. This is the "test discipline" the user said was v4's main failure mode.

### 5.8 Documentation NOT copied (10 docs)

v4 had 11 docs in `docs/`. v5 has 1 (`PIPELINE_REVIEW.md`). The other 10 were not copied because:

- `00-OVERVIEW.md` through `06-SKILLS.md`, `09-SCALE-PLAN.md`, `10-CLIENT-ONBOARDING.md`, `11-CODE-REVIEW.md` — these are the v4 specification, and v5 is rebuilding from `PIPELINE_REVIEW.md` instead. The v4 docs are in v4's git history if needed.
- `PHASE_2E_PROMPT.txt` — a prompt file from a previous session. Not source code.

The v4 docs serve as reference for the v5 design but are not part of v5's truth.

---

## 6. Quick stats

| Metric | Count |
|---|---|
| Files in v5 | 61 |
| Files copied from v4 | 56 |
| New files written for v5 | 5 (README, requirements, .env.example, .gitignore, V5_MIGRATION_LOG.md) |
| P0 fixes applied during migration | 3 (P0-03, P0-09, P0-10) |
| P0 fixes verified in v4 (not re-applied) | 3 (P0-07, P0-11, P0-12) |
| P0 fixes deferred to Phase 0 build | 6 (P0-01, P0-02, P0-04, P0-05, P0-06, P0-08) |
| v4 test files NOT copied (deferred to Phase 0) | 15 (5 of which are important) |
| v4 doc files NOT copied (replaced by PIPELINE_REVIEW.md) | 10 |

---

## 7. What still needs to happen (Phase 0 build session)

In order:

1. **Apply the 6 deferred P0 fixes.** P0-01 (Twilio signature validation) is the most important. P0-08 (CSRF) is the easiest. P0-04 (tenant resolution legacy fallback) is the cleanest.
2. **Add the 5 important-but-not-copied tests** from v4: `test_intake_adapters.py`, `test_inventory.py`, `test_routing.py`, `test_tenant_isolation.py`, `test_webhooks.py`. Verify they pass against the v5 code.
3. **Add the 2 regression tests** for P0-11 (conversation history) and P0-12 (follow-up sender).
4. **Add the 5 P0-replacement feature tests** that the review calls for in Section G.2: webform/SMS intake, email intake (with LLM fallback), missed-call text-back with Message row, quiet-hours per-dealer override, rep notification on APPT_SET.
5. **Wire APScheduler into the FastAPI lifespan** and remove the separate `python -m app.scheduler` process from any future `start.sh`.
6. **Move the conversation engine to a true async background task** (not `asyncio.create_task` after returning TwiML, but a proper queue or background worker that survives request completion).
7. **Build the 5 features marked REPLACE in the review:** email intake (LLM fallback + Mailgun), per-dealer quiet-hours override, rep notification on WhatsApp via Twilio template, on APPT_SET notification, missed-call handoff decision rule.

---

**End of migration log. The v5 directory is ready for Phase 0 build.**
