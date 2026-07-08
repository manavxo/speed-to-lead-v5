# Speed to Lead v4 — Agent Instructions

You are building Speed to Lead v4, a speed-to-lead response engine for small car dealerships in BC, Canada.

## What This Project Does

Captures leads from multiple channels (web forms, SMS, email), auto-replies via SMS in under 60 seconds, routes leads to sales reps via WhatsApp (round-robin), uses AI to qualify leads and book test drive appointments, escalates if reps don't claim within SLA windows, and complies with CASL + PIPA BC.

**Target customers:** Small used-car dealerships in British Columbia (2-10 salespeople).
**Revenue target:** $5-7k/month ($299-499/dealer).

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Web framework | FastAPI (Python 3.12) | Async, fast, great docs |
| Database | Postgres (prod) / SQLite (tests) | Render includes Postgres |
| ORM | SQLModel + SQLAlchemy | Already wired |
| Validation | Pydantic v2 | Type-safe configs |
| SMS/WhatsApp | Twilio SDK | Industry standard |
| AI | OpenRouter (OpenAI-compatible) | Swap models easily |
| Templates | Jinja2 + HTMX | No JS framework needed |
| Scheduler | APScheduler (in-process) | Background tasks |
| CSS | Custom properties (dark theme) | No build step |
| Auth | Session-based (cookie) | Simple |
| Deploy | Render.com | Auto-deploy, $7/mo |

## File Structure

```
Speed to Lead v4/
├── app/
│   ├── main.py              # FastAPI app + webhook routes + lifespan
│   ├── config.py             # Settings (env) + DealerConfig (YAML)
│   ├── db.py                 # Database layer
│   ├── scheduler.py          # Background jobs (merged into lifespan)
│   ├── engine/
│   │   ├── lifecycle.py      # State machine (KEEP — don't modify)
│   │   ├── router.py         # Round-robin assignment
│   │   ├── conversation.py   # AI orchestration
│   │   └── escalation.py     # Timeout handler
│   ├── models/
│   │   └── __init__.py       # Lead, Vehicle, Message, LeadEvent, Appointment, ConsentLog
│   ├── adapters/
│   │   ├── intake/           # Webform, SMS, email intake adapters
│   │   ├── inventory/        # Vehicle feed adapters
│   │   └── organization/     # CRM/output sinks
│   └── dashboard/
│       ├── __init__.py       # Dashboard routes (TO BUILD)
│       └── templates/        # 7 Jinja2 templates (TO WIRE)
├── tools/
│   ├── route_lead.py         # Core ingest pipeline (KEEP)
│   ├── send_sms.py           # Messaging chokepoint (KEEP)
│   ├── check_inventory.py    # Vehicle search (KEEP)
│   └── book_appointment.py   # Appointment creation (KEEP)
├── tests/                    # Test suite (126 passing)
├── dealers/                  # YAML configs per dealer
├── workflows/                # AI conversation SOPs
├── docs/                     # These instruction files
├── Dockerfile                # Container config
├── start.sh                  # Startup script
├── render.yaml               # Render blueprint
└── .env.example              # Environment variables
```

## How to Run Locally

```bash
# Install dependencies
pip install -e ".[dev]"

# Set environment variables (copy .env.example to .env)
cp .env.example .env
# Edit .env with your values

# Initialize database
python -c "from app.db import init_db; init_db()"

# Run tests
pytest -q --tb=short

# Start the app
uvicorn app.main:app --reload

# Visit http://localhost:8000/dashboard/leads
```

## Key Design Decisions

1. **Three-axis adapter model:** Every integration is an adapter on one of three axes: intake (where leads come from), inventory (where vehicle data comes from), organization (where data goes). This means new integrations are just new adapter files — no core code changes.

2. **Single messaging chokepoint:** ALL outbound messages flow through `tools/send_sms.py`. This is the ONLY module that calls Twilio. It enforces compliance (opt-out check, quiet hours, footer append) before sending.

3. **Append-only event log:** `LeadEvent` is an append-only table that records every state change with a JSON payload. This is the canonical audit trail.

4. **OUTBOUND_ENABLED safety gate:** When false (the default), no real Twilio calls are made. A synthetic DRYRUN SID is returned. This lets you test the full pipeline without sending real SMS.

5. **DealerConfig YAML:** Each dealership has a YAML file in `dealers/<slug>.yaml` that declares business hours, team members, phone numbers, AI personality, and adapter selections. This is how you onboard a new client without touching core code.

## API Endpoints

### Webhooks (Twilio)
- `POST /api/webhooks/sms` — Inbound SMS from Twilio
- `POST /api/webhooks/whatsapp` — Inbound WhatsApp from Twilio
- `POST /api/webhooks/voice` — Voice call webhook

### Webhooks (Intake Adapters)
- `POST /api/intake/webform` — Website form submission
- `POST /api/intake/email` — Email parser webhook

### Health
- `GET /healthz` — Liveness probe (always 200)
- `GET /readyz` — Readiness probe (checks DB)

### Dashboard
- `GET /dashboard/login` — Login page
- `POST /dashboard/login` — Login submit
- `GET /dashboard/leads` — Leads list
- `GET /dashboard/leads/{id}` — Lead detail
- `GET /dashboard/team` — Team management
- `GET /dashboard/stats` — Analytics
- `GET /dashboard/settings` — Dealer settings

## Design System

**Read `docs/04-FRONTEND.md` before writing any HTML or CSS.**

Key values:
- Background: `#0a0a0f`
- Surface: `#12121a`
- Border: `rgba(255,255,255,0.06)`
- Primary text: `#e8e8ed`
- Accent: `#6366f1` (indigo)
- Success/Warning/Error: `#22c55e` / `#eab308` / `#ef4444`
- Font: Inter
- Border radius: 6px-8px

## What NOT to Do

- Don't call Twilio directly — always use `tools/send_sms.py`
- Don't modify `app/engine/lifecycle.py` — it's tested and stable
- Don't add new database tables — use existing models
- Don't use React/Vue/Next.js — Jinja2 + HTMX is enough
- Don't add Alembic, Redis, Celery, or any new infrastructure
- Don't set `OUTBOUND_ENABLED=true` until Twilio is tested
- Don't store PII at INFO log level
- Don't hardcode secrets — use env vars

## When Extending

1. **New intake channel:** Add a new adapter in `app/adapters/intake/`
2. **New vehicle source:** Add a new adapter in `app/adapters/inventory/`
3. **New CRM output:** Add a new adapter in `app/adapters/organization/`
4. **New dashboard page:** Add route in `app/dashboard/__init__.py`, template in `app/dashboard/templates/`
5. **New background job:** Add to `app/scheduler.py`'s `register_jobs()` function

## Documentation

- `docs/00-OVERVIEW.md` — Project overview
- `docs/01-ARCHITECTURE.md` — File structure, DB schema, API design
- `docs/02-PIPELINE.md` — Core business logic flow
- `docs/03-BACKEND.md` — Implementation patterns with code examples
- `docs/04-FRONTEND.md` — UI spec + design system
- `docs/05-DEPLOYMENT.md` — How to ship it
- `docs/06-SKILLS.md` — Specialized knowledge (compliance, testing, pitfalls)
- `docs/07-TASKS.md` — Ordered implementation tasks with verify steps
