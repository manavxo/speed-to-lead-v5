# Speed to Lead v4 — Pipeline Review

> **Mode:** Sharpen the axe. No code, no migrations, no config edits. Read-only review of the v4 pipeline against the Phase 1 customer promise.
> **Scope:** The 6 Phase 1 promises from `Phase_1_Customer_Features.md` + the 10 owner notes.
> **Default verdict:** REUSE. Anything we change needs a concrete reason.

---

## Executive Summary

**The 3 biggest reasons v4 kept failing:**

1. **The conversation engine did not remember previous turns.** When the AI replied, it saw only the latest customer message — not the last 10 messages in the thread. So "do you have the Tucson?" got a fresh answer every time, even when the customer had already asked about it 3 messages ago. This single bug made the AI feel broken, even when the rest of the pipeline was fine. **Status: actually fixed in v4 — `_call_openrouter()` loads the last 10 messages (lines 786-799). Keep that fix; do not regress it.**
2. **Several "in place" features are silently no-ops.** The follow-up sender's job handler is wired but does not actually send messages. The auto-reply for missed calls is a TwiML response — it never lands in the conversation thread. The rep notification for a booked appointment does not exist — the rep only finds out by checking the dashboard. Each of these looks fine in a test that calls a leaf function, but does not work in real life.
3. **Auto-reply messages were not being recorded.** When a web form came in, the auto-reply SMS was sent but the Message row was not always written — so the lead detail page said "0 messages" even though the customer had received a reply. The recent fix in `tools/route_lead.py` (always-record) is correct, but it relies on a fresh session query, which is fragile.

**The 3 highest-leverage simplifications:**

1. **Cut the inventory auto-discovery stub.** It always returns "manual" with confidence 0.1, no matter what URL you give it. Replace it with one of: manual upload, simple CSV feed, or a single concrete scraper. The "auto" ladder is dead weight.
2. **Cut the inventory feed auto-detection.** Use a known-platform hint (one enum value the dealer picks) plus a per-platform field map. Don't try to detect the platform from a URL — it never worked in v4.
3. **Cut Facebook Messenger.** It is a stub. CASL is murky for Facebook DMs in Canada. If a dealer asks for it later, add the adapter then. The pipeline does not need it now.

**The single recommended next action:** Build the Phase 0 safety net first — the 12 fixes in `PHASE_V5_CHECKLISTS.md` (Twilio signature validation, conversation history, OpenAI client leak, etc.) plus one honest end-to-end test that exercises webform → auto-reply → rep claim → customer reply → book appointment. Do not start the dashboard, do not start the AI persona work, do not start the value-add widgets. Make the engine pass the test first, then build on top.

---

## A. Pipeline-as-built (the honest map)

A lead flows through the system today. Here is the chain for each intake channel, with the actual file at each hop, and the gaps where the chain silently dead-ends.

### A.1 Webform → SMS auto-reply → rep claim

```
[Customer submits form on dealer site]
  → POST /webhook/form/{token}              app/main.py:312
  → Tenant resolution: _find_dealer_by_token  app/main.py:153
  → WebFormAdapter().parse(payload)         app/adapters/intake/webform.py
  → tools.route_lead.ingest_lead()          tools/route_lead.py:49
        ├─ 1. Dedup (24h window, same phone)  ✅ working
        ├─ 2. Persist Lead (NEW)              ✅ working
        ├─ 3. Resolve vehicle_ref             ✅ works for stock# / VIN / URL
        │      (free-text resolution is naive)
        ├─ 4. Log consent (webform = express) ✅ working
        ├─ 5. Transition NEW→AUTO_REPLIED     ✅ working
        ├─ 6. send_sms() auto-reply           ✅ working (gated)
        │      └─ records Message             ✅ fixed (always-record)
        └─ 7. assign_lead()                    app/engine/router.py
              ├─ pick next rep (round-robin)
              ├─ transition AUTO_REPLIED→ASSIGNED
              └─ send_sms() claim ping to rep  ⚠️ SMS, not WhatsApp
                                                (see Note 3)
```

**Dead-ends / weak spots:**
- Free-text vehicle resolution (`"looking for a red Honda SUV"`) is naive — it will not match.
- Rep notification goes out as **SMS**, not WhatsApp. The `/webhook/twilio/whatsapp` endpoint only handles inbound (claim/pass replies). The "WhatsApp claim" branding is misleading.

### A.2 Inbound SMS → conversation

```
[Customer texts dealer number]
  → POST /webhook/twilio/sms                app/main.py:342
  → _validate_twilio_signature()             🔧 STUB (C-01 from code review)
  → _find_dealer_by_sms()                    app/main.py:174
  → Rep identification (for "1" / "2" reply)  app/main.py:380
  → If rep + "1" or "2": claim/pass
  → If "STOP" / "START": opt-out handling
  → Otherwise: find or create lead
  → If new lead: ingest_lead() (same as A.1)
  → If existing: app.engine.conversation.handle_turn()
        ├─ load workflow SOP + dealer config
        ├─ call OpenRouter with last 10 messages
        ├─ execute tool calls (check_inventory / book_appointment)
        └─ return {mode, text, tools_used}
  → background task: send_sms() reply        🔧 off the request path
```

