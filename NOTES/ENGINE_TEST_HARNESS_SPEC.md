# Engine Test Harness — Execution Spec (for Mimo)

**Goal:** Prove the AI/SMS engine actually helps the sales process. Drive the real
conversation engine in-process (no phone, no Twilio), check the hard criteria
automatically, capture every transcript, and write ONE report a human reads at the end.

**Owner split:** Mimo builds + runs this and fills the deterministic checks. The
sales-quality judgment calls are flagged in the report for Claude + Manav to read —
do NOT have the AI grade its own conversational quality as pass/fail.

---

## Ground rules

1. **No real sends.** Run with `OUTBOUND_ENABLED=false`. In that mode `send_sms`,
   `send_whatsapp`, and `notify_rep` all return a `DRYRUN_*` sid and still persist
   the `Message` row — so we can assert "a rep was notified" without any Twilio/
   Telegram traffic. Confirm the env before running.
2. **Use the REAL model, not `fake_llm`.** The whole point is to test the actual
   DeepSeek/GPT-4o-mini behavior. Call `handle_turn(...)` WITHOUT the `fake_llm`
   arg. This costs a small amount of LLM API spend (DeepSeek for chat + GPT-4o-mini
   for tool-critical turns via OpenRouter). It costs ZERO Twilio. Note the rough
   token spend in the report.
3. **Env keys required:** `OPENROUTER_API_KEY` (so tool-critical turns route to the
   reliable function-calling model) and `DEEPSEEK_API_KEY` (chat). If `OPENROUTER_API_KEY`
   is missing, tool turns fall back to DeepSeek — the harness MUST detect this and
   print a loud warning in the report, because booking reliability degrades without it.
4. **Fresh state per scenario.** Each scenario gets its own seeded lead on an
   in-memory SQLite DB. Reuse the seeding pattern in `test_t2_ai_engine.py` and the
   fixtures in `tests/conftest.py`.
5. **Use the REAL dealer config for routing.** Load `dealers/premier-auto.yaml` as
   the dealer_config so the test exercises the actual sales_team + Telegram routing,
   not a hand-built dict. In that file Helly is the only `active: true` rep
   (`notify_backend: telegram`, `telegram_chat_id: "8990699115"`), so every booked
   lead round-robins to her — assignment is deterministic.
6. **Telegram never fires in dry run — by design.** In `notify_rep`, the
   `OUTBOUND_ENABLED=false` gate returns a `DRYRUN_*` sid and logs the rep `Message`
   row BEFORE the `backend == "telegram"` branch. So no real Telegram message is
   sent and Helly's phone does NOT buzz. We verify the notification by inspecting the
   logged record + the assigned rep, not by anyone receiving it.
5. **Deterministic clock.** Pass a fixed `now=` into `handle_turn` and the booking
   tools so business-hours/availability are stable. Pick a weekday inside dealer hours
   (e.g. a Thursday 10:00 local, like `frozen_now` in conftest).

---

## What to build

A standalone runner: `scripts/engine_test_harness.py` (runnable as
`python scripts/engine_test_harness.py`). It:

- Seeds the dealer + a known inventory (reuse the 5-vehicle set in
  `test_t2_ai_engine.py`; add 1–2 more so "not in stock" tests are unambiguous).
- Runs each scenario below as a sequence of `handle_turn` calls on its own lead.
- After each turn, records: the customer message, the AI reply text, `tools_used`,
  the lead state, and any DB side-effects (Appointment rows, rep Message rows).
- Evaluates the deterministic checks (D1–D8) in code → pass/fail.
- Writes `NOTES/ENGINE_TEST_REPORT.md` (format at the bottom).

Key engine facts to wire against (already verified in the code):
- `handle_turn(session, lead, inbound_text, *, dealer_config, now=...)` returns
  `{"mode", "text", "tools_used": [...]}`.
- Tools the model can call: `check_inventory`, `check_availability`, `book_appointment`
  (names land in `tools_used`).
- A successful booking creates an `Appointment` (status `"set"`), transitions the
  lead to `APPT_SET`, and fires `notify_rep(message_type="appointment_set")`, which
  in dry-run logs a `Message` row with `recipient_role="rep"`. Assert on that row to
  prove the rep notification wired through.
- Leaked tool-call markup is scrubbed by `_sanitize_reply`; the marker list is
  `app.engine.conversation._TOOLCALL_MARKERS`. Reuse that exact list for D6.
- **Footer caveat:** the CASL footer is appended in `app/main.py` (the
  `_run_ai_and_send` background path), NOT inside `handle_turn`. So the footer-dedup
  check (D7) MUST drive through the main.py send path, not `handle_turn` directly.
  Find that function, call it twice for the same lead, and assert footer count.

---

## Scenarios

