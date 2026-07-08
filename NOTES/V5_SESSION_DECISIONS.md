# V5 Session Decisions — 2026-06-09

> **What this is:** Everything we agreed on in the chart (Hermes session) on 2026-06-09. One place. Saves the next agent from re-asking the same questions.
>
> **Where the durable truth lives:**
> - Spec + decisions: `docs/PIPELINE_REVIEW.md` (Sections H, I, J)
> - Implementation plan: `V5_BUILD_PLAN.md`
> - What we did this session: `V5_SESSION_DECISIONS.md` (this file)
> - Migration audit: `V5_MIGRATION_LOG.md`

---

## 1. Where things live

| What | Path |
|---|---|
| v5 root | `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/` |
| v4 (dead, reference only) | `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v4/` |
| Git | v5 has a fresh git init on `main`, commit `6bdac8d` |
| v4 Render | DELETED (services and Postgres) |
| Twilio creds | ROTATED (post-v4 teardown) |
| OpenRouter creds | ROTATED (post-v4 teardown) |

## 2. v5 hard rules (carried into every session)

| Rule | Why | What it means in code |
|---|---|---|
| **DRYRUN default** | Twilio credits burned in v4 by automated tests | `OUTBOUND_ENABLED=false` in `.env.example`. Real sends only on explicit user command. |
| **TDD** | v4's main failure mode was untested features | Failing test first, then impl, then verify, then commit. |
| **One commit per task** | Easy to revert, easy to review | `git commit -m "..."` after every task |
| **No fabricated results** | The user has been burned by agents that claim success when there was failure | If a tool call fails, say so. Don't make up API responses. |
| **Polished output** | User is recording a video of the build | Progress bars, banners, no raw terminal spam. |

## 3. The 5 design directives (locked in 2026-06-09)

### 3.1 Render tier: free for dev, paid for production

- **Dev:** free tier is fine. The service may sleep. Acceptable.
- **Production (first real dealer):** switch to Render Starter tier. $14/mo ($7 web + $7 Postgres).
- **VPS:** not now. Re-evaluate at 10+ dealers or if Render pricing changes.

### 3.2 Dealer-side comms = WhatsApp, NOT SMS

- The system contacts the dealer for: rep claim pings, escalations, appointment confirmations, missed-call handoffs.
- **All four go via WhatsApp.** SMS is for customer-side only.
- Build a single chokepoint: `tools/notify_rep.py` with `notify_rep(rep_config, lead, message_type, payload, dealer_config, db_session)`.
- All engine modules call `notify_rep`, never `send_sms` directly, for rep-targeted messages.
- Function dispatches to configurable backend per rep:
  - `twilio_whatsapp` (default) — pre-approved Twilio WhatsApp template
  - `sms` (fallback) — legacy `send_sms()` chokepoint
  - `email` (Phase 2) — not yet implemented
  - `dashboard` (Phase 2) — in-app notification
- All rep notifications persist a `Message` row with `recipient_role="rep"`. (This was a missing piece in v4.)

### 3.3 Bypass Twilio for dealer-side if possible (don't force it)

- **The abstraction is the bypass.** `notify_rep()` reads its backend from config. Swapping backends doesn't touch callers.
- **Phase 1:** Ship with `twilio_whatsapp` as the only implemented backend. Don't add Meta Cloud API in Phase 1.
- **Phase 2:** When dealer count hits 3+ and Twilio WhatsApp costs matter, evaluate Meta direct. Add a `meta_cloud` backend. Zero changes to engine code.
- **Phase 3+:** `email` and `dashboard` backends for dealers without WhatsApp.

### 3.4 Phase 2 provisions in Phase 1 architecture

