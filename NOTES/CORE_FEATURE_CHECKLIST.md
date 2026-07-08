# Core Feature Checklist — What's Promised, What to Test

> Compiled from `v5-MIGRATION-BIBLE/PRD_HUMAN.md` (the north star — what the world
> expects) and `v5-MIGRATION-BIBLE/_AGENT_EXECUTION_DOCS/01_ARCHITECTURE.md` (the
> current channel/role architecture), cross-checked against `git log` since the
> last written status doc (`02_CODEBASE_AUDIT.md`, dated 2026-06-19 — ~50 commits
> stale as of today, 2026-07-07). Where the audit doc says something is a stub,
> a later commit message suggests otherwise — those are flagged below as
> "confirm," not assumed fixed or assumed broken.

Status column meaning: **untested** = plausibly built, never verified end-to-end
this session. Nothing here is marked done — that's the point of this checklist.

---

## A. Customer-Facing Promises

| # | Promise | Source | Status |
|---|---|---|---|
| A1 | Any inbound channel (SMS, WhatsApp, webform, email, missed call) gets a response within 60 seconds | PRD_HUMAN §1 | untested |
| A2 | Missed call → SMS text-back triggered automatically | ARCHITECTURE.md, CALL_DETECTION.md | untested — audit called this a stub; commit `94505e4 fix(missed-call): repair broken voice webhook SMS sender + dedup window` postdates that |
| A3 | AI only references real inventory — never invents a car, price, or spec | PRD_HUMAN §2 | untested (this is what `scripts/engine_test_harness.py` D1-D3 already targets) |
| A4 | AI says "we don't have that" honestly instead of guessing when inventory doesn't match | PRD_HUMAN §2 | untested (harness D2/S2 targets this) |
| A5 | AI offers only within-business-hours appointment slots | PRD_HUMAN §3 | untested |
| A6 | No double-booking — two customers can't land the same rep/slot | PRD_HUMAN §3 | untested |
| A7 | Booked appointment shows on rep's dashboard with customer name, car, phone, full history | PRD_HUMAN §3 | untested |
| A8 | STOP = instant, code-enforced unsubscribe; no further messages ever, even from queued/scheduled sends | PRD_HUMAN §4 | untested |
| A9 | START re-subscribes | PRD_HUMAN §4 | untested |
| A10 | Reasonable-intent opt-out phrasing (not just literal "STOP") is honored | PRD_HUMAN §4 | untested — likely not implemented (needs NLP-ish matching); confirm scope with owner before testing |
| A11 | Quiet hours (9pm–8am dealer-local) enforced on every outbound customer message | PRD_HUMAN §4 | untested |
| A12 | Only minimum data collected (name, phone, vehicle interest); consent logged w/ timestamp | PRD_HUMAN §5 | untested |
| A13 | Data deletion request → hard delete within 72h, compliance log entry remains | PRD_HUMAN §5 | untested — likely NOT built (no deletion endpoint found in audit or recent commits); confirm scope |
| A14 | Same customer across SMS/webform/call/email = one thread, one history (phone-based dedup) | PRD_HUMAN §6 | untested |
| A15 | Returning customer (weeks/months later) is recognized, not treated as brand new | PRD_HUMAN §6 | untested |
| A16 | Tone matches the dealer's configured persona, never sounds like a call-center bot | PRD_HUMAN §2 | untested (harness S1/S8 partially covers, human judgment call) |

## B. Sales Rep-Facing

| # | Promise | Source | Status |
|---|---|---|---|
| B1 | Rep login via dealer + name + PIN, own PIN per rep | ARCHITECTURE.md | untested — commit `77f9bf7 feat(dashboard): per-rep PIN login` suggests built |
| B2 | Rep sees only their assigned + unassigned leads, never another rep's leads | ARCHITECTURE.md, "Rep Profile" | untested |
| B3 | Rep can claim an unassigned lead | ARCHITECTURE.md | untested |
| B4 | Only the actual assigned rep can claim/act on a lead assigned to them (identity check) | 02_CODEBASE_AUDIT.md "HIGH" #7 | untested — `tests/test_claim_identity.py` exists, run it and confirm it's not a stale/soft check |
| B5 | Rep can request a transfer; manager approves/rejects | ARCHITECTURE.md | untested |
| B6 | Rep can mark outcome: SOLD / LOST / NOT_INTERESTED | ARCHITECTURE.md, PRD_HUMAN | untested |
| B7 | Rep sees own stats: leads handled, appointments, close rate | ARCHITECTURE.md | untested |
| B8 | Rep gets Telegram notification for their own leads only (hot 🟢 vs triage 🔵 framing) | ARCHITECTURE.md | untested — Telegram is now built per `dealers/premier-auto.yaml` (`notify_backend: telegram`) and commit `7960f0e feat(telegram): inbound webhook + chat_id capture + inline claim/pass buttons`; audit doc saying "never built" is stale |
| B9 | Rep can claim/pass a lead directly from the Telegram inline buttons | commit `7960f0e` | untested |
| B10 | One-tab workflow — rep never has to leave the dashboard to act on a lead | PRD_AGENT Test 8 | untested |
| B11 | Full conversation history + AI summary visible on lead detail, no hunting for context | PRD_HUMAN §3 | untested |

## C. Manager / Owner-Facing

