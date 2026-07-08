<!-- HOW TO USE: Select ALL of this file (Ctrl+A), copy, and paste it into your agent (Cline) —
or just tell the agent "read and execute PIPELINE_BRAINSTORM_PROMPT.md". It is fully self-contained.
This is a BRAINSTORM / pipeline-review task. The agent must NOT write or change any code. Its only
output is a written review document (PIPELINE_REVIEW.md) plus a discussion. We sharpen the axe
first; we swing later. -->

You are a SENIOR PYTHON / FASTAPI + TWILIO ENGINEER, a SEASONED PRODUCTION DEBUGGER who has shipped
"speed-to-lead" engines before, AND a pragmatic systems designer who is allergic to needless
complexity. You are being hired for your JUDGMENT, not your typing speed.

## THE MODE: SHARPEN THE AXE — BRAINSTORM ONLY, NO CODE
"If I had six hours to chop down a tree, I'd spend the first four sharpening the axe." We are in the
sharpening phase. In THIS run you will **read, think, and propose — you will NOT edit a single line
of code, you will NOT run migrations, you will NOT change config.** Your entire deliverable is a
written analysis (`PIPELINE_REVIEW.md`) and a focused conversation. If you feel the urge to "just
quickly fix" something, don't — write it down as a proposal instead. Execution is a later session.

## CONTEXT YOU MUST INTERNALIZE FIRST
- This codebase is **Speed to Lead v4**. It was **partially working but kept failing**, so the owner
  is planning **v5**. v4 is NOT garbage — roughly 70% is sound and must be **reused**, not rewritten.
  Your job is to separate the gold from the gravel.
- **Source of truth for what the customer must experience:** `../Phase_1_Customer_Features.md` (the
  six Phase-1 promises: instant response, real grounded conversation, booking over text, opt-out
  that truly works, privacy by default, one-customer-one-conversation across channels). If a
  proposal does not protect one of those promises, it's wrong.
- **Read before you opine** (do not skim — actually read): `AGENTS.md`, `.clinerules`,
  `docs/00-OVERVIEW.md`, `docs/01-ARCHITECTURE.md`, `docs/02-PIPELINE.md`, then the real code:
  `app/main.py`, `tools/route_lead.py`, `tools/send_sms.py`, `app/engine/lifecycle.py`,
  `app/engine/router.py`, `app/engine/conversation.py`, `app/engine/escalation.py`,
  `app/adapters/intake/{webform,twilio_sms,email_lead}.py`, `app/adapters/inventory/*`,
  `app/scheduler.py`, `app/dashboard/__init__.py`, and `dealers/example-dealer.yaml` +
  `dealers/_schema.md`. Also skim `tests/` to learn what is genuinely proven vs. what only passes
  because tests call leaf functions directly.
- **The reusable bones (default = REUSE, justify any change):** the three-axis adapter model
  (intake / inventory / organization behind canonical `Lead`/`Vehicle`/`LeadEvent`); the single SMS
  chokepoint `tools/send_sms.py` (the one place compliance lives); the deterministic state machine
  `app/engine/lifecycle.py`; the inventory-grounded AI tool-calling loop in
  `app/engine/conversation.py`; the schema incl. `ConsentLog` (CASL 7-yr audit); per-dealer
  `dealers/<slug>.yaml` onboarding; the `OUTBOUND_ENABLED` dry-run safety gate.
- **Business reality:** small/independent used-car dealers in British Columbia, Canada. Compliance =
  **CASL + PIPA BC** (NOT US TCPA/A2P). Price point ~$299–499/dealer, so every proposal must be
  **cheap to run, easy to operate, low-failure, and scalable** — and must keep what we ask the
  dealer to hand over to an absolute minimum (see Note 10).

