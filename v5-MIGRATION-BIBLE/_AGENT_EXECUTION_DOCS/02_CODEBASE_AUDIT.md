# Speed to Lead v5 — Codebase Audit (Jun 19, 2026)

> **For:** Manav + AI agents executing refactoring work
> **State:** LIVE on GitHub (origin/main, commit c4ca0ff)
> **Purpose:** Ground truth of what exists, what's broken, what's missing

---

## The Big Picture

Speed to Lead v5 is a dealership lead response system. Leads come in (webform, SMS, WhatsApp, email), get auto-replied within 60 seconds, and an AI conversation engine qualifies the customer and books test drives. Reps get notified via WhatsApp when appointments are booked. There's a dashboard for reps and an admin panel for the platform operator.

**Architecture decision (Jun 19):** Twilio = customer-facing ONLY. Telegram = dealer-facing internal notifications. **Telegram was never built.** Dealer notifications currently go via Twilio WhatsApp.

**Major architectural shift (by AI agents):** Rep assignment is now DEFERRED. Previously, a rep was assigned at lead creation. Now, the AI qualifies the customer and books the appointment FIRST, then the rep is assigned. This is a significant design change that affects the entire pipeline.

---

## What the AI Agents Changed (16 commits on GitHub)

### Critical Changes

1. **PostgreSQL migration** — Database moved from SQLite to PostgreSQL on Render. `app/db.py` now handles `postgres://` → `postgresql+psycopg://` URL normalization with SSL.

2. **Deferred rep assignment** — The biggest change. Rep is NOT assigned when a lead comes in. The AI qualifies and books an appointment, THEN the rep is assigned. State machine changed from `NEW → AUTO_REPLIED → ASSIGNED` to `NEW → AUTO_REPLIED → ENGAGED → APPT_SET → ASSIGNED`.

3. **AI proactive follow-up** — After webform submission, the AI immediately generates a personalized follow-up based on form data (name, vehicle interest, message), then transitions to ENGAGED. The customer gets a real conversation, not just a template reply.

4. **notify_rep chokepoint** — All dealer-side notifications (claim pings, appointment confirmations, escalations, missed-call handoffs) go through a single `notify_rep()` function. Direct Twilio calls from engine/tool code are forbidden.

5. **Async webhook processing** — SMS webhook returns empty TwiML immediately and processes AI reply in `asyncio.create_task()` background. Prevents Twilio's 15s timeout from killing slow AI responses.

6. **DRYRUN dedup fix** — When `OUTBOUND_ENABLED=false`, leads were created with DRYRUN SIDs. When re-enabled, dedup would silently return the stale lead. Now: deletes stale DRYRUN messages, resets lead to NEW, re-sends.

7. **Phone masking fix** — Phones were being masked at storage time, breaking lookups. Now stored as-is with runtime fallback to fix masked phones.

### New Features

8. **Debug endpoints** — `/debug/config` (runtime config), `/debug/dealer/{slug}` (dealer config + recent leads), `/readyz` (DB connectivity check returning 503 on failure).

9. **CORS fix** — Vercel dealership site origins added to allow cross-origin requests.

10. **Manager escalation** — After 3 consecutive passes, escalates to manager via `notify_rep()`.

11. **Daily digest** — Hourly SMS digest of lead activity to managers (has a crash bug — see below).

12. **Stuck lead sweep** — Detects leads stuck in NEW (>5 min) or ASSIGNED (>2x timeout).

13. **Vehicle seeding endpoint** — `/admin/api/seed-vehicles` seeds 20 demo vehicles with enriched specs.

14. **Rate limiting on admin login** — 5 attempts per 15 minutes.

### UI Additions (from earlier)

15. **Admin panel** — Complete admin module with onboarding wizard, dealer management, platform settings.

16. **Dashboard enhancements** — Rep leaderboard, analytics, settings tabs, lead health indicators, attention widgets, activity logging buttons.

---

## File Map (live on GitHub)