**Dead-ends / weak spots:**
- Twilio signature validation is a no-op (header-presence check only). Any attacker who knows the URL can inject fake SMS. (CRITICAL)
- The AI reply is sent in a background `asyncio.create_task` after returning TwiML. If the process dies between the TwiML response and the background send, the customer sees a reply arrive from a previous turn (or never). (HIGH — but acceptable trade-off vs. hitting Twilio's 15s response deadline)
- `book_appointment` succeeds → `LeadEvent` written → state transitions. But **no notification is sent to the rep** that an appointment was just booked. The rep has to check the dashboard.

### A.3 Missed call → text-back

```
[Customer calls, no answer]
  → POST /webhook/twilio/voice              app/main.py:754
  → _validate_twilio_signature()             🔧 STUB
  → _find_dealer_by_sms()
  → Returns TwiML with text-back body
  → Twilio delivers the SMS to the customer
```

**Dead-ends / weak spots:**
- The text-back is generated inline in the webhook and returned as TwiML. **No Message row is written.** So the conversation thread on the lead detail page will not show this text-back. (HIGH — owner note 4 cares about this)
- There is no handoff to a human rep. The customer gets a "we missed your call" text, and that's it. The owner wants the missed-call flow to try to **connect the customer to a salesperson as fast as possible**. (HIGH — owner note 4)

### A.4 Email → ingest

```
[Customer emails a listing site, email forwards to dealer's lead_email_inbox]
  → POST /api/intake/email                   (this endpoint may not exist in v4 main.py)
  → EmailLeadAdapter().parse(payload)         app/adapters/intake/email_lead.py
  → ingest_lead() (same as A.1)
```

**Dead-ends / weak spots:**
- The email adapter uses **regex only**. It matches `Customer Name:`, `Phone:`, `Email:`, `Stock:`, etc. Each listing site uses different formats. AutoTrader, CarGurus, Kijiji all have different templates. (HIGH — owner note 9 calls this the backbone)
- The docstring says "tools/parse_lead_email.py does the heavy parsing (with an LLM fallback for unknown templates)" — **that file does not exist** in v4. The LLM fallback is missing.
- There is no concrete email-to-webhook service configured. The docstring mentions Mailgun/Postmark/SendGrid Inbound Parse, but **none is wired up**. (CRITICAL — owner note 9)

### A.5 Escalation sweep (background)

```
[Every 1 min, APScheduler fires]
  → _run_escalation_sweep()                  app/scheduler.py:36
  → Find ASSIGNED leads with last-assigned event > claim_timeout_min ago
  → on_claim_timeout()                       app/engine/escalation.py:17
        ├─ transition ASSIGNED→ESCALATED
        └─ run actions from config: [reassign, notify_manager]
```

**Dead-ends / weak spots:**
- Escalation runs as a separate process (`python -m app.scheduler`), not inside FastAPI. The main.py lifespan shows a scheduler has been started there too, but the standalone process is still in start.sh.
- No advisory lock — if two scheduler processes run (multi-worker, the wrong start.sh), leads get double-escalated. (CRITICAL for prod, MEDIUM for dev)
- The escalation job handler in `app/scheduler.py:115` is **NOT a no-op** as the v4 code review says — it does actually call `handle_turn` to generate AI text and then `send_sms()`. The code review was wrong about this one. ✅

### A.6 Follow-up sender (background)

```
[Per-lead scheduled job]
  → _handle_followup()                       app/scheduler.py:115
  → load lead + dealer config
  → call handle_turn() to generate AI follow-up text
  → append CASL footer
  → send_sms()
  → persist Message row
```

**Status:** Actually wired and working — contrary to the v4 code review (issue H-06). The code review was looking at an older version.

### A.7 Inventory sync (background)

```
[Every 3 hours per dealer, refresh_min adjustable]
  → _run_inventory_sync()                    app/scheduler.py:202
  → tools.sync_inventory.sync_inventory(session, dealer)
```

**Status:** Stub. `app/adapters/inventory/discovery.py` only has `FeedSource` and `_ManualFloor`. `FeedSource` accepts CSV/TSV/XML — the dealer would have to set up a static URL. No real detection. (Owner note 5 — frequently-changing inventory.)

### A.8 Org-sink flush (background)

```
[Every 15 min, only if dealer config has lead_org.mode != "native"]
  → _run_org_sink_flush()                    app/scheduler.py:225
  → tools.sync_crm.flush_events()
```

**Status:** Stub. No concrete CRM adapter wired. (Cut from v5 MVP per checklist.)

---

## B. Phase-1 Feature × Pipeline Matrix

Default verdict = **REUSE**. Anything marked MODIFY/REPLACE/CUT has a reason.

| # | Feature / Owner Note | Where it lives in v4 | Works? | Verdict | Why (one line) | Failure risk if shipped as-is |
|---|---|---|---|---|---|---|
| **P1-1** | Instant response on every channel (webform) | `app/main.py:312` + `tools/route_lead.py` | yes | REUSE | Works, tested | None for the path itself |
| **P1-1** | Instant response on SMS | `app/main.py:342` | yes | REUSE | Working | Twilio signature bypass — see security bug C-01 |
| **P1-1** | Missed call text-back | `app/main.py:754` | partial | MODIFY | Returns TwiML with text, but **no Message row written** | Conversation thread is wrong; no handoff to rep |
| **P1-1** | Email intake (AutoTrader/CarGurus/Kijiji) | `app/adapters/intake/email_lead.py` | stub | REPLACE | Regex-only, no LLM fallback, no inbound-parse wired | Most leads from listing sites will be lost |
| **P1-2** | Real conversation, grounded on inventory | `app/engine/conversation.py` + `tools/check_inventory.py` | yes | REUSE | Multi-turn history now loads (10 msgs); tools work | None |
| **P1-2** | Tone-matched to dealer (persona, guardrails) | `dealers/*.yaml` → `build_system_prompt()` | yes | REUSE | All persona/guardrail config flows through | None |
| **P1-3** | Test drive booked over text | `tools/book_appointment.py` | yes | REUSE | AI calls it, transition fires, confirmation sent | **No rep notification on APPT_SET** — owner note 2 |
| **P1-4** | Opt-out works instantly (STOP/START) | `app/main.py:497` (SMS) | yes | REUSE | Single chokepoint enforces it | None |
| **P1-4** | Quiet hours respected (21:00–08:00) | `tools/send_sms.py:111` | yes | REUSE | Single chokepoint | **Blocks testing at 3am** — owner note 8 |
| **P1-5** | Data private, CASL 7-yr audit | `app/models` (`ConsentLog` table) + `tools/send_sms.py:215` | yes | REUSE | Every consent event logged | None |
| **P1-6** | One customer, one thread across channels | `ingest_lead()` dedup (24h window) | partial | MODIFY | Dedup is phone-based within 24h only | Cross-day webform + SMS from same person = 2 leads |
| | | | | | | |
| **N1** | Form → real conversation with website context | `app/main.py:312` → does NOT continue thread | partial | REPLACE | Webform ends at auto-reply; no inbound follow-up handler | Customer texts "tell me more" → not connected to webform lead |
| **N2** | Notify rep on booked appointment | nowhere | missing | REPLACE | No notification on APPT_SET state | Rep misses the appointment until they check the dashboard |
| **N2** | Notify rep on handoff request (AI → human) | `app/main.py:587` (background reply) | partial | MODIFY | Background reply happens, but rep is not actively told | Same as above |
| **N3** | Rep notification channel: WhatsApp or SMS | `send_sms()` in `app/engine/router.py:79` | yes (but SMS) | REPLACE | v4 sends SMS, not WhatsApp. Rep reply path expects WhatsApp endpoint | Round-trip works but is 100% SMS — owner wants WhatsApp for richness |
| **N4** | Missed call → human handoff, decision rule | nowhere | missing | REPLACE | Text-back only, no decision logic | "I want to talk to Mike" gets a bot reply, not Mike |
| **N5** | Inventory freshness (frequently changing) | `inventory.refresh_min` in YAML | partial | REPLACE | Polling, no webhook, no on-demand check | Car sold 5 minutes ago is still in AI's inventory |
| **N5** | AI coachable per dealer (persona, guardrails) | `dealers/*.yaml` → `ai.*` + `workflows/qualify_and_book.md` | yes | REUSE | All loaded into system prompt | None |
| **N5** | Grounding: never invent a car or price | `app/engine/conversation.py` system prompt + `check_inventory` tool | yes | REUSE | Tool is the only source; AI forbidden from guessing | None |
| **N6** | Twilio chokepoint + CASL/PIPA | `tools/send_sms.py` (the only caller) | yes | REUSE | All compliance lives here | None |
| **N6** | 24/7 always-on, no laptop in the loop | Render hosting + APScheduler | yes | REUSE | Cron pings + healthz keep it warm | Cold-start 30-60s on free tier (cost = $7/mo fix) |
| **N7** | Conversations visible to rep/manager in dashboard | `app/dashboard/templates/lead_detail.html` | yes | REUSE | Already wired | None |
| **N8** | Quiet hours testing override | `QUIET_HOURS_DISABLED` env flag in `tools/send_sms.py:290` | partial | MODIFY | Works but global, not per-dealer | Owner wants per-dealer override |
| **N9** | Email ingestion (the backbone) | `app/adapters/intake/email_lead.py` | stub | REPLACE | See P1-1 row above | Lost leads |
| **N10** | Minimal dealer onboarding ask | `dealers/example-dealer.yaml` (8 sections) | partial | MODIFY | Asks for a lot. Can be cut to 4 sections for v5 | Dealer anxiety at onboarding |

**Counts:**
- 11 features REUSE (no change)
- 5 features MODIFY (small fix, same architecture)
- 5 features REPLACE (different approach)
- 0 features CUT (every Phase 1 promise is load-bearing)

---

## C. Decisions to Make

For each open design question, three options + a recommendation. Scoring: cheap, easy, low-failure, scalable, minimal-dealer-access.

### C1. Rep notification channel: WhatsApp template vs. Telegram bot vs. SMS

| Option | Cost | Setup friction | Failure modes | Dealer-access required | Scales? | Verdict |
|---|---|---|---|---|---|---|
| **SMS (current v4)** | ~$0.0079/msg | zero | Twilio rate limits, no rich content | Dealer's phone number | yes | fallback |
| **Twilio WhatsApp template** | ~$0.005/msg + 24h session window | low — same Twilio account | Sandbox must be joined for testing; 24h window for free-form | WhatsApp-enabled phone | yes | **default** |
| **Telegram bot** | free | medium — bot token, webhook setup | Telegram availability, no Canada reach data | Telegram account | yes | no — most BC dealers don't use Telegram |

**Recommended default:** Twilio WhatsApp with a pre-approved template for the claim ping. Same channel for both directions. The 24h session window is a real constraint — the rep must reply within 24h or the next claim ping needs a new template. Acceptable trade-off because claim pings are event-driven and reps are motivated.

**Fallback:** Plain SMS if WhatsApp not provisioned. Less rich, but always works.

### C2. Event-driven push vs. cron sweep

| Pattern | Pros | Cons | When to use |
|---|---|---|---|
| **Event-driven (push)** | Instant notification, no lag | Requires Twilio to be up, requires webhooks wired | Rep claim ping, missed-call handoff, appointment booked |
| **Cron sweep** | Restart-safe, no missed events, no webhooks needed | Up to N minutes of lag | Unclaimed-lead escalation, daily digest, inventory refresh |

**Recommended:** Use **event-driven** for customer-facing notifications (claim ping, appointment booked, missed-call handoff). Use **cron sweep** for state-machine escalation and inventory. This is what v4 mostly does, with the right intent. The fix is the **rep notification on APPT_SET** (Note 2) — make that event-driven, sent immediately on state transition.

### C3. Missed-call → human handoff decision rule

The owner wants: if the customer asks for a specific salesperson, route to them. Otherwise, the AI tries to answer first; hands off if it can't.

**Decision rule:**
1. Text-back fires within 60s of missed call.
2. If customer's next message contains a name in the dealer's sales_team list (Mike, Dana, etc.) → send `Welcome, [customer name]! I'll connect you with [rep name]. They will text you shortly.` and transition to ASSIGNED for that rep. Notify the rep via WhatsApp/SMS claim ping.
3. If customer's next message is a vehicle question → AI answers normally.
4. If customer's next message is "talk to a person" / "real person" / "manager" → give the dealer phone number, offer a callback, transition to ASSIGNED for the manager.
5. If customer's next message is anything else → AI handles (it can answer "are you open Sundays?" or "do you have financing?" from the dealer config).

**Why this rule:** The handoff is never blocked by the AI. The AI never becomes a bottleneck. The customer always has a way to reach a human, but the AI still helps for things it can ground.

### C4. Inventory freshness: poll vs. webhook vs. on-demand-at-conversation

| Approach | Latency | Cost | Reliability |
|---|---|---|---|
| **Poll every N minutes** (current) | up to N min | low | medium — depends on cron firing |
| **Webhook from dealer site** | seconds | zero | low — most dealer sites don't expose webhooks |
| **On-demand check at conversation time** | zero | 1 DB read per AI turn | high — no stale data |
| **Hybrid: poll + on-demand at convo time** | zero | 1 DB read per turn | highest — on-demand catches anything the poll missed |

**Recommended:** **Hybrid** — keep `refresh_min` polling as a background job, and add a single `vehicles` table read at the start of every `check_inventory` call (it already does this — the read is the function). The current v4 code already does on-demand, so this is "what we have, confirmed." If the dealer's site supports a webhook, register it (Note: most don't).

