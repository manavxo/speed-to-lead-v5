# V5 Conversation + Booking Fix Spec (for Mimo)

**Source of truth:** real live SMS test on 2026-06-24, prod dashboard **Lead #34 ("Manav", +16048392870)**, 40 msgs 5:38–8:39 PM Vancouver. A buy-ready customer who said "yes, book it" and offered to finance through the dealer was **ghosted mid-booking**. Full transcript + bug evidence is in Claude's memory `v5-lead34-booking-failure.md`. This spec turns those findings into executable fixes.

---

## ROLE
Senior Python/FastAPI engineer + production debugger. Bash is fixed. You recover from your own errors, **confirm each root cause in the code/logs before changing anything**, and never pester. Working dir: `C:\Speed to Lead v5`. Shell: bash (git-bash/MSYS), NOT PowerShell.

## HARD RULES (non-negotiable)
0. **NEVER text Manav during testing.** ALL dry-run tests run with `OUTBOUND_ENABLED=false` — this gates `send_sms`/`send_whatsapp`/`notify_rep` (returns a synthetic `DRYRUN_…` SID, persists the Message row, never calls Twilio/Telegram). No real SMS or Telegram may reach the user during dev/test. Live (post-push) verification of Twilio/Telegram happens ONLY on Manav's explicit "go ahead."
1. **TEST BEFORE PUSH.** For every fix: run the relevant unit tests **and** a real dry-run of the fixed path (simulate the actual conversation/flow). Must be green before commit.
2. **VERIFY LIVE AFTER PUSH.** After Render auto-deploys, re-run the path **through the deployed service** and confirm the fix holds in prod. "Committed = done" is NOT allowed (see memory `live-testing-over-unit-tests`).
3. **SHOW RECEIPTS per fix:** (a) pre-push test output, (b) deploy confirmation, (c) post-deploy live proof (transcript / DB row / screenshot). Record in `NOTES/FIX_RECEIPTS.md`.
4. **Confirm root cause first.** Where this spec says "suspected," prove it in code/logs before editing. If the real cause differs, fix the real one and note it.
5. **Small commits, one per fix.** `git add` specific files, never `git add -A`. Never commit red.
6. **Additive & reversible. No secrets in code.** Gate external sends behind `OUTBOUND_ENABLED` for dry-runs.
7. Run tests with `python -m pytest` (bare `pytest` errors on `v4 archived/`). Baseline: 203 passed, 1 skipped.

## HOW TO PULL A LIVE CONVERSATION (for after-push verification)
`cd tests/e2e && MAX_ID=40 node scrape_convo.js` — Playwright logs into the prod dashboard as Manager (PIN 1234), probes lead IDs directly (the default list hides advanced-state leads), and dumps each Conversation thread. Use this to read the real prod result of your fix.

## KEY FILES
- `app/engine/conversation.py` — AI engine: `handle_turn`, `_call_openrouter`, `TOOL_DEFINITIONS`, `_execute_tool_call`, leak recovery (`_looks_like_leaked_toolcall`/`_parse_leaked_tool_calls`/`_sanitize_reply`/`_TOOLCALL_FALLBACK`), `_get_model_name`. System prompt build lives here.
- `tools/check_availability.py` (T7), `tools/book_appointment.py`, `tools/notify_rep.py`
- `app/models/__init__.py` — `Message` (direction, channel, sender_role, recipient_role, ai_generated), `Appointment`, `Lead`
- `app/dashboard/__init__.py` — `login_page` (~682), `login_submit` (~722), `logout` (~858); `lead_detail` timeline build
- `app/dashboard/templates/login.html` (rep dropdown ~219-236), `lead_detail.html` (conversation thread ~123-192)
- `dealers/premier-auto.yaml` — dealer config (sales_team, manager_pin, per-rep PINs; needs `website` + availability data)

---

# TASKS (priority order)