## THE OWNER'S PIPELINE-REVIEW NOTES — TREAT EACH AS A FIRST-CLASS REQUIREMENT
These are the owner's own notes after reading the Phase-1 doc. Do NOT hand-wave them, do NOT bury
them, do NOT silently overrule them. For EACH one: confirm whether v4 already does it, then propose
the simplest reliable way to satisfy it, with tradeoffs.

1. **Form → real conversation.** After a website form is submitted, the AI must actually *engage* the
   customer in a back-and-forth, answer their questions, and do so with real context: the dealer's
   website info, **fees, services**, hours, location. It must **proactively try to book an
   appointment** for a salesperson. Map: does `route_lead.py` → `conversation.py` truly continue the
   thread, and where would "fees/services/website context" live (dealer YAML? a knowledge blob?)?

2. **Notify the salesperson on the two events that matter.** The rep must be reliably notified for
   (a) a **booked-appointment confirmation**, and (b) a **handoff request** (customer needs a human).
   After notification, the rep can **take over** the conversation. Map this to `router.py` /
   `escalation.py` / the WhatsApp claim ping, and the lifecycle states (ENGAGED, APPT_SET, handoff).

3. **Rep-notification channel: Telegram or WhatsApp — and maybe a cron.** Lay out the real options
   for notifying the salesperson (Twilio WhatsApp template vs. a Telegram bot vs. SMS), with honest
   pros/cons on cost, setup friction, the 24-hour WhatsApp session window, and reliability. Say where
   a **cron / scheduled sweep** belongs (e.g. a recurring "unacknowledged handoff" or "unclaimed
   lead" sweep) vs. an event-driven push. Recommend one default and one fallback.

4. **Missed-call text-back is the PRIORITY, and it is about reaching a HUMAN fast.** When a call is
   missed, the goal is to **connect the customer to a salesperson as fast as possible**, because some
   queries are too hard for the AI. Design the **handoff** so: (a) if the customer explicitly asks
   for a **specific salesperson**, the AI gets out of the way and routes them — it must NEVER become a
   bottleneck to a human; (b) but if the customer just has a question the AI's grounded context can
   answer, the AI still helps instead of making them wait. Define the exact decision rule for
   "answer vs. hand off," and which lifecycle state/notification each path triggers.

5. **Coachable AI, grounded on FREQUENTLY-CHANGING inventory, never pushy.** Inventory at a dealer
   changes constantly (cars added/removed/sold on the website). Propose how the AI's knowledge stays
   fresh **every time inventory changes** (the `app/adapters/inventory/*` sync ladder +
   `inventory.refresh_min` — is polling enough? webhook? on-demand check at conversation time?), and
   how the AI is "coachable" (persona/guardrails/SOP in `dealers/<slug>.yaml` + `workflows/`). It must
   suggest **smart alternatives without pressure**: red not available → mention the blue one; no Honda
   Civic → suggest the Corolla/Camry/similar you DO have, and **ask the customer their price range and
   what matters to them**. Confirm grounding can never invent a car or price.

6. **Twilio for SMS + full compliance, but no Twilio bottleneck; AI must be 24/7 on standby.** SMS to
   customers goes through Twilio via the `send_sms.py` chokepoint with CASL/PIPA enforced. But flag
   any place Twilio limits (rate limits, throughput, number capabilities, trial limits) could
   **bottleneck** us, and how to avoid it. Critically: the AI assistant must be **always-on, 24/7**,
   and **auto-activate the instant the dealer's phone number is engaged** (inbound SMS / missed call)
   — with no laptop in the loop. Survey what makes this reliable: always-on cloud hosting, the
   APScheduler worker, health checks, and whether **Claude Code skills / scheduled agents (cron) /
   tools** or a **dedicated VPS** add value. The owner is willing to spin up a VPS — say plainly when
   that's worth it vs. when managed hosting (Render/Fly/Railway) is simpler and cheaper.

7. **Conversations visible to sales staff AND the manager in the dashboard.** Reps and the manager
   must be able to look up any AI↔customer conversation in the dashboard. Map this to
   `app/dashboard/` + the `lead_detail` timeline (LeadEvent + Message stream). Identify what's missing
   for a clean, complete, per-lead conversation view.

8. **Quiet hours — keep them, but add a TESTING OVERRIDE.** Quiet hours (no outbound 21:00–08:00
   dealer-time) are correct for production, but in the last attempt they **blocked testing at 3 AM
   and caused a real headache.** Propose a clean override (e.g. a `QUIET_HOURS_ENABLED` /
   `QUIET_HOURS_OVERRIDE` flag, or a per-dealer staging bypass, or test-number allowlist) that lets us
   test any hour **without ever weakening real-customer protection or CASL compliance**. Note where it
   lives and how it stays off in prod.

9. **Email leads (AutoTrader / CarGurus / Kijiji, etc.) — THE BACKBONE.** Most third-party leads
   arrive as an **email to a dedicated dealer inbox.** The AI must **ingest that email, extract the
   lead (name/phone/vehicle), craft a reply, and respond.** This is the backbone of the product, so
   the solution must be **cheap, easy to execute, minimum failure rate, and scalable.** Compare the
   real options for getting that email INTO the pipeline (inbound-email-to-webhook services like
   Mailgun/Postmark/SendGrid Inbound Parse, IMAP polling, a forwarding rule into a parse endpoint),
   map them to the existing `app/adapters/intake/email_lead.py`, and recommend the one with the best
   reliability-per-dollar and the least dealer setup. Be explicit about parsing fragility (each
   listing site's email format differs) and how to make it robust.

10. **Minimize what the dealer must hand over.** The onboarding ask must be **short and
    non-threatening** — nothing a dealer would be uncomfortable giving access to. For every proposal
    above, list exactly what the dealer must provide (a number? an email forward? website URL?
    inventory feed?), and prefer designs that need the LEAST access while still working. Call out
    anything that would make a dealer nervous and offer a lower-friction alternative.

## WHAT TO PRODUCE — write `PIPELINE_REVIEW.md` in the repo root (a DOCUMENT, not code)
Structure it exactly like this:

### A. Pipeline-as-built (the honest map)
A concise end-to-end trace of how a lead flows TODAY for each intake channel (web form, inbound SMS,
missed call, email), naming the real functions/files at each hop, and **flagging every point where
the chain silently dead-ends or is only a stub/placeholder** (this is where v4 "kept failing" —
find it). Distinguish "proven by a real end-to-end test" from "passes only because a test calls the
leaf directly."

### B. Phase-1 feature × pipeline matrix
A table: one row per Phase-1 promise (from `Phase_1_Customer_Features.md`) AND one row per owner note
(1–10 above). Columns:
`Feature/Note | Where it lives in v4 (files) | Works? (yes/partial/stub/missing) | Verdict: REUSE / MODIFY / REPLACE / CUT | Why (one line) | Failure risk if shipped as-is`.
Default verdict is **REUSE** — you must justify any MODIFY/REPLACE/CUT with a concrete reason.

### C. Decisions to make (options with a recommendation)
For each of these open design questions, give a short options table (Option · Cost · Setup friction ·
Failure modes · Dealer-access required · Scales?) and then **your recommended default + fallback**:
  - C1. Rep notification channel: WhatsApp template vs. Telegram bot vs. SMS (Note 3).
  - C2. Event-driven push vs. cron/sweep for handoffs & unclaimed leads (Notes 2, 3).
  - C3. Missed-call → human handoff decision rule: when does the AI answer vs. step aside (Note 4).
  - C4. Inventory freshness: poll vs. webhook vs. on-demand-at-conversation (Note 5).
  - C5. 24/7 always-on hosting: managed (Render/Fly/Railway) vs. self-hosted VPS; where Claude Code
        skills/scheduled-agents/cron fit, and whether they help or add fragility (Note 6).
  - C6. Email-lead ingestion: inbound-parse webhook vs. IMAP poll vs. forward-to-endpoint (Note 9).
  - C7. Quiet-hours testing override mechanism (Note 8).

### D. The simplification pass (fewer moving parts = fewer failures)
v4 failed partly from complexity. List concrete ways to make the pipeline SIMPLER and more reliable
without losing a Phase-1 promise: things to merge, delete, replace with a managed service, or stop
doing. For each, state what reliability/maintenance we gain and what (if anything) we give up.

### E. Minimal dealer onboarding ask (Note 10)
The shortest possible list of what a dealer must provide to go live, ranked least-to-most sensitive,
with a lower-friction alternative noted for anything that could make a dealer nervous.

### F. Known-failure watchlist (so v5 doesn't repeat v4's bugs)
Review the pipeline against these real-stack gotchas and note which ones v4 is exposed to and how a
v5 design avoids them: opt-out send-after-STOP; duplicate Twilio webhook → double-text (MessageSid
idempotency must precede any send); WhatsApp 24h session window / sandbox-not-joined for rep pings;
Twilio signature 403 behind a TLS-terminating host; timezone bugs in business-hours/quiet-hours
(decide in dealer tz, store UTC); AI grounding/hallucination when inventory is empty; LLM rate-limit
→ backoff then templated fallback; tenant resolution doing a full table scan per webhook; scheduler
jobs not firing after restart; email parsing breaking when a listing site changes its format.

### G. Recommended sequence (the plan we'll EXECUTE LATER — do not execute now)
An ordered, smallest-risk-first plan that starts with a **Phase 0 safety net** (the one honest
end-to-end test + the dry-run gate so nothing can text a real customer during development), then the
highest-value fixes, each phrased as "smallest change that proves a Phase-1 promise." Mark each item
REUSE/MODIFY/REPLACE so the build session is unambiguous.

### H. Open questions for the owner
A short, prioritized list of genuine decisions only the owner can make (budget ceilings, whether to
run a VPS, which rep-notification channel they prefer, how aggressive the AI should be about booking,
etc.). Keep it tight — decide everything you reasonably can yourself and record assumptions inline.

## HARD CONSTRAINTS (do not violate)
1. **No code, no migrations, no config edits, no installs.** Read-only. Output is `PIPELINE_REVIEW.md`
   + the discussion. (You MAY create that one markdown file.)
2. **Reuse-first.** Default verdict is REUSE; the burden of proof is on changing anything. Never
   propose React/Vue/Next, Redis/Celery, new DB tables, or new infra unless you show why the existing
   approach genuinely can't work.
3. **Every promise in `Phase_1_Customer_Features.md` must survive** every proposal. If a simplification
   would weaken one, say so and don't recommend it.
4. **Cheap, easy, low-failure, scalable, minimal-dealer-access** is the scoring function for every
   option. State each of these for each recommendation.
5. **Compliance is non-negotiable:** CASL + PIPA BC, single send chokepoint, ConsentLog audit, opt-out
   honored instantly, quiet hours protected in prod even when you add a test override. Design to
   Canada, not the US.
6. **Be concrete and grounded:** cite real file/function names from this repo, not generic advice. If
   v4 already solves something, say "already handled in `<file>`" and move on — don't pad.
7. **Self-sufficient:** decide what you reasonably can, record the assumption, and keep going. Save
   true owner-only decisions for section H. Do not stop mid-review to ask one-off questions.

## WHEN DONE, GIVE ME (in one message)
- `PIPELINE_REVIEW.md` written to the repo root with sections A–H above.
- A 6–10 line executive summary at the very top: the 3 biggest reasons v4 kept failing, the 3 highest-
  leverage simplifications, and the single recommended next action.
- The decision table (section B) and your recommended default+fallback for each item in section C,
  surfaced in your reply so we can discuss them immediately.
- Your open questions (section H) as a short numbered list, most-important first.
- Explicitly confirm you changed NO code and ran NO migrations — this was a sharpen-the-axe review.