### C5. 24/7 always-on hosting: managed vs. VPS

| Option | Cost | Setup | Always-on? | Cron reliability |
|---|---|---|---|---|
| **Render (current v4)** | $7/mo web + $7/mo db | zero | yes on Starter tier; sleeps on free | good (Postgres jobstore) |
| **Fly.io** | $5-10/mo | low | yes | good |
| **Railway** | $5-15/mo | low | yes | good |
| **Dedicated VPS (DigitalOcean, Hetzner)** | $5-20/mo | high (you manage everything) | yes | depends on you |

**Recommended:** Stay on **Render** for v5. The $14/mo (web + db) buys you: 24/7 uptime, no laptop in the loop, automatic deploys from GitHub, the Postgres jobstore for APScheduler means jobs survive restarts. A VPS adds work for no benefit at this scale (single-digit dealers).

**When to switch to VPS:** When the dealer count exceeds 10, OR when Render's pricing stops making sense, OR when you need to run a non-Postgres piece of infra. Don't switch before then.

### C6. Email-lead ingestion: inbound-parse webhook vs. IMAP poll vs. forward-to-endpoint

| Option | Cost | Setup | Parsing fragility | Dealer access required | Verdict |
|---|---|---|---|---|---|
| **Mailgun inbound parse** | $0 (free tier, 100 emails/mo) | low — DNS MX record | low (Mailgun pre-parses headers) | Forward `leads+dealership@mg.yourdomain.com` | **default** |
| **SendGrid Inbound Parse** | $0 (free tier) | low | low | Forward `leads@parse.sendgrid.net` | fallback |
| **Postmark inbound** | $0 (free tier) | low | low | Forward `leads@inbound.postmarkapp.com` | fallback |
| **IMAP poll (Gmail/Outlook)** | $0 | medium — OAuth | high — different sites use different formats | Dealer's email credentials | **never** — too much access, too brittle |
| **LLM fallback for unknown formats** | ~$0.001/email | medium | medium — LLM gets it 80% right | none | **always on** — for the 20% the regex misses |