### Core Application
| File | Purpose | LOC | Status |
|------|---------|-----|--------|
| `app/main.py` | FastAPI entry, ALL webhook routes, debug endpoints | ~1200 | ⚠️ God-file |
| `app/config.py` | Pydantic Settings + DealerConfig YAML loader | ~250 | ✅ Clean |
| `app/db.py` | PostgreSQL engine with psycopg3, pool tuning | ~106 | ✅ Clean |
| `app/models/__init__.py` | All ORM models | ~169 | ✅ Clean |
| `app/scheduler.py` | BackgroundScheduler: escalation sweep, inventory sync, stale cleanup, daily digest | ~621 | ⚠️ Has crash bug |

### Engine
| File | Purpose | LOC | Status |
|------|---------|-----|--------|
| `app/engine/conversation.py` | AI conversation — OpenRouter, tool dispatch, proactive mode, engagement modes | ~917 | ⚠️ Large |
| `app/engine/lifecycle.py` | State transition helper | ~100 | ✅ Clean |
| `app/engine/router.py` | Round-robin assignment, claim/pass/escalate, silent assignment mode | ~219 | ✅ Clean |
| `app/engine/escalation.py` | SLA escalation sweep | ~82 | ✅ Clean |

### Tools
| File | Purpose | LOC | Status |
|------|---------|-----|--------|
| `tools/route_lead.py` | Main ingestion: dedup → persist → auto-reply → AI proactive follow-up → ENGAGED | ~313 | ✅ Critical |
| `tools/send_sms.py` | SMS/WhatsApp chokepoint — CASL, quiet hours, DRYRUN, sanitization | ~420 | ✅ Chokepoint |
| `tools/notify_rep.py` | Dealer notification chokepoint — WhatsApp/SMS backends, DRYRUN gate | ~394 | ✅ Clean |
| `tools/book_appointment.py` | Appointment booking + deferred rep assignment + mark_sold | ~284 | ✅ Clean |
| `tools/check_inventory.py` | Vehicle search | ~100 | ✅ Clean |
| `tools/detect_missed_call.py` | Missed call detection | ~60 | ⚠️ Stub |
| `tools/sync_inventory.py` | Inventory sync from CSV | ~150 | ⚠️ Partial |

### Adapters
| File | Purpose | Status |
|------|---------|--------|
| `app/adapters/intake/__init__.py` | Base class + NormalizedLead | ✅ Clean |
| `app/adapters/intake/webform.py` | Web form → NormalizedLead (now handles VIN, consent) | ✅ Clean |
| `app/adapters/intake/sms.py` | SMS webhook → NormalizedLead (consent=True for CASL) | ✅ Clean |
| `app/adapters/intake/email_lead.py` | Email → NormalizedLead (regex + LLM fallback) | ⚠️ Not wired to provider |
| `app/transports/twilio.py` | Thin adapter → Twilio SDK | ✅ Clean |

### Dashboard (10 templates)
| File | Purpose | Status |
|------|---------|--------|
| `base.html` | Dark theme, HTMX, sidebar nav | ✅ Polished |
| `leads.html` | Pipeline view with stats, attention widget | ✅ Complete |
| `lead_detail.html` | 3-column: info, conversation, actions | ✅ Complete |
| `login.html` | Login with CSRF | ✅ Complete |
| `team.html` | Rep leaderboard | ✅ Complete |
| `stats.html` | Analytics with funnel, metrics | ✅ Complete |
| `settings.html` | Settings tabs — **save buttons are stubs** | ⚠️ Partial |
| `appointments.html` | Appointments view | ✅ Complete |
| `leads_partial.html` | HTMX partial | ✅ Complete |

### Admin (7 files)
| File | Purpose | Status |
|------|---------|--------|
| `app/admin/__init__.py` | Admin routes: dealers, onboarding, seed vehicles | ✅ Complete |
| Admin templates (6) | Login, dealers list, detail, onboarding, settings | ✅ Complete |

### Dealer Config
| File | Purpose | Status |
|------|---------|--------|
| `dealers/premier-auto.yaml` | Premier Auto, Vancouver — 20 vehicles, Harsh as active rep | ✅ Production |
| `dealers/example-dealer.yaml` | Template | ✅ Reference |
| `tests/fixtures/demo-dealer.yaml` | Test fixture | ✅ Test |

---

## Data Model