## F0 — Model routing: send tool-critical turns to a reliable tool-calling model 🔴 (root-cause fix)
**Root cause of F1–F4:** the model is `deepseek-v4-flash` invoked with `tool_choice="auto"`. DeepSeek is unreliable at structured tool calls — it skips them or leaks them as text (see memory `deepseek-toolcall-leak`). The infra (tools registered, dealer hours present, prompt correct) is all fine; the MODEL won't use it.
**Decision (Manav, cost-constrained):** keep DeepSeek for general conversation (cheap); route **tool-critical turns** (booking / availability / inventory) to a reliable function-calling model **via the EXISTING OpenRouter client path** (no new SDK, no Anthropic — Manav's OpenRouter credits can't run Claude models).
- **Primary model: `openai/gpt-4o-mini`** (cheap, gold-standard reliable function calling, supports strict schemas + forced `tool_choice`). Alt/cheaper: `google/gemini-2.0-flash-001`.
- Put the model ID in **config/env** (e.g. `TOOL_MODEL` setting, default `openai/gpt-4o-mini`) so it's swappable without code changes.
**Wiring (do it cleanly — this is a SMALL change, the OpenRouter path already passes `tools=TOOL_DEFINITIONS`):**
- In `app/engine/conversation.py`, make the **client + model turn-aware**: a small **model router** detects tool-critical / booking-intent turns and, for those, uses the **OpenRouter client** (`openrouter_api_key`/`openrouter_base_url`) with `TOOL_MODEL`; all other turns keep the current DeepSeek default. Keep one shared tool-execution interface — don't fork the loop.
- On tool-critical turns set `tool_choice` to REQUIRE the tool (OpenAI style: `{"type":"function","function":{"name":"check_availability"}}`, then `book_appointment` on confirm) — not `"auto"`. Use strict tool schemas if the model supports it.
- `OPENROUTER_API_KEY` is ALREADY set in local `.env` AND Render env (confirmed) — no setup needed. **F0 step 1: make ONE cheap test call to `openai/gpt-4o-mini` through the OpenRouter client (OUTBOUND_ENABLED=false, no SMS) to confirm the existing key has access + credit for this model BEFORE building the router.** If it fails (no credit/access), fall back to `google/gemini-2.0-flash-001` and note it.
**Test:** unit test asserts the router routes a booking-intent turn to the OpenRouter `TOOL_MODEL` path with forced `tool_choice`, and that a leaked/garbled tool call can't occur because the call is structured. Run with `OUTBOUND_ENABLED=false`.
**Verify live:** once `OPENROUTER_API_KEY` is set, a booking convo through prod actually calls the tool and books (appointment in dashboard + DB).