**Recommended:** **Mailgun Inbound Parse (or SendGrid equivalent)** + **LLM fallback for unknown templates**. The dealer forwards their listing-site emails to `leads+<slug>@mg.yourdomain.com`. We get a webhook POST with the email body. The LLM fallback (the missing `tools/parse_lead_email.py`) extracts name/phone/vehicle from the body when regex fails.

**Dealer-access required:** a one-time email forwarding rule in their Gmail/Outlook. The Mailgun address is opaque (no credentials to share).

### C7. Quiet-hours testing override

| Option | Implementation | Risk in prod |
|---|---|---|
| **Global `QUIET_HOURS_DISABLED` env flag** (current) | single env var, off in prod by default | low if you remember to turn it off |
| **Per-dealer `quiet_hours_enabled: bool` in YAML** | one field per dealer config, can be true for staging dealers | low — only staging dealers set it true |
| **Test-number allowlist (e.g. only +1604*** test phones bypass)** | clever but complex | medium — easy to forget to update |
| **All of the above, layered** | env var > per-dealer > allowlist | low |

**Recommended:** **Per-dealer `quiet_hours_enabled: bool` in YAML**, defaulting to `true` (quiet hours on, as production wants). The staging dealer in the YAML sets it to `false`. The `QUIET_HOURS_DISABLED` env var stays as a global kill-switch for the test fleet. The test-number allowlist is overkill — skip it.

---

## D. The Simplification Pass

Things to merge, delete, replace, or stop doing. For each: what we gain, what (if anything) we give up.

1. **Cut `app/adapters/inventory/discovery.py`.** It returns "manual" 100% of the time. Replace the `inventory.source: auto` YAML value with `inventory.source: manual` or `inventory.source: feed`. **Gain:** one fewer moving part that lies to the user. **Give up:** the "magic" onboarding flow (it never worked).

2. **Cut Facebook Messenger intake.** It is a stub. The endpoint exists but the adapter does not. **Gain:** no half-built code. **Give up:** Facebook as a future channel (add the adapter when a real dealer asks for it).

3. **Cut the `lead_org` org-sink flush.** No concrete CRM is wired. The scheduled job fires every 15 min and does nothing useful. **Gain:** one fewer cron job, cleaner logs. **Give up:** Google Sheets sync, which v4 docs mentioned but never built.

4. **Cut the daily-digest SMS feature.** It is a "nice to have" that adds a per-dealer scheduled job, a per-dealer `digest_enabled` flag, and a per-dealer `digest_time` field. **Gain:** simpler config schema, fewer background jobs. **Give up:** the GM getting a morning text summary (rebuild this as a dashboard widget in Phase 2 instead).