Each scenario = one fresh lead + a scripted sequence of customer messages.

**S1 — Inventory truth (broad ask).**
"Hi, what SUVs do you have under $35k?"
→ Expect `check_inventory` fired; reply names only real seeded cars; ≤3 cars.

**S2 — Inventory honesty (not in stock).**
"Do you have a 2024 Ferrari 488?"
→ Expect no fabricated match; AI says it doesn't have it / offers a real alternative.

**S3 — Specific car depth.**
"Tell me about the Hyundai Tucson — what engine and color?"
→ Expect `check_inventory` fired; specs in reply match the seeded `raw` data
(engine "2.5L I4", color "Phantom Black"); no invented specs.

**S4 — Real booking (the money path).**
Turn 1: "I want to test drive the Tucson, can I come by?"
Turn 2: "What times are open?"  (expect `check_availability`)
Turn 3: "Book me for <a slot the tool returned>." (expect `book_appointment`)
→ Assert the booking actually happened (D4) and the rep got notified (D5).

**S5 — Availability honesty.**
Across S4, capture every clock time the AI offers and assert each one is a member
of the `check_availability` result set for that lead. No invented slots.

**S6 — Leak / sanitization.**
Run all scenarios; for EVERY customer-facing reply, assert no tool-call markers
present (D6). This rides along on all scenarios, not a separate one.

**S7 — Footer dedup.**
Via the main.py send path: first customer-facing message → footer present once;
second message → no additional footer. Assert total footer occurrences across the
thread == 1 (D7).

**S8 — Objection handling (judgment, transcript only).**
"I'm just looking, not ready to buy." then "what's your best price?"
→ No deterministic pass/fail. Capture transcript for human read.

---

## Deterministic checks (Mimo scores these — pass/fail)

- **D1** `check_inventory` appears in `tools_used` on inventory questions (S1, S3).
- **D2** No hallucinated vehicle: every year/make/model or price quoted in an
  inventory reply maps to a real row in the seeded DB. (Match make+model tokens and
  any `$` figure against the inventory table. Flag anything quoted that isn't in stock.)
- **D3** ≤3 vehicles listed in any single inventory reply.
- **D4** After S4: an `Appointment` row exists for the lead (status `set`), lead
  state == `APPT_SET`, and `scheduled_for` equals a slot `check_availability` returned.
- **D5** After S4, verify the WHOLE assignment + notification chain (dry run, no
  real send):
  - `lead.assigned_rep == "Helly"` (round-robin assigned the lead).
  - A `Message` row with `recipient_role="rep"` exists for the lead (the
    appointment_set notification was logged through `notify_rep`).
  - The notification routed to Helly's Telegram target — assert the resolved rep
    config used `notify_backend == "telegram"` and `telegram_chat_id == "8990699115"`
    (capture the `NotificationResult` / resolved rep_config to prove the exact
    destination, even though nothing was actually sent).
- **D6** No string from `_TOOLCALL_MARKERS` appears in ANY customer-facing reply.
- **D7** The CASL footer text appears exactly once across the customer thread (S7).
- **D8** No reply claims "booked/confirmed/all set" UNLESS `book_appointment` is in
  `tools_used` for that turn AND it returned success. (Catches the Lead #34 failure
  where the AI said it booked but never called the tool.)

## Judgment flags (NOT scored — captured for Claude + Manav)

- Did it curate (2–3 cars + a benefit hook + a question), or dump a spec sheet?
- Tone: warm and human, or robotic / pushy?
- Objection grace (S8): did it stay no-pressure and keep a next step open?
- Cross-sell / qualifying intelligence where natural.

---

## Report format — write to `NOTES/ENGINE_TEST_REPORT.md`

```
# Engine Test Report — <date>

## Run info
- Model (chat): <name>   Model (tool turns): <name or "FELL BACK TO DEEPSEEK ⚠️">
- OUTBOUND_ENABLED: false   Approx LLM tokens used: <n>

## Hard checks (deterministic)
| ID | Scenario | Check | Result |
|----|----------|-------|--------|
| D1 | S1 | check_inventory fired | ✅ / ❌ |
| ...| ...| ...   | ... |

## Failures — detail
<for each ❌: the scenario, what was expected, what actually happened, the offending text>

## Transcripts
<full customer/AI back-and-forth for every scenario, including S8>

## Judgment flags (for human review)
<bullet notes on selling style / tone / objection handling, pointing at transcript lines>
```

## Done = 
- `scripts/engine_test_harness.py` runs clean with `python scripts/engine_test_harness.py`.
- `NOTES/ENGINE_TEST_REPORT.md` is written with all D1–D8 scored and every transcript captured.
- Any ❌ has a clear "expected vs actual" so the fix is obvious.
- Do NOT fix engine bugs in this pass — just report them. Fixing is a separate decision.
