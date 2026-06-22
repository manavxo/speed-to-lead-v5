# Speed to Lead v5 — Mimo Code Execution Spec (FINAL)

> **Runner:** DeepSeek V4 Pro + headroom compression layer.
> **How to read this doc:** Each TASK below is self-contained — it restates its own files, steps, and acceptance test so you never depend on remembered context. If compression drops something, re-read the two blocks below (PROJECT FACTS, DECISIONS LOCKED); they hold everything stable.
> **Owner:** Manav. **Planner:** Claude. **North star:** `v5-MIGRATION-BIBLE/PRD_HUMAN.md` — if any task contradicts it, STOP and ask.

---

## PROJECT FACTS (stable — preserve through compression)

- Stack: FastAPI + SQLAlchemy + PostgreSQL on Render. Live URL: `https://speed-to-lead-v5.onrender.com`.
- AI conversation engine: `app/engine/conversation.py` (`handle_turn()`), DeepSeek/OpenRouter.
- SMS/WhatsApp/Voice via Twilio. Telegram = the ONLY dealer notification channel.
- The single SMS sender: `tools/send_sms.py`. The single rep-notify chokepoint: `tools/notify_rep.py`.
- Dealer config lives in DB (and `dealers/*.yaml` for the test dealer `premier-auto`).
- Test suite: 128 passing, 1 skipped. `pytest` must stay green.
- **Grounding rule (sacred):** the AI may ONLY state facts returned by deterministic tools (inventory, availability, business facts). It must NEVER invent cars, slots, prices, or policies.

---

## DECISIONS LOCKED (Manav, final — preserve through compression)