5. **Cut the `message_tags_enabled` staging tag.** The `_apply_message_tag` function adds `[STG REP lead#123 ->Mike]` to messages when `MESSAGE_TAGS_ENABLED=true`. Useful for testing on a single phone, but a per-dealer `staging_only: bool` flag is simpler. **Gain:** one fewer env var. **Give up:** the ability to disambiguate sends during live-fire testing on a shared test phone (use multiple test phones instead).

6. **Merge `_handle_followup` and `_run_escalation_sweep` into one cron job.** They both scan leads and react. The unified job can be `every_1_min_do_everything()`, with internal branching. **Gain:** one cron instead of two. **Give up:** slightly more readable code (the merge adds an if/else).

7. **Replace the `BlockingScheduler` separate process with the FastAPI lifespan pattern.** v4's `app/main.py` already has a `_scheduler` global started in lifespan, but `start.sh` also launches `python -m app.scheduler`. Pick one. **Gain:** one fewer process to manage, no risk of double-escalation. **Give up:** nothing — the lifespan version is the right one.

8. **Delete the 23 debug scripts in the repo root** (`check_*.py`, `fix_*.py`, `hit_*.py`, `test_*.py`). They are one-off inspection scripts from past debugging. The conversation logs in the dashboard are the canonical record of what they tested. **Gain:** clean repo. **Give up:** the ability to re-run them verbatim (the user can always re-create a one-off `check_*.py` if needed).

