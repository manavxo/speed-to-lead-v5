# Speed to Lead v5

A speed-to-lead SMS engine for small BC used-car dealerships. The dealer gets a webform + a phone number; a lead arrives; the AI replies within 30 seconds, qualifies the customer, suggests matching cars from the dealer's live inventory, and books a test drive. The system runs 24/7. The dealer sleeps.

## The story

v4 (~6,000 LOC, 222 tests) was a sound engine that "kept failing." The failure was a small set of well-hidden bugs (Twilio signature validation was a no-op, the AI didn't see past the last message, the follow-up sender was a no-op) plus an overgrown dashboard that masked what was actually broken. v5 is a rebuild that uses v4 as a reference: it keeps the engine that works, fixes the bugs, and builds the visible product on top of a tested core.

**v5 is built validate-before-build.** The 12 P0 safety fixes land first, then one end-to-end test that exercises webform → auto-reply → rep claim → customer reply → book appointment, then the dashboard, then the AI persona, then the value-add widgets. No more "let me add one more thing and see if it works."

## Quick start

```bash
# 1. Clone
git clone <repo-url> speed-to-lead-v5
cd speed-to-lead-v5

# 2. Python 3.12+
python3.12 -m venv .venv
source .venv/bin/activate     # bash/zsh
# .venv\Scripts\activate      # Windows cmd

# 3. Install
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
# edit .env: set DATABASE_URL (sqlite for dev, postgres for prod), TWILIO_*, OPENROUTER_*
# IMPORTANT: keep OUTBOUND_ENABLED=false (DRYRUN) for all local dev

# 5. Initialize DB
python -c "from app.db import init_db; init_db()"

# 6. Run
uvicorn app.main:app --reload --port 8000

# 7. Test
pytest -v
```

For local Twilio testing: use ngrok to expose port 8000, point your Twilio number's SMS webhook to `https://<ngrok>.ngrok.io/webhook/twilio/sms`.

## Architecture

The engine is a deterministic state machine over a `Lead` row. The state machine has 11 states (NEW, AUTO_REPLIED, ASSIGNED, CLAIMED, ENGAGED, APPT_SET, SHOWED, SOLD, LOST, ESCALATED, OPTED_OUT). State transitions are audited via `LeadEvent` rows. Every state transition that sends an SMS goes through `tools/send_sms.py` — the single chokepoint that enforces opt-out, quiet hours, message sanitization, and the OUTBOUND_ENABLED dry-run gate.

The AI is OpenRouter-backed (OpenAI-compatible API), called once per inbound customer message with the last 10 messages of conversation history as context. It can call two tools: `check_inventory` and `book_appointment`. Both tools are grounded in the database; the AI is forbidden from inventing cars or prices.

Read the full pipeline review (the spec this v5 was built from): `docs/PIPELINE_REVIEW.md`.

## The 7 open owner decisions

Before Phase 1 features ship, the owner must answer 7 design questions. The review's recommendations are in `docs/PIPELINE_REVIEW.md` Section H. The 7 questions:

1. VPS or stay on Render?
2. Rep notification channel: WhatsApp or SMS?
3. Email intake on day 1, or cut from MVP and add later?
4. Per-dealer quiet-hours override: yes or no?
5. Inventory upload UX: dashboard CSV or public URL feed?
6. AI persona: 3 templates to pick from, or open text box?
7. Daily morning digest SMS: keep or cut?

## The P0 safety net

The 12 fixes that must land before any Phase 1 feature. 3 of them (P0-03, P0-09, P0-10) are already applied during migration — search for `# P0-` comments in the code. The remaining 9 are tracked in the original checklists (`docs/../PHASE_V5_CHECKLISTS.md`) and will land in Phase 0 of the v5 build.

## Project layout

```
Speed to Lead v5/
├── app/                  # FastAPI app, engine, adapters, models, dashboard
├── tools/                # Lead ingest + SMS chokepoint
├── dealers/              # Per-dealer YAML configs
├── workflows/            # SOPs the AI follows (qualify_and_book.md)
├── tests/                # pytest with FakeTwilio + FakeLLM
├── docs/                 # PIPELINE_REVIEW.md (the spec)
├── V5_MIGRATION_LOG.md   # Audit log of what was kept from v4
├── requirements.txt
├── .env.example
└── README.md
```

## License

MIT