1. **Website forms (#1):** Do NOT touch dealer websites. Read leads from the dealer's email inbox instead. **Implement TODAY.**
2. **"Built but untested" features:** Mimo must **test them in real time**, not just rely on unit tests. Mimo may **ask Manav for inputs** to simulate a real test (sample data, a phone number, a test call). Manav will also **manually re-test sensitive items** as a second confidence layer.
3. **Login (#4):** **Log in every visit** (session ends when browser closes). **One shared link** for everyone; each person uses **their own PIN**.
4. **Inventory (#5):** **Manual upload only** (CSV/XLSX). No auto-crawl now.
5. **Twilio (#6):** TOP priority. Mimo gets **full access** — browser control, API keys, Render env — to fix it. Manav does not want to touch Twilio/Render.
6. **Distinct Telegram messages (#7):** Build it.
7. **Dealer-own send address (#9):** Already built. **Verify** it; only add work if a gap is found.
8. **Business facts (#10):** Build a per-dealer facts field fed at onboarding.
9. **Cover-me (#11):** Must be **fixed AND deployed TODAY**.
10. **After-hours (#13):** Default = **follow up in the morning**. Instant after-hours response is a **paid upsell to build later** — keep lean now.
11. **Missed-call (#15):** Fix the repeat-caller bug, push, test in real time.
12. **Testing strategy:** Manav + Claude will define the full market-readiness test plan separately while Mimo works. For now, Mimo applies the "real-time test" rule to every task.

---

## OPERATING RULES FOR MIMO

1. **Keep tests green.** Run `pytest` after every task; report pass/fail. A task isn't done until tests pass AND its real-time acceptance test passes.
2. **Real-time test everything you touch.** For each task, after coding, actually exercise it live. If you need something to simulate (a phone number, sample email, test call, API key), **ask Manav and wait** — do not fake it silently.
3. **Config before code.** Manav's strong prior: the system works; bad config makes it look broken. Diagnose config first; show before/after.
4. **Grounding rule is sacred** (see PROJECT FACTS). Any change letting the model free-text facts is a regression — revert it.
5. **Never hardcode phone numbers.** Read recipients from lead data / dealer config.
6. **Report before surprising.** If a task is bigger or more broken than described, STOP and report with evidence before proceeding.
7. **You own Twilio/Render config**, not Manav. Make the changes; document exactly what changed.
8. **Order matters.** Do tasks in the numbered order. T1 (Twilio) unlocks the live testing for everything else.

---

## ACCESS NEEDED FROM MANAV (request up front)

Twilio Account SID + Auth Token · Twilio number(s) + Messaging Service SID · Render env access · DeepSeek/OpenRouter key · SendGrid key · Telegram Bot token · Manav's personal phone · real sample lead emails (AutoTrader, CarGurus) · the dealer's lead-inbox email login (for #1).

---

# TASKS (in order)

## T1 — FIX TWILIO (top priority, unlocks everything)  — concern #6
**Goal:** Real SMS in/out works on the live deployment.
**Files/where:** Twilio Console + Render env + routes `app/main.py` (`/webhook/twilio/sms`, `/webhook/twilio/voice`).
**Steps:**
1. Audit settings in order: `OUTBOUND_ENABLED` (must be true to send), `PUBLIC_BASE_URL` (live https URL), Twilio number's webhook URL (must point to the correct route), `require_twilio_signature`, Account SID/token, Messaging Service vs raw number.
2. Produce a before/after table of every value changed.
**Acceptance / real-time test:** Manav texts the dealer number → it reaches the webhook → AI reply is delivered back to Manav's phone, on live Render.
**If blocked:** ask Manav for the specific key/value you can't see.

## T2 — PROVE THE AI ENGINE  — concern #3
**Goal:** Show the AI holds a real, grounded conversation. (Independent of Twilio.)
**Files/where:** `app/engine/conversation.py::handle_turn()`.
**Steps:**
1. Drive `handle_turn()` with a fake inbound message (local harness or curl).
2. Confirm: model connects, persona loads, `check_inventory` returns seeded cars, AI offers only real inventory.
**Acceptance / real-time test:** A scripted 3-turn chat (greeting → car question → booking intent) gives sensible grounded replies. Then repeat the same over real SMS now that T1 is fixed.

## T3 — MISSED-CALL FOLLOW-UP: FIX BUG + PROVE LIVE  — concern #15
**Goal:** Every missed call gets one text-back; repeat callers are NOT ignored.
**Files/where:** `tools/detect_missed_call.py` (bug at lines ~84-101), route `app/main.py:927` `/webhook/twilio/voice`, doc `docs/CALL_DETECTION.md`.
**Bug:** Today it skips the text-back if ANY prior phone lead exists for that number — forever.
**Steps:**
1. Change dedup to per-CallSid (idempotent) or a short time window — NOT "ever had a lead."
2. Ensure the text-back honors quiet hours (see T11 default = morning).
3. Wire the Twilio number's Voice webhook → `{PUBLIC_BASE_URL}/webhook/twilio/voice`, status callback → `/webhook/twilio/status`, ring timeout ~25s. Voice number may equal the SMS number (zero extra config).
4. Add config fields if missing: `channels.voice_number`, `channels.call_detection` (always_on|time_based|voicemail_notify), `channels.ring_timeout_sec`.
**Acceptance / real-time test:** Real call to the dealer number, unanswered → text-back lands on caller's phone → caller replies → AI takes over. Then: same caller missed on two different days → texted both times. **Push/deploy when green.**

## T4 — COVER-ME / HANDOFF ACTUALLY NOTIFIES  — concern #11  (DEPLOY TODAY)
**Goal:** Passing a lead to another rep reliably reaches that rep, who confirms receipt.
**Files/where:** reassign route in `app/dashboard/__init__.py` (currently only flips the DB field, notifies no one); notify chokepoint `tools/notify_rep.py`; Telegram.
**Steps:**
1. On reassign, fire a Telegram message to the new rep with a `[✅ Take it]` button carrying the lead id.
2. New rep taps → lead confirmed as theirs → dashboard reflects it.
3. (Depends on T5 inbound Telegram for the button tap; if doing T4 before T5 completes, at minimum send the notify message and wire the button in T5.)
**Acceptance / real-time test:** Rep A reassigns to Rep B → Rep B gets a distinct Telegram ping → taps Take it → lead shows under Rep B. No silent transfers. **Push/deploy when green.**

## T5 — TELEGRAM INBOUND + chat_id CAPTURE + DISTINCT MESSAGES  — concerns #2(blocker), #7
**Goal:** Reps can claim leads from Telegram, get auto-enrolled, and receive clearly different message types.
**Files/where:** new route `POST /webhook/telegram` in `app/main.py`; dealer config (per-rep `telegram_chat_id`); `tools/notify_rep.py`.
**Steps:**
1. Add `POST /webhook/telegram` handling inline-button callbacks and `/start` deep links. Set it once via Telegram `setWebhook`.
2. chat_id capture: onboarding makes a per-rep link `t.me/<Bot>?start=<dealer>__<rep>`; rep taps Start → webhook reads `message.chat.id` → save as that rep's `telegram_chat_id`.
3. Replace "reply 1/2" with inline buttons `[✅ Claim] [➡️ Pass]` carrying the lead id. Claim → assign; Pass → increment pass count, re-route, escalate to manager after 3.
4. Build ONE message-template module with **visibly distinct** messages: NEW_LEAD, COVER_ME ("🆘 cover request"), HANDOFF_RECEIVED ("📨 handed to you" — must read differently from COVER_ME), CLAIM_CONFIRM, ESCALATION, DAILY_DIGEST.
**Acceptance / real-time test:** New rep taps their link → chat_id captured + confirmation sent. Real lead ping → rep taps Claim → assigned, others can't claim it. Trigger each event → six visibly different messages; COVER_ME ≠ HANDOFF_RECEIVED.

## T6 — WEBSITE-FORM LEADS VIA EMAIL  — concern #1  (IMPLEMENT TODAY)
**Goal:** Capture dealer website-form leads with zero changes to their site, by reading their email inbox.
**Files/where:** email ingestion (`app/adapters/intake/email_ingest.py`), lead routing (`tools/route_lead.py`), parsers.
**Steps:**
1. Use the existing email-ingestion path as the universal intake for website-form notification emails (most site forms email the dealer a lead).
2. Branch correctly: lead has phone → AI/SMS takes over; lead has no phone → warm auto-email + notify rep to handle manually. (Make sure the no-phone branch works for these emails — the webform-style path historically didn't split phone vs no-phone like the email path does.)
3. Add a parser for the dealer's website-form email format (ask Manav for a real sample).
**Acceptance / real-time test:** A real website-form notification email arrives in the inbox → a lead is created → phone leads get AI texts; no-phone leads get a warm email + rep notice. Ask Manav to submit a test form.

## T7 — BOOKING GUARDRAILS (Layer 1)  — concern #1-of-PRD (most damaging failure mode)
**Goal:** AI can never book outside business hours or double-book a rep.
**Files/where:** new `check_availability` tool; `tools/book_appointment.py`; prompt in `app/engine/conversation.py`.
**Steps:**
1. Add a deterministic `check_availability(date_range)` tool (same grounding as inventory). Open slots = dealer business hours − existing appointments per rep. Returns only VALID slots.
2. Add guards to `book_appointment`: reject if outside business hours; reject if it collides with that rep's existing appointment. Assign a rep who is FREE at the slot, round-robin among free reps.
3. Change the prompt: remove "YOU ARE THE CALENDAR / book anything"; replace with "offer only the slots check_availability returned."
**Acceptance / real-time test:** AI cannot book 3am or a closed Sunday; two leads can't book the same rep into one slot; AI offers only tool-returned slots. Add regression tests.

## T8 — LOGIN: EVERY VISIT + ONE LINK + PIN  — concern #4
**Goal:** Everyone uses one shared link, logs in each visit with their own PIN.
**Files/where:** `app/dashboard/__init__.py` (login sets cookie at ~line 827 with `max_age=86400`).
**Steps:**
1. Make the session a per-visit cookie: drop `max_age` so it expires when the browser closes (Manav's choice = log in every visit).
2. One central link that defaults the dealer, lists reps, each enters their own PIN. Ensure logout works.
**Acceptance / real-time test:** From one shared URL, two different reps each log in with their PIN; closing the browser logs them out; no straight-to-dashboard surprise. Manav re-tests this manually (sensitive).

## T9 — REP PRIVACY: NO BACK-DOOR  — concern #12
**Goal:** A rep can never view OR modify another rep's lead by guessing its id.
**Files/where:** all mutating routes in `app/dashboard/__init__.py` (reassign, notes, status, appointment edits).
**Status:** Viewing is already scoped correctly. The gap: confirm every "change/edit" action also checks ownership, not just that the user is logged in.
**Steps:** Audit each mutating route; add an ownership/role guard (managers bypass; reps limited to their own + unassigned). Add a regression test per route.
**Acceptance / real-time test:** A logged-in rep trying to change another rep's lead by id is rejected. Manav re-tests this manually (sensitive).

## T10 — PER-DEALER BUSINESS FACTS  — concern #10
**Goal:** AI accurately states each dealer's specifics (fees, inspection reports, sub-prime credit, trade-ins, warranty) and never invents them.
**Files/where:** `AIConfig` in `app/config.py` (today only has persona + boolean guardrails — no facts field); prompt assembly in `app/engine/conversation.py`.
**Steps:**
1. Add a `business_facts` block to dealer config (YAML + DB).
2. Inject it into the system prompt as grounded facts; if asked something not listed, AI defers ("let me check with the team") instead of inventing.
3. Capture these at onboarding (T13 checklist).
**Acceptance / real-time test:** Add a fact ("we work with sub-prime credit") → AI answers correctly. Remove it → AI defers instead of guessing.

## T11 — AFTER-HOURS DEFAULT = MORNING  — concern #13
**Goal:** Leads arriving after hours are followed up in the morning by default (lean, compliant).
**Files/where:** quiet-hours logic in `tools/send_sms.py`; scheduler `app/scheduler.py`; the global `quiet_hours_disabled` flag.
**Steps:**
1. Set behavior so after-hours phone leads queue for a morning send (default), respecting quiet hours.
2. Leave a clear hook for a future per-dealer "instant after-hours" paid option — but do NOT build the instant path now.
**Acceptance / real-time test:** A simulated after-hours lead is not texted at night; it sends in the morning. (Note: reliable overnight scheduling needs Render's always-on paid tier — flag to Manav.)

## T12 — INVENTORY: RELIABLE MANUAL UPLOAD  — concern #5
**Goal:** Manager can upload inventory by CSV/XLSX and the AI is immediately current. (No auto-crawl.)
**Files/where:** manager dashboard upload; Vehicle table; `Inventory` config.
**Steps:** Make CSV/XLSX upload solid: parse, validate, upsert into Vehicle, report row-level errors (don't silently drop bad rows).
**Acceptance / real-time test:** Manager uploads a sample CSV and XLSX → cars appear → AI's `check_inventory` returns them → malformed rows are reported.

## T13 — ONBOARDING CHECKLIST + CONFIG GENERATOR  — concern #7 (setup side)
**Goal:** A repeatable way to stand up a new dealer in under an hour, no hand-edited YAML.
**Steps:**
1. Fixed intake checklist: business name, hours, timezone, address, main phone, reps (name + mobile), manager, inventory file, lead inbox email, business facts (T10), after-hours preference (T11 default morning), send-from email (T14).
2. Config generator writes a complete valid config to the DB, including per-rep PINs.
3. Self-capture: Telegram deep links (T5).
4. Missed-call setup: pick detection mode; set voice_number/call_detection/ring_timeout; Mimo sets the Twilio voice webhook; dealer activates carrier call-forwarding (`*72` always-on / `*71` conditional); verify with a test call.
**Acceptance / real-time test:** Run the generator with checklist inputs → a working dealer: reps log in, get Telegram pings, AI knows the facts, inventory loaded — no YAML hand-editing.

## T14 — VERIFY DEALER-OWN SEND ADDRESS  — concern #9
**Goal:** Confirm emails can send from the dealer's address (already built); flag deliverability work.
**Files/where:** `app/transports/email.py` (`_resolve_sender` already supports per-dealer `email_from_address`).
**Steps:**
1. Verify per-dealer send address works end-to-end with a real send.
2. Document the deliverability requirement (per-dealer SPF/DKIM/DMARC domain auth in SendGrid) as an onboarding step. Interim: send from your verified domain with the dealer as reply-to.
**Acceptance / real-time test:** A test email sends from the configured dealer address and arrives (check inbox vs spam). Report whether domain-auth is needed before go-live.

## T15 — EMAIL LEAD CAPTURE: PROVE WITH REAL SAMPLES  — concerns #2, #8
**Goal:** AutoTrader/CarGurus + no-phone email leads are proven against real emails.
**Files/where:** `app/adapters/intake/email_ingest.py` + parsers; no-phone path `ingest_lead_email_no_phone`.
**Steps:** Validate parsers against real sample emails (ask Manav). Confirm: phone → AI/SMS; no-phone → warm email + rep notice.
**Acceptance / real-time test:** A real AutoTrader and a real CarGurus email each create a correct lead and route correctly.

---

## T16 — THE REAL-WORLD REHEARSAL (the gate)  — concern #14
**Goal:** Prove market readiness with one clean live run. (Manav + Claude will expand the full test plan separately; this is the minimum gate.)
**Run live, on real numbers/Telegram/email, seeded inventory:**
1. Lead arrives (website-form email, 3rd-party email, manual, OR missed call → text-back) → captured < 60s.
2. AI texts Manav's real phone within seconds.
3. Manav replies as a customer → AI holds a human, grounded chat.
4. AI offers only real inventory and only valid slots.
5. AI books inside hours, no double-book.
6. The rep gets a distinct Telegram ping → taps Claim → confirmed.
7. Cover-me: reassign to another rep → distinct ping → they take it.
8. Dashboard reflects every change; rep privacy holds.
**Acceptance:** Whole loop runs clean once and is recorded. That recording is the demo asset.

---

## DEFERRED (do NOT spend time on now)
- Auto-crawl inventory from dealer websites.
- Instant after-hours response (paid upsell).
- Per-dealer email domain authentication beyond documenting it (full go-live email hardening).
- Dashboard visual polish.
- A2P 10DLC registration (required before LIVE consumer texting — start paperwork the day a dealer is closed; not a feature).

## ORDER RECAP
T1 Twilio → T2 prove AI → T3 missed-call (deploy) → T4 cover-me (deploy today) → T5 Telegram inbound + messages → T6 website-leads-via-email (today) → T7 booking guardrails → T8 login → T9 privacy → T10 business facts → T11 after-hours morning → T12 inventory upload → T13 onboarding → T14 verify send address → T15 email capture proof → **T16 live rehearsal (gate).**