### Lead (key fields)
`id`, `dealer_id`, `source` (Channel), `name`, `phone`, `email`, `vehicle_ref`, `vehicle_id`, `state` (LeadState), `assigned_rep`, `pass_count`, `consent`, `loss_reason`, `created_at`, `updated_at`

### Message (key fields)
`id`, `lead_id`, `direction`, `channel`, `body`, `provider_sid` (unique — idempotency), `delivery_status`, `ai_generated`, `sender_role`, `recipient_role`, `created_at`

### LeadEvent
`id`, `lead_id`, `dealer_id`, `type`, `payload` (JSON), `synced`, `created_at`

### Appointment
`id`, `lead_id`, `dealer_id`, `scheduled_for`, `status` (set/confirmed/showed/no_show/cancelled), `created_at`

---

## State Machine (CURRENT — post AI agent changes)

```
NEW → AUTO_REPLIED → ENGAGED → APPT_SET → ASSIGNED → CLAIMED → SHOWED → SOLD
                     ↓           ↓
                  ESCALATED   ESCALATED
                     ↓
                  (reassign to manager after 3 passes)

Any state → OPTED_OUT (STOP keyword)
Any state → LOST (manual or 7-day no response)
```

**Key difference from original:**
- OLD: Rep assigned at lead creation (`NEW → AUTO_REPLIED → ASSIGNED`)
- NEW: Rep assigned at appointment booking (`ENGAGED → APPT_SET → ASSIGNED`)
- The AI qualifies the customer before a human ever sees the lead

---

## API Endpoints (LIVE)

### Webhooks
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/webhook/sms/inbound` | Twilio SMS (async background processing) |
| POST | `/webhook/sms/status` | Twilio delivery status |
| POST | `/webhook/whatsapp/inbound` | Twilio WhatsApp |
| POST | `/webhook/whatsapp/status` | Twilio WhatsApp status |
| POST | `/webhook/form/{token}` | Web form submission |
| POST | `/webhook/email` | Email ingestion |

### Debug (temporary)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/debug/config` | Runtime config (no secrets) |
| GET | `/debug/dealer/{slug}` | Dealer config + recent 5 leads |
| GET | `/readyz` | DB connectivity (503 on failure) |

### Dashboard
| Method | Path | Purpose |
|--------|------|---------|
| GET/POST | `/dashboard/login` | Auth with CSRF |
| GET | `/dashboard/leads` | Pipeline view |
| GET | `/dashboard/leads/{id}` | Lead detail |
| POST | `/dashboard/leads/{id}/messages` | Send message |
| POST | `/dashboard/leads/{id}/reassign` | Reassign rep |
| POST | `/dashboard/leads/{id}/mark-sold` | Mark sold |
| POST | `/dashboard/leads/{id}/mark-lost` | Mark lost |
| GET | `/dashboard/team` | Leaderboard |
| GET | `/dashboard/stats` | Analytics |
| GET | `/dashboard/settings` | Settings (saves are stubs) |
| GET | `/dashboard/appointments` | Appointments |

### Admin
| Method | Path | Purpose |
|--------|------|---------|
| GET/POST | `/admin/login` | Admin auth (rate limited) |
| GET | `/admin/dealers` | Dealers list |
| GET | `/admin/dealers/{slug}` | Dealer detail |
| GET/POST | `/admin/onboarding` | Onboarding wizard |
| POST | `/admin/api/seed-vehicles` | Seed demo vehicles |
| POST | `/admin/api/cleanup-test-leads` | Delete 555-number test leads |

---

## What's Working

1. ✅ Web form → auto-reply → AI proactive follow-up → ENGAGED
2. ✅ SMS/WhatsApp inbound → AI conversation → appointment booking
3. ✅ STOP/START opt-out (CASL compliant)
4. ✅ Phone normalization (canonical function)
5. ✅ Cross-day dedup (same phone + same dealer = one lead)
6. ✅ DRYRUN dedup fix (stale DRYRUN leads re-send correctly)
7. ✅ Phone masking fix (stored as-is, runtime fallback)
8. ✅ PostgreSQL on Render
9. ✅ Async webhook processing (no Twilio timeout)
10. ✅ notify_rep chokepoint (all dealer notifications centralized)
11. ✅ Manager escalation after 3 passes
12. ✅ Debug endpoints for troubleshooting
13. ✅ CORS for Vercel dealership site
14. ✅ Dashboard with leaderboard, analytics, attention widgets
15. ✅ Admin panel with onboarding wizard