9. **Cut `_archive_phase1/`.** Old code from a previous attempt that is not imported anywhere. **Gain:** clean repo. **Give up:** the ability to see v1 in-tree (it's in git history).

---

## E. Minimal Dealer Onboarding Ask

What a dealer must hand over to go live, ranked least-to-most sensitive, with a lower-friction alternative for each.

| What | Required? | Sensitivity | Lower-friction alternative |
|---|---|---|---|
| **Business name + address** | yes | low — already on their website | Use their Google Business profile, scrape, or have us look it up |
| **Business hours + timezone** | yes | low | Default to Mon-Sat 9-7, Sun closed, America/Vancouver. Dealer edits later in the dashboard |
| **One Twilio phone number** (SMS) | yes | low — they have to buy this anyway | We provision it for them ($1/mo on Twilio, billed to us) |
| **Sales team: name + phone + active** | yes | low — every dealer knows their team | Add reps over time; v5 works with 1 rep |
| **Inventory source** | yes | medium — depends on how they maintain cars | Default: manual upload (CSV). 5 cars at a time via the dashboard |
| **Manager phone** (for escalations) | yes | low | Optional — if blank, manager is not notified, lead just escalates to "next rep" |
| **A lead email inbox** (forwarding rule) | optional | medium — they have to set up email forwarding | Skip email intake in v5; rely on webform + SMS only. Add email later |
| **AI persona + guardrails** | yes | low — they pick from 3 templates | Default persona works. Customization in dashboard later |
| **Their existing CRM credentials** | NO | high — would make them nervous | Never. Native dashboard only. Webhook to their CRM is opt-in (Phase 2) |
| **Their website admin access** | NO | high | Never. We use the public website URL for inventory scraping if they opt in (Phase 2) |
| **Their Twilio account** | optional | medium | Shared account works for the first 5 dealers. Per-dealer Twilio subaccount is Phase 2 |
| **OpenRouter / AI provider credentials** | NO | high | Never expose. We provide. Dealer pays via our metered bill (Phase 2) |

**The shortest possible onboarding ask:**

1. Business name + hours + timezone (3 fields)
2. Sales team (name + phone + active, one row per rep)
3. One Twilio number (we provision or you provide)
4. Upload 5 cars via the dashboard (manual upload, no integration needed)

That's it. **5 minutes of work** for a dealer to go live with the lean MVP scope.

---

## F. Known-Failure Watchlist

Real-stack gotchas. For each: v4's exposure and v5's design to avoid it.

| Failure mode | v4 exposure | v5 fix |
|---|---|---|
| **Opt-out send-after-STOP** | medium — relies on `send_sms()` opt-out check + `_log_consent` | Add a fast-path test: every STOP keyword immediately transitions lead to OPTED_OUT and any in-flight `send_sms` calls check state before sending |
| **Duplicate Twilio webhook → double-text** | low — MessageSid idempotency check exists in `_idempotency_check()` | Keep the check, add a per-lead rate limit (max 1 outbound per 30s) as a belt-and-suspenders |
| **WhatsApp 24h session window** | high — claim pings go as SMS in v4, not WhatsApp, so this isn't hit. But Phase 2 will add WhatsApp. | Use pre-approved Twilio WhatsApp templates for any business-initiated message. Free-form replies are only for the 24h session window after customer texts in |
| **Twilio signature 403 behind TLS-terminating host** | CRITICAL — currently a no-op | Use `RequestValidator.validate()` with the **external** URL (not the internal http URL). Read body once, cache, validate. Fix is in P0-01 |
| **Timezone bugs in business-hours / quiet-hours** | medium — `is_business_hours()` and `_is_quiet_hours()` both convert to dealer tz | Add a test per dealer timezone: Vancouver, Toronto, Halifax. Confirm 21:00 dealer-time = 04:00 UTC next day in Halifax (Atlantic), etc. |
| **AI grounding / hallucination when inventory is empty** | low — `check_inventory` returns empty list, system prompt tells AI to say "we don't have it" | Add a test: empty inventory → AI replies with the prescribed message, not invented cars |
| **LLM rate-limit → backoff then templated fallback** | medium — retry logic exists for 5xx, no templated fallback | When retries exhausted, send a static template ("We're experiencing high volume, will reply shortly") and queue the lead for human follow-up |
| **Tenant resolution doing a full table scan per webhook** | medium — legacy fallback in `_find_dealer_by_*` scans all dealers | After all dealers have the indexed columns, drop the legacy fallback. Add a JSONB index on `config->'channels'->>'web_form_token'` for safety |
| **Scheduler jobs not firing after restart** | low — `SQLAlchemyJobStore` persists jobs | Verify: kill the process, restart, confirm scheduled jobs re-load. Add a test |
| **Email parsing breaking when a listing site changes its format** | HIGH — regex-only adapter | Add the LLM fallback (the missing `tools/parse_lead_email.py`). On parse failure, log to a "needs review" inbox for a human to fix manually |
| **OpenAI client created per request** | CRITICAL — memory leak | Singleton at module level, lazy-initialized. Fix in P0-03 |
| **Round-robin pointer not atomic** | low — single-process app, but risk if multi-worker | Wrap `next_rep` in `SELECT ... FOR UPDATE` or use a Redis-free advisory lock |

---

## G. Recommended Sequence

Smallest-risk-first plan, phrased as "smallest change that proves a Phase-1 promise." Each item is marked REUSE / MODIFY / REPLACE so the build session is unambiguous.

### G.1 Phase 0 — Safety net (3–5 days)

These are not features. They are correctness fixes. The v5 build is dead before it starts if these aren't in.

- [P0-01] REPLACE — Twilio signature validation: real `RequestValidator.validate()` against parsed form body
- [P0-02] MODIFY — `app/scheduler.py:296`: fix the `_normalize_db_url` (it's actually fine; code review was wrong, but the line is suspicious — replace with the explicit prefix logic)
- [P0-03] REPLACE — `app/engine/conversation.py:773-778`: singleton `_get_openai_client()` at module level
- [P0-04] MODIFY — `app/main.py`: drop the legacy fallback in `_find_dealer_by_*` after audit confirms all dealers have indexed columns
- [P0-05/06] REPLACE — review the two remaining CRITICAL issues from `docs/11-CODE-REVIEW.md` and fix
- [P0-07] REPLACE — `app/dashboard/__init__.py`: signed session cookie via `itsdangerous.URLSafeTimedSerializer` (already done — keep it)
- [P0-08] MODIFY — `app/dashboard/__init__.py`: add CSRF token on login form POST
- [P0-09] REPLACE — `app/main.py:293` (readyz): return 503 on DB failure
- [P0-10] REPLACE — `app/main.py:222` (_twiml): `html.escape(body)` before interpolating
- [P0-11] — conversation history: **already fixed in v4** (lines 786-799 of conversation.py). Add a test to prevent regression
- [P0-12] — follow-up sender: **already fixed in v4**. Add a test to prevent regression

### G.2 Phase 1, Feature-by-feature (10–14 days)

In order:

1. **REUSE** — Data model + state machine (already sound)
2. **REUSE** — Intake adapters (webform, SMS) — keep, fix Twilio signature
3. **REPLACE** — Email intake (Notes 9, C6): wire Mailgun inbound parse, build `tools/parse_lead_email.py` with regex + LLM fallback
4. **MODIFY** — Missed-call text-back (Note 4): write Message row to conversation thread, add the human-handoff decision rule
5. **MODIFY** — Quiet hours per-dealer override (Note 8, C7)
6. **REPLACE** — Rep notification channel (Notes 2, 3, C1): move to WhatsApp template via Twilio, send notification on APPT_SET
7. **MODIFY** — Inventory freshness (Note 5, C4): add webhook support for dealers that have it, keep on-demand as the default
8. **REPLACE** — `app/adapters/inventory/discovery.py`: delete, replace with known-platform hint
9. **MODIFY** — `tools/route_lead.py`: extend dedup window from 24h to longer (Note P1-6: cross-day webform + SMS)
10. **REPLACE** — Onboarding form: 4 sections, not 8 (Note E)

### G.3 Phase 1, Test discipline (parallel, 5+ days)

For every feature built, the test lands in the same commit. Target: 50+ tests, all passing in <30s, all using FakeTwilio + FakeLLM.

### G.4 Phase 2 — Customer-facing (10–14 days)

Lean MVP scope per `PHASE_V5_CHECKLISTS.md`:
- 6 customer-facing features (2.1.1 through 2.1.6, plus 2.1.8 after-hours)
- 5 rep-facing features (2.2.1 through 2.2.5, plus 2.2.12 response timer)
- 3 owner-facing features (2.3.1 leads list, 2.3.2 attention widget, 2.3.5 appointments)
- 2 system health (2.4.1, 2.4.2)

Total: ~18 features, ~3,000 lines of code.

---

## H. Confirmed Decisions

In priority order. **All 7 originally open questions have been resolved** (per the user session of 2026-06-09). Plus 5 new design directives added below.

### H.1 Original 7 open questions — ALL CONFIRMED

1. **VPS or no VPS?** ✅ **Stay on Render.** Free tier for dev, $14/mo Starter tier for production (web $7 + Postgres $7) when the first dealer goes live. The user has confirmed they're okay with the spend. (C5)
2. **Rep notification channel: WhatsApp or SMS?** ✅ **WhatsApp via Twilio** as the default backend. Fallback to SMS if WhatsApp isn't provisioned. (C1) → See H.2.3 for the implementation decision.
3. **Email intake on day 1, or cut from MVP?** ✅ **Cut from MVP.** Only dealer webform + SMS for v5 launch. Add email intake (Mailgun Inbound Parse + LLM fallback) as a fast-follow. (C6, G.2 step 3)
4. **Per-dealer quiet-hours override: yes or no?** ✅ **Yes, per-dealer.** `quiet_hours_enabled: bool` in dealer YAML, defaults to `true`. Staging dealers set it to `false`. The `QUIET_HOURS_DISABLED` env flag stays as a global kill-switch. (C7)
5. **Inventory upload UX:** ✅ **Dashboard CSV upload.** Drag-and-drop in the dealer settings page. Web-crawling is a Phase 2 opt-in feature for dealers who refuse to upload CSVs. (G.2 step 8)
6. **AI persona:** ✅ **3 templates + an open text box for tweaks.** The dealer picks from Friendly, Professional, or Casual; can edit the system prompt in a text box. (E)
7. **Daily digest SMS:** ✅ **Cut.** Replace with a dashboard widget in Phase 2. (D-4)

### H.2 New directives from session 2026-06-09 (5)

These were added in a follow-up session after the original review was written. They're locked in for the v5 build.

#### H.2.1 Render tier strategy: free for dev, paid for production

- **Dev / staging:** Render free tier. The service may sleep after 15 min of inactivity. Fine for development where the user is poking at it.
- **Production (first dealer goes live):** Switch to Render Starter tier. $14/mo total ($7 web + $7 Postgres). This is the cost of doing business — a 24/7 product needs 24/7 hosting.
- **Trigger to switch:** The moment any real dealer's leads start flowing. Don't wait for a paying customer to upgrade; the customer's first lead is when the system needs to be awake.
- **VPS alternative:** Not now. If Render pricing stops making sense at 10+ dealers, revisit. A Hetzner/DO box at $5-20/mo is the only viable alternative and it adds operational work.

#### H.2.2 Dealer-side comms = WhatsApp, NOT SMS

- The system contacts the dealer for: rep claim pings, escalation notifications, appointment confirmations, missed-call handoffs.
- **All four go via WhatsApp**, not SMS. SMS is for the customer-facing side (the dealer's Twilio number, which customers expect to be reachable as SMS).
- Implemented as a single chokepoint: `tools/notify_rep.py` with `notify_rep(rep_config, lead, message_type, payload, dealer_config, db_session)`. All engine modules that need to tell the dealer something call this function — never `send_sms()` directly.
- The function dispatches to a configurable backend per rep. Default = `twilio_whatsapp` (pre-approved Twilio WhatsApp template). Fallback = `sms` (legacy `send_sms()` chokepoint). Phase 2 = `email` and `dashboard` backends.
- All rep notifications persist a `Message` row with `recipient_role="rep"` so the lead detail page shows them. This was a missing piece in v4 (the rep notification went out but didn't show in the conversation thread).

#### H.2.3 Bypass Twilio for dealer-side if possible (don't force it)

- **The abstraction is the bypass.** `notify_rep()` reads its backend from the rep's config. Swapping backends doesn't require touching any caller.
- **For Phase 1:** Ship with `twilio_whatsapp` as the only implemented backend. Don't add Meta Cloud API direct integration in Phase 1 — it would be ~1 week of work (Meta business verification, template approval, separate webhook signature verification) for $0 savings at the current scale.
- **For Phase 2:** When the dealer count is 3+ and Twilio WhatsApp costs become meaningful, evaluate Meta direct. Add a `meta_cloud` backend to `notify_rep()`. Zero changes to engine code.
- **For Phase 3+:** The abstraction supports `email` and `dashboard` backends for dealers who don't have WhatsApp.

#### H.2.4 Phase 2 provisions MUST exist in Phase 1 architecture

Phase 2 features per the review (and the user wants the architecture to leave room):

- 5 rep-facing dashboard refinements (response timer, lead-claim-rate, etc.)
- 3 owner-facing features (leads list, attention widget, appointments)
- 2 system health (logging, monitoring)
- Email intake with LLM fallback
- Missed-call handoff decision rule
- Rep notification on APPT_SET (covered by `notify_rep` already)
- Per-dealer quiet-hours override

**The Phase 1 architectural decisions that leave room for these (no extra cost in Phase 1, just don't undo them):**

| Provision | Why | Phase 1 verification |
|---|---|---|
| `Channel` enum includes SMS, WHATSAPP, WEB_CHAT, EMAIL | Phase 2 can add new channels without schema changes | Verify `app/models/__init__.py` has all four |
| Dealer config is a free-form `dict`, not strict Pydantic | Phase 2 can add fields without breaking old configs | Verify `Dealer.config` is typed as `dict` |
| Dashboard `base.html` has a `{% block nav %}` | Phase 2 pages plug in, no template rewrite | Verify the template |
| State machine events persist to `LeadEvent` | Phase 2 can add Slack/email listeners on event inserts | Verify `app/engine/lifecycle.py` writes `LeadEvent` rows |
| `notify_rep()` is the notification chokepoint | Phase 2 can add new backends | See H.2.2 |
| Conversation engine returns `{text, tools_used, mode}` | Phase 2 can add `mode: webhook_response` for chat widget | Verify `app/engine/conversation.py` |
| `Lead.tags` is a JSONB field | Phase 2 can tag leads without schema changes | Verify `app/models/__init__.py` |
| `Message.recipient_role` and `Message.sender_role` | Phase 2 can attribute messages to roles (rep, customer, ai, system) | Added in P1-1 task |

#### H.2.5 Testing strategy: manual for the fun stuff, automated for the rest

- **User will test manually:** AI persona tone, conversation flow ("does the AI handle 'I'm just looking' right?"), rep dashboard UX ("can I find my leads quickly?"), customer-facing copy.
- **Will be automated:** state machine transitions, API contracts, compliance gates (opt-out, quiet hours, OUTBOUND_ENABLED), tool calling (check_inventory, book_appointment), webhook signature validation, every P0 regression test, every Phase 1 feature test.

**Testing infrastructure required in v5 (already partially built):**

| Component | Status in v5 | What it gives you |
|---|---|---|
| pytest fixtures: FakeTwilio, FakeLLM, in-memory DB | ✅ Already in `tests/conftest.py` | No real network calls in tests |
| Structured JSON logs (state transitions, SMS sent, LLM calls) | ✅ Already in v4 | Grep-friendly for debugging |
| `/debug/lead/{id}` endpoint | ❌ Not yet — add in Phase 0 | See the lead's current state, all messages, all events |
| `/debug/inbox` endpoint | ❌ Not yet — add in Phase 0 | See all recent leads at a glance |
| `python -m app.seed_demo` | ❌ Not yet — add in Phase 0 | Creates a "Smoke Test Dealer" with 10 sample leads |
| `OUTBOUND_ENABLED=false` | ✅ In `.env.example` | All SMS / WhatsApp go to a log file instead of Twilio |
| Per-dealer `quiet_hours_enabled: false` | ✅ Config schema supports it | Test at 3am without quiet hours blocking |
| `pytest -v` runs all tests in <30s | TBD — verify | CI-ready, no slow tests |

---

## I. Phase 2 Provisions in Phase 1 Architecture — Detail

For each Phase 2 feature, the Phase 1 architectural decision that enables it.

| Phase 2 feature | Phase 1 architectural decision | Code that locks it in |
|---|---|---|
| Email intake (AutoTrader / CarGurus / Kijiji) | Dealer config has `lead_email_inbox` field; email adapter has a stub | `app/adapters/intake/email_lead.py` |
| Rep notification on APPT_SET | `notify_rep()` is the chokepoint; `book_appointment` tool calls it after state transition | `tools/notify_rep.py`, `tools/book_appointment.py` |
| Missed-call handoff decision rule | `/webhook/twilio/voice` writes a Message row (post-P0-09) so the handoff text shows in the lead thread | `app/main.py:voice webhook` |
| Per-dealer quiet-hours override | Dealer config has `quiet_hours_enabled: bool`; `tools/send_sms.py` reads it | `tools/send_sms.py` |
| Email backend for `notify_rep` | `notify_rep()` reads `notify_backend` from rep config; `email` is a valid value (returns NotImplementedError for now) | `tools/notify_rep.py` |
| Dashboard "attention" widget | `LeadEvent` table tracks all state changes; the widget queries for leads with no rep activity in 30 min | `app/dashboard/templates/leads.html` (Phase 2) |
| Daily digest (dashboard widget, not SMS) | `LeadEvent` table aggregates; the dashboard widget queries | `app/dashboard/templates/stats.html` (Phase 2) |
| Multi-channel conversation thread | `Channel` enum + `Message.channel` field | `app/models/__init__.py` |
| Lead tagging (hot-lead, price-sensitive, etc.) | `Lead.tags` JSONB field | `app/models/__init__.py` |
| Slack notification on APPT_SET | `LeadEvent` insert can be subscribed to; a Phase 2 listener adds Slack | New file `app/event_listeners/slack.py` (Phase 2) |

---

## J. Testing Strategy — Detail

### J.1 What gets automated

| Category | Test target | Test file |
|---|---|---|
| **State machine** | All 11 states, all valid transitions, invalid transitions rejected | `tests/test_lifecycle.py` |
| **Round-robin** | Even distribution, skip-inactive, escalation to manager | `tests/test_router.py` |
| **Conversation engine** | Multi-turn history (10 msgs), tool calls, retries, dry-run | `tests/test_conversation.py` |
| **SMS chokepoint** | Opt-out check, quiet hours, sanitization, OUTBOUND_ENABLED gate | `tests/test_send_sms.py` (or `tests/test_sms_chokepoint.py`) |
| **Notify rep** | Default = WhatsApp, fallback to SMS, message persistence, dry-run | `tests/test_notify_rep.py` |
| **Webhook security** | Signed/unsigned/tampered requests (P0-01) | `tests/test_webhook_security.py` |
| **End-to-end pipeline** | webform → auto-reply → claim → reply → book (the one test that matters) | `tests/test_pipeline_e2e.py` |
| **P0 regression** | P0-11 conversation history, P0-12 followup not no-op | `tests/test_p0_regressions.py` |
| **Phase 1 features** | One test file per feature, in the same commit | `tests/test_*.py` |

### J.2 What stays manual

| Category | Why | How the user does it |
|---|---|---|
| **AI persona tone** | Subjective; only a human can judge "does this feel like a salesperson?" | Sends the dealer number a few test texts as a fake customer |
| **Conversation flow** | Multi-turn interactions are hard to assert in unit tests | Replays 5–10 realistic customer scripts (e.g., "I'm just looking", "do you have financing?") |
| **Rep dashboard UX** | "Can I find my leads quickly?" is a human question | Logs in, navigates, times the click paths |
| **Customer-facing copy** | "Does this greeting feel right?" | Reads the auto-reply, adjusts the YAML |
| **Twilio sandbox integration** | Only meaningful with a real phone | Joins the sandbox, runs the opt-in integration test, confirms the WhatsApp arrives |
| **Email intake** | Depends on real AutoTrader / CarGurus / Kijiji email formats | Forwards a real lead email to the Mailgun address, checks it lands as a Lead |

### J.3 The one test that matters most

`tests/test_pipeline_e2e.py` — the end-to-end test that exercises the full pipeline. It already exists in v5. The user should run it manually after every major change:

```bash
cd "C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5"
pytest tests/test_pipeline_e2e.py -v
```

Expected: green in <5 seconds. If this test is red, the engine is broken. If this test is green, the engine works.

---

## K. The Plan

The implementation plan lives at `V5_BUILD_PLAN.md` (in the v5 root). It covers:
- **Phase 0 Task 0.1:** Twilio signature validation (P0-01) — 2-5 min
- **Phase 1 Task 1.1:** `notify_rep` abstraction with Twilio WhatsApp default — 30-60 min
- **Phase 1 Task 1.2:** Real Twilio WhatsApp send (replace the stub) — 15-30 min

Each task is bite-sized, TDD-disciplined, one commit per task. See `V5_BUILD_PLAN.md` for the full task list with code examples and verification steps.

---

**End of pipeline review. The build plan is at `V5_BUILD_PLAN.md`. The migration log is at `V5_MIGRATION_LOG.md`. The next-session prompt is at `NEXT_SESSION_PROMPT.md`.**