These architectural decisions in Phase 1 leave room for Phase 2 (no extra cost in Phase 1, just don't undo them):

- `Channel` enum: SMS, WHATSAPP, WEB_CHAT, EMAIL
- Dealer config: free-form `dict` (not strict Pydantic)
- Dashboard `base.html`: `{% block nav %}` for plug-in pages
- State machine events: persist to `LeadEvent` (event bus for Phase 2 listeners)
- `notify_rep()`: the notification chokepoint
- Conversation engine: returns `{text, tools_used, mode}` (Phase 2 can add `mode: webhook_response`)
- `Lead.tags`: JSONB field
- `Message.recipient_role` and `Message.sender_role`: P1-1 task

### 3.5 Testing: manual for fun stuff, automated for the rest

- **User tests manually:** AI persona tone, conversation flow, rep dashboard UX, customer-facing copy, Twilio sandbox integration, email intake.
- **Automated:** state machine, API contracts, compliance gates, tool calling, webhook security, P0 regression tests, every Phase 1 feature test.
- **The one test that matters most:** `tests/test_pipeline_e2e.py` — webform → auto-reply → claim → reply → book. Run after every major change.

## 4. What's open / not decided

These were discussed but not locked in (defer to future sessions):

- Web crawling as default inventory source: **no**. CSV upload is the v5 default. Web crawling is Phase 2 opt-in.
- Daily digest SMS: **cut**. Replace with dashboard widget in Phase 2.
- Per-dealer quiet-hours override: **yes**, but the implementation lands in Phase 1 step 3 (not step 1).
- Email intake on day 1: **cut** from MVP. Add as fast-follow after first dealer.
- Inventory auto-discovery (the v4 stub that always returned "manual"): **deleted**. Replaced with manual upload + feed source.
- Facebook Messenger: **cut**. No adapter. Add only if a real dealer asks.

## 5. The 6 deferred P0 fixes (still to do)

| P0 | What | Why deferred | When |
|---|---|---|---|
| **P0-01** Twilio signature validation | In Phase 0 Task 0.1 (FIRST task in the build) | Required for WhatsApp safety | This session |
| **P0-02** `normalize_db_url` | Cosmetic, code review was wrong about it being broken | Not urgent | Future session |
| **P0-04** Tenant resolution legacy fallback | Do O(n) table scan only for old dealer records | Not urgent | Future session |
| **P0-05** TBD (other critical from code review) | Need to read v4's code review again | Future session | Future session |
| **P0-06** TBD (other critical from code review) | Need to read v4's code review again | Future session | Future session |
| **P0-08** CSRF on dashboard login | Dashboard-level, not webhook-level | Future session | Future session |

## 6. The 5 already-done P0 fixes (during migration)

| P0 | What | File | Status |
|---|---|---|---|
| **P0-03** | OpenAI client singleton | `app/engine/conversation.py` | ✅ Done (migration) |
| **P0-07** | Signed session cookies via itsdangerous | `app/dashboard/__init__.py` | ✅ Verified (was already in v4) |
| **P0-09** | `/readyz` returns 503 on DB failure | `app/main.py` | ✅ Done (migration) |
| **P0-10** | `_twiml` escapes body | `app/main.py` | ✅ Verified (was already in v4) |
| **P0-11** | Conversation history loads last 10 msgs | `app/engine/conversation.py` | ✅ Verified (was already in v4) |
| **P0-12** | Follow-up sender is not a no-op | `app/scheduler.py` | ✅ Verified (was already in v4) |

P0-11 and P0-12 have regression tests in `tests/test_p0_regressions.py` and `tests/test_conversation.py`.

## 7. The 7 originally open questions (now all decided)

| # | Question | Decision |
|---|---|---|
| 1 | VPS or no VPS? | Stay on Render. Free for dev, $14/mo Starter for prod. |
| 2 | Rep notification: WhatsApp or SMS? | WhatsApp via Twilio. Fallback to SMS. |
| 3 | Email intake on day 1? | Cut from MVP. Add as fast-follow. |
| 4 | Per-dealer quiet-hours override? | Yes, `quiet_hours_enabled: bool` in YAML. |
| 5 | Inventory upload UX? | Dashboard CSV upload. Web crawl is Phase 2 opt-in. |
| 6 | AI persona? | 3 templates + open text box for tweaks. |
| 7 | Daily digest SMS? | Cut. Replace with dashboard widget in Phase 2. |

## 8. Files written this session

| File | Purpose |
|---|---|
| `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v4/PIPELINE_REVIEW.md` | The pipeline review (Sections A-J). The spec. |
| `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/PHASE_V5_CHECKLISTS.md` | Synthesized Phase 0/1/2 checklists. Reference. |
| `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Phase_1_Customer_Features.md` | Customer-facing feature doc. For sales conversations. |
| `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed_to_Lead_v4_Tech_Reference.pdf` | 6-page technical reference PDF. |
| `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/` (whole directory) | The v5 codebase, migrated from v4 |
| `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/V5_MIGRATION_LOG.md` | Audit log of the v4 → v5 migration |
| `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/V5_BUILD_PLAN.md` | The implementation plan (Phase 0 + Phase 1 step 1) |
| `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/V5_SESSION_DECISIONS.md` | This file. Everything we agreed on this session. |
| `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/NEXT_SESSION_PROMPT.md` | The copy-paste prompt for the build session |
| `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/docs/PIPELINE_REVIEW.md` | Updated with Sections H, I, J (confirmed decisions + Phase 2 provisions + testing strategy) |
| `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/tests/test_p0_regressions.py` | P0-11 + P0-12 regression tests |

## 9. What's the build plan in 3 lines

1. **Task 0.1** (Phase 0): Twilio signature validation. 5 tests, 1 file modified, 1 commit. 2-5 min.
2. **Task 1.1** (Phase 1): `notify_rep()` abstraction with Twilio WhatsApp default. 4 unit tests + 1 E2E test, 1 new file, 1 file modified, 1 commit. 30-60 min.
3. **Task 1.2** (Phase 1): Real Twilio WhatsApp send (replace the stub). 1 opt-in integration test, 1 file modified, 1 commit. 15-30 min.

The full plan with code examples and verification is in `V5_BUILD_PLAN.md`.

## 10. The copy-paste prompt for the next session

See `NEXT_SESSION_PROMPT.md`. The full prompt is in the "=== COPY FROM HERE ===" block at the bottom of that file. The new agent will:
- Read the prompt
- Read `V5_BUILD_PLAN.md` end to end
- Execute Task 0.1 with TDD
- Report back
- Wait for "next task"

---

**This file is the bridge between sessions. When in doubt, read this first.**