| # | Promise | Source | Status |
|---|---|---|---|
| C1 | Manager sees ALL leads across the dealership, can filter by rep | ARCHITECTURE.md | untested |
| C2 | Manager can reassign leads, with reason + audit trail | ARCHITECTURE.md | untested |
| C3 | Manager can approve/reject rep transfer requests | ARCHITECTURE.md | untested |
| C4 | Manager sees team performance / rep comparison | ARCHITECTURE.md, `team.html`/leaderboard | untested |
| C5 | Manager gets Telegram escalation after 3 rep passes on a lead | ARCHITECTURE.md, CODEBASE_AUDIT "Manager escalation" | untested |
| C6 | Manager can add/edit/remove reps | ARCHITECTURE.md | untested |
| C7 | Manager can manage dealer settings from the dashboard (no YAML editing) | PRD_HUMAN "What the Dealer Does NOT Have to Do" | **known gap** — 02_CODEBASE_AUDIT.md flagged settings-page save buttons as UI stubs (`showToast()` only, no persistence); no later commit mentions fixing this — confirm first, likely still broken |
| C8 | Manager can upload/manage inventory via dashboard CSV/XLSX, incl. per-row mark-sold/relist and full-sync | PRD_HUMAN, commits `14fe7b0`/`612ebdd`/`c3702d7`/`14550ca` | **already verified working** per `NOTES/FIX_RECEIPTS.md` (live prod verification, 2026-06-27) |
| C9 | Onboarding a new dealer requires no IT setup — self-serve or ≤5 min of dealer time | PRD_HUMAN "Hard Truth #4" | untested — admin onboarding wizard exists (`app/admin/`), but "5 minutes, no help" is a UX claim, not just a functional one |

## D. System-Level / Cross-Cutting Guarantees

| # | Promise | Source | Status |
|---|---|---|---|
| D1 | Every outbound customer message passes through the `send_sms` chokepoint (opt-out, quiet hours, sanitization, DRYRUN gate) — no side-channel sends | README, ARCHITECTURE.md | untested at the "no bypass exists" level — worth an audit-style grep pass (search for any Twilio call outside `tools/send_sms.py`), not just a functional test |
| D2 | Every dealer-facing notification passes through the `notify_rep` chokepoint | ARCHITECTURE.md | untested, same caveat as D1 |
| D3 | State machine transitions are always logged as `LeadEvent` rows (no direct `lead.state = X` bypass) | 02_CODEBASE_AUDIT.md "HIGH" #3 (`greeting_only` bypass) | untested — flagged broken in the stale audit, no later commit obviously fixes it; confirm |
| D4 | System degrades gracefully when Twilio/DB/DeepSeek/Telegram is down — no crash, no silent data loss | PRD_AGENT Test 1 | untested |
| D5 | 3am unattended operation: AI still responds, cron/scheduler recovers from a crashed tick, dealer notifications still respect quiet hours (dealer notify ≠ customer quiet hours) | PRD_AGENT Test 6 | untested |
| D6 | AI never claims a booking succeeded when the tool call didn't actually create the appointment (anti-hallucination) | commit `0bbafba fix(engine): book appointments via bounded tool loop + anti-hallucination guard` | untested — harness D8 already targets this |
| D7 | No leaked tool-call markup ever reaches the customer's SMS | commit `1511f5a` | untested — harness D6 already targets this |
| D8 | AI never re-greets mid-conversation (treats an ongoing thread as ongoing) | commit `b586823` | untested |
| D9 | Dealer YAML config is validated at load time — malformed phone numbers, etc. fail loudly instead of silently breaking routing | This session's incident (masked phone numbers broke `normalize_phone`) | **not yet built** — this is Phase 2 of `NOTES/HERMES_CLEANUP_SECURITY_SPEC.md`, still pending |

## E. Explicitly Out of Scope — verify they correctly do NOT happen / fail gracefully, don't build tests expecting them to work

Per PRD_HUMAN.md "Boundaries" table:
- AI phone calls (voice AI) — only missed-call detection is in scope
- Facebook/Instagram DMs
- CRM sync (Salesforce/HubSpot) — stubs only, expected
- Multi-location dealer support — one config = one dealership
- Reseller portal

---

## Known conflicts in the source docs worth flagging to Manav

1. **`01_ARCHITECTURE.md` (dated Jun 19) claims to supersede `PRD_HUMAN.md`, but `PRD_HUMAN.md`'s own header says "Version 1.0 — written June 20, 2026"** — one day *after* the doc that calls it stale. Likely a typo in one of the two dates, but worth a 10-second confirm since it affects which doc is "the north star" when they disagree (they don't disagree on much, mainly Telegram vs WhatsApp for dealer notifications, and the ARCHITECTURE.md version matches what's actually in the code).
2. **`02_CODEBASE_AUDIT.md` is ~50 commits stale.** Several things it lists as "broken" or "never built" (Telegram, missed-call SMS, per-rep PINs, booking anti-hallucination, inventory sync) have visible fix/feat commits after Jun 19. Do not use that doc's status table as current truth — re-verify everything in this checklist fresh rather than trusting either the old "broken" or assuming "the commit fixed it."

---

*Next step: pick a test method per section (A-D) — likely a mix of the existing
`scripts/engine_test_harness.py` pattern for the AI/conversation items, `pytest`
for the deterministic backend logic, and a live-browser Playwright pass (like
`tests/e2e/`) for the dashboard/role-permission items. Not designed yet —
that's the next conversation.*