---

## What's Broken (LIVE bugs)

### CRITICAL — Will crash in production

1. **Daily digest crash** — `app/scheduler.py` line ~424 references undefined `dealer` variable in `send_daily_digest()`. Will crash when the job runs.

2. **WhatsApp test mode handler in production** — `_handle_customer_whatsapp_test()` in `app/main.py` is ~180 lines of production code in a "test mode" handler. Routes non-rep WhatsApp to conversation engine. Duplicates logic from SMS handler. Should be removed before production.

### HIGH — Will cause data issues

3. **`greeting_only` mode bypasses lifecycle** — `conversation.py` sets `lead.state = LeadState.ASSIGNED` directly without using `transition()`. Bypasses state change logging (LeadEvent).

4. **`_normalize_db_url` duplicated** — Same function in `app/db.py` and `app/scheduler.py`. Risk of divergence.

5. **Connection pool size = 2** — `app/db.py` sets `pool_size=2, max_overflow=2`. Too small for production under load.

6. **No future-date validation on appointments** — `book_appointment()` can book appointments in the past.

7. **`handle_claim` doesn't verify rep identity** — Any rep can claim any ASSIGNED lead, not just the assigned one.

8. **`pass_count` not persisted** — Set as runtime attribute via `getattr(lead, "pass_count", 0) + 1`. May be lost on session refresh.

### MEDIUM — Fragile but works

9. **Settings save buttons are stubs** — `settings.html` buttons call `showToast()` but don't persist.

10. **No rate limiting on webhooks** — Only admin login is rate-limited.

11. **`book_appointment` is a stub** — Creates DB records, no calendar integration.

12. **`detect_missed_call` is a stub** — Logs a warning, doesn't detect.

13. **No conversation memory management** — Long conversations will hit token limits.

14. **Debug endpoints have no removal mechanism** — Marked "temporary" but no expiry.

15. **Hardcoded WhatsApp template SID** — Different dealers need different templates.

---

## Architecture Concerns

### Layering Violations
1. `app/main.py` is a god-file (~1200 lines) — webhooks, verification, delegation, debug endpoints
2. Engine imports tools directly (`conversation.py` → `check_inventory`, `book_appointment`)
3. Tools import engine (`route_lead.py` → `lifecycle`)
4. Dashboard imports everything — no service layer

### Missing Abstractions
5. No service layer — business logic scattered
6. No event bus — state changes logged but no pub/sub
7. No transport abstraction — Twilio hardcoded in `send_sms.py`
8. No DMS integration — only manual CSV

### Tight Coupling
9. Dealer config is a JSON blob — no schema validation
10. Templates reference `lead.state.value` — model changes break templates

---

## What the PRD Promised but Doesn't Exist

1. **Telegram dealer-facing channel** — Decision was made, never built
2. **Google Calendar integration** — `book_appointment` is a stub
3. **CRM sync** — All stubs
4. **Inventory DMS integration** — Only manual CSV
5. **Email provider wiring** — Adapter exists, not connected
6. **Phone/voicemail intake** — No Twilio Voice integration
7. **AI conversation modes** — "Qualify Only" and "Greeting Only" partially implemented
8. **Multi-region compliance** — Only BC/CASL
9. **Monitoring/alerting** — No health checks, no metrics
10. **Backup/disaster recovery** — No backup strategy

---

## The .claude/ Noise

The AI agents added Claude Code swarm coordination scaffolding:
- `.claude-flow/` — metrics, security audits, swarm activity
- `.claude/helpers/` — 30+ shell scripts
- `.claude/commands/` — SPARC methodology
- `.claude/agents/` — Browser/testing agent configs

**This is development scaffolding, not product code.** Should be gitignored or removed.

---

*Last updated: 2026-06-19. Based on live GitHub codebase (origin/main, commit c4ca0ff).*