## F1 — Booking must actually execute (fix at ALL FOUR layers) 🔴
**Symptom:** AI said "let me book it" 5+ times (7:34–7:37) but never created an appointment, never confirmed; customer ghosted at 7:37.
**Required: prove and fix at each layer — none may remain broken.**
- **Model/wiring:** see **F0** — route this turn to the OpenRouter `TOOL_MODEL` (`openai/gpt-4o-mini`) with forced `tool_choice` so the call is structured and actually executes. Confirm `book_appointment` is in `TOOL_DEFINITIONS` and routed in `_execute_tool_call`.
- **Backend logic:** `check_availability` returns deterministic real slots (already correct); `book_appointment` must create an `Appointment` row and return a concrete confirmation (date/time). AI answers from tool results only.
- **Data:** `dealers/premier-auto.yaml` already has real business hours (Mon–Fri 9–7, Sat 10–5, Sun closed, tz America/Vancouver). **Scheduling stays dealer-wide for now** — `check_availability` = dealer hours minus booked appointments.
  - **REQUIRED — leave a clearly-documented per-rep provision (flip-the-switch seam), do NOT build the feature:**
    - Add a config key `scheduling_mode: "dealer_wide" | "per_rep"` (default `"dealer_wide"`) in the dealer YAML schema, and read it in `check_availability`. Only the `dealer_wide` branch is implemented; the `per_rep` branch is a clearly-marked stub that raises `NotImplementedError("per-rep scheduling not yet built — see PER_REP_SCHEDULING.md")`.
    - Keep/populate the existing `rep_name` field on each slot dict as the carrier for the future per-rep path (note in a comment that it's intentionally part of the seam).
    - Add a top-of-file docstring/comment block in `tools/check_availability.py` AND a short `NOTES/PER_REP_SCHEDULING.md` that spell out — in plain language — exactly what to change to turn it on (where rep hours would live in config, how slots would be filtered per rep, what tests to add). Write it so a future reader (or Manav) immediately sees how to flip it on. **Make it obvious and impossible to miss.**
- **AI/prompt:** system prompt rule — **never say "let me book"/"I'll lock it in" without calling `book_appointment`; only claim it's booked AFTER the tool returns success, and echo the concrete confirmed time.** No looping.
**Test (before push):** unit/dry-run replays the Lead #34 booking sequence ("yes book me Thursday 2pm" …) → asserts (a) an `Appointment` row is created, (b) reply contains a concrete confirmation, (c) no repeated "let me book" with no action. Run with `OUTBOUND_ENABLED=false`.
**Verify live (after push):** run a real booking convo through prod via SMS dry-run/scraper → appointment appears in dashboard + DB.

## F2 — Tool-recovery must return REAL answers, not fluff 🔴
**Symptom:** "What engine does the Kona have?" (asked twice) → generic `_TOOLCALL_FALLBACK` "Thanks! Let me pull that up — what's most important to you…". Raw-markup leak is hidden, but the customer still gets a non-answer.
**Suspected cause:** recovery re-prompts WITHOUT tools but without a successfully-executed result, or the fallback fires instead of a real answer.
**Fix:** recovery path must parse the leaked call → execute it → feed the REAL result back → re-prompt for a grounded answer. Only use the generic fallback when truly unrecoverable; never replace an answerable question with fluff.
**Test:** feed the exact leaked `check_inventory` Kona case → assert reply contains real spec data, not the fallback string.
**Verify live:** ask a spec question over SMS → real answer.

## F3 — `max_turns_reached` must not cut off mid-booking 🔴
**Symptom:** at 7:34, as the customer said "yes book it," engine hit the turn cap, flipped ENGAGED→ASSIGNED, sent "a rep will follow up," then kept talking anyway.
**Fix:** raise/relax the cap and/or do not trigger the handoff while the customer has active booking intent; never send a handoff message and then continue. Booking intent extends or bypasses the cap.
**Test:** a >N-turn convo that reaches booking → no premature handoff, booking completes.

## F4 — Internal notifications must NEVER reach the customer thread or SMS 🔴
**Symptom:** raw `[CLAIM] {'rep_name':'Helly'…}` dicts and "Lead Manav (+16048392870) unclaimed after timeout. Please review." rendered in the customer thread, tagged "AI Assistant."
**FIRST: confirm whether any of these went out over SMS** (check the `Message` rows' `channel`/`recipient_role` + Twilio logs). If yes, that's a customer-facing leak of internal ops + the customer's own number — escalate severity.
**Fix:** rep/claim/cover/unclaimed notifications route to Telegram/rep channel only — never `channel=sms`/`recipient_role=customer`, and never render in the customer Conversation card (separate as internal events or exclude).
**Test:** trigger claim/cover/unclaimed-timeout → assert no customer-channel Message created; customer thread renders no raw dicts/HTML.

## F5 — Conversation style: concise, formatted, emojis, strong CTA 🟠
**Ask (Manav):** responses too verbose; want SMS-native brevity, clean formatting, tasteful emojis, and a clear call-to-action in every message driving toward the booking.
**Fix:** update the system prompt / persona guidelines — 1–3 short sentences, scannable, 1–2 relevant emojis, end with a concrete CTA ("want me to lock in Thursday 2pm? 🚗").
**Test:** sample conversations → assert avg message length under threshold, CTA present, no walls of text. Manual eyeball on tone.

## F6 — Share the dealer website link 🟠
**Symptom:** "Can you give me your website?" → "I'm not able to send links."
**Fix (data + code):** add `website:` URL to `dealers/premier-auto.yaml`; surface it to the AI (prompt context or a small tool) so it shares the real link on request. Remove the blanket link refusal. Do NOT let it invent a URL — only share the configured one.
**Test:** ask for the website → reply contains the configured URL.

## F7 — Compliance footer: once per customer, never duplicated 🟠
**Symptom:** "Reply Stop to opt out…" appended to nearly every message, sometimes 2–3× in one message.
**Suspected cause:** footer appended on every outbound send (and re-appended by another layer).
**Fix:** append the consent/opt-out footer only on the FIRST message to a customer; dedupe so it can never appear more than once.
**Test:** multi-message convo → footer appears exactly once (first message), never duplicated.

## F8 — Login: one central link populates reps for any dealer slug 🟠
**Root cause (confirmed):** `login_page` fills the rep dropdown only from the `dealer_slug` **query param at load**; `logout` redirects to bare `/dashboard/login` (no slug) → `sales_team=[]` → template renders a single hardcoded `Manager` option (`login.html:233-235`); typing the slug doesn't refresh the dropdown (no JS).
**Fix:** add a GET endpoint (e.g. `/dashboard/api/sales-team?dealer_slug=X`) returning team names + `show_manager_option`; add JS to `login.html` that fetches and repopulates the rep dropdown on `dealer_slug` change/blur. (Also OK to have `logout` preserve `?dealer_slug=` in the redirect.) One central `/dashboard/login` link must let every rep pick their profile.
**Test:** load `/dashboard/login` (no slug), type `premier-auto` → dropdown shows Helly/Vishva/Manager. E2E: login as Helly → logout → re-enter slug → Helly selectable → login succeeds.

## F9 — Claim must stick (stop the timeout loop) 🟠
**Symptom:** ASSIGNED↔ESCALATED claim_timeout loop at 7:39/7:45/7:51/8:38; Helly's `[CLAIM]` records but state reverts.
**Suspected cause:** claim handler records the tap but never transitions state to CLAIMED, so round-robin/timeout keeps firing.
**Fix:** claim sets state=CLAIMED, stops the timeout/round-robin loop.
**Test:** simulate a claim → state=CLAIMED, no further claim_timeout transitions.

## F10 — Cleanup: greeting placeholders, duplicate sends, raw HTML 🟡
**Symptoms (other leads):** `[Your Name]`/"Hi Number!"/"Hi Test Lead!" (#10/#25); consent+intro sent twice + Rep/AI mis-attribution (#18/#25); literal `<b>COVER REQUEST</b>` HTML in thread (#32/#33).
**Fix:** resolve persona name + customer name from config/lead (never ship placeholders); idempotency so consent/intro aren't double-sent; correct `sender_role` attribution; escape/route HTML out of the customer thread.
**Test:** new lead → exactly one consent + one intro, correct name, correct `sender_role`; cover request absent from customer thread.

## F11 — Telegram pipeline: round-robin + booked-appointment rep notification 📲
**State (confirmed in code):** the wiring EXISTS — `notify_rep` defaults to the `telegram` backend; reps carry `telegram_chat_id` in `dealers/premier-auto.yaml`; `TelegramTransport` posts to the real Telegram API when `TELEGRAM_BOT_TOKEN` is set and cleanly dry-runs when it's blank (that's the current "placeholder"). `book_appointment` already calls `notify_rep` with an `appointment_set` payload, and round-robin assignment runs on booking.
**Manav prefers NOT to provide a bot token yet** — so verify everything in DRYRUN; live delivery is one deferred step.
**Fix/verify:**
- Round-robin assigns a booked lead to the correct active rep (`app/engine/router.py`).
- On booking, an `appointment_set` notification is dispatched to that rep's `telegram_chat_id` with a clean, human-readable body (no raw dicts/HTML — ties to F4/F10).
- Confirm the rep notification path is separate from the customer thread (never `channel=sms`/`recipient_role=customer`).
**Test (DRYRUN, `OUTBOUND_ENABLED=false`):** simulate a booking → assert `notify_rep` is called with `backend=telegram`, the right `telegram_chat_id`, and a well-formed appointment message; assert nothing is sent to the customer channel.
**Deferred live step (mark clearly in `FIX_RECEIPTS.md`):** set `TELEGRAM_BOT_TOKEN` (Render env) → real Telegram delivery to the rep. Do NOT do this until Manav provides the token / says go.

---

## SUGGESTED SEQUENCE
1. **F0** first (model routing — Haiku 4.5 for tool turns). It's the root cause; F1–F4 largely collapse once tool calls are structured + forced.
2. **F1+F2+F3** together (booking executes / real answers / no mid-booking cutoff) — the demo-killer.
3. **F4** (leak audit — confirm no internal-note SMS leak; compliance/privacy risk).
4. **F7, F5, F6** (message quality & content).
5. **F8** (login — unblocks multi-rep demo).
6. **F9, F11** (claim sticks + Telegram round-robin/appointment notification, DRYRUN).
7. **F10** (cleanup).

## DEFINITION OF DONE
Every task: tests green pre-push + live-verified post-deploy + receipt logged in `NOTES/FIX_RECEIPTS.md`. The Lead #34 scenario, re-run end-to-end through prod, results in a **confirmed booked appointment** (visible in dashboard + DB), concise on-brand messaging with working CTAs, no leaked internal notes, and every rep able to log in from the single central link.
