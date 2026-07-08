# Speed to Lead v4 — Overview

## What We're Building

A speed-to-lead response engine for small car dealerships in BC, Canada. The system:

- Captures leads from multiple channels (web forms, SMS, missed calls, email)
- Auto-replies via SMS in under 60 seconds, 24/7
- Routes leads to sales reps via WhatsApp (round-robin with claim/pass)
- Uses AI (OpenRouter) to qualify leads and book test drive appointments
- Escalates if reps don't claim within SLA windows
- Complies with CASL + PIPA BC (Canadian texting laws)
- Runs autonomous AI conversations after business hours

**Target customers:** Small used-car dealerships in British Columbia (2-10 salespeople).
**Revenue target:** $5-7k/month ($299-499/dealer).

---

## Tech Stack

| Layer              | Technology                       | Why                                    |
| ------------------ | -------------------------------- | -------------------------------------- |
| Web framework      | FastAPI (Python 3.12)            | Async, fast, great docs                |
| Database           | Postgres (prod) / SQLite (tests) | Render includes Postgres               |
| ORM                | SQLModel + SQLAlchemy            | Already wired from v3                  |
| Validation         | Pydantic v2                      | Type-safe configs and models           |
| SMS/WhatsApp       | Twilio SDK                       | Industry standard for texting          |
| AI                 | OpenRouter (OpenAI-compatible)   | Swap models with one config change     |
| Templates          | Jinja2 + HTMX                    | Interactivity without a JS framework   |
| Scheduler          | APScheduler                      | Background tasks (escalation, followup)|
| CSS                | Custom properties (dark theme)   | No build step, no Tailwind CDN         |
| Auth               | Simple session-based             | Username/password + cookie             |
| Deploy             | Render.com                       | Auto-deploy from GitHub, $7/mo         |

**What we're NOT using:** React, Vue, Next.js, Docker Compose, Redis, Celery, GraphQL, TypeScript, or any frontend build tooling.

---

## Cost

| Item                    | Cost          |
| ----------------------- | ------------- |
| Render Web Service      | $7/mo (hobby) |
| Render Postgres         | $7/mo         |
| Twilio SMS              | ~$0.0079/msg  |
| OpenRouter (AI)         | ~$0.01-0.05/conversation |
| Domain (speedtolead.ca) | ~$15/year     |

**Total to run:** ~$15-20/month. Each dealer at $299-499/month pays for infrastructure many times over.

---

## Constraints

1. **No real developers on staff.** Instructions must be clear enough for a non-developer to follow.
2. **Render hobby plan** for testing. Upgrade to standard ($25/mo) when going to production.
3. **OUTBOUND_ENABLED defaults to false.** No real SMS sends until Twilio creds are configured and verified.
4. **Canadian compliance is non-negotiable.** Every message must respect CASL and PIPA BC.
5. **Phone numbers provided later.** Twilio numbers will be provisioned during onboarding.
6. **Landing page is separate.** The marketing site is built independently.
7. **126 tests passing, 4 expected failures** (dashboard template content changes).

---

## Key Files (Start Here)

```
app/main.py                  — FastAPI app + webhook endpoints
app/engine/lifecycle.py      — Lead state machine
app/engine/router.py         — Round-robin assignment
app/engine/conversation.py   — AI orchestration
app/models/__init__.py       — All data models (Lead, Vehicle, Message, etc.)
app/config.py                — Settings + DealerConfig schema
app/dashboard/__init__.py    — Dashboard routes
tools/route_lead.py          — Lead ingestion pipeline
tools/send_sms.py            — SMS/WhatsApp chokepoint (compliance gates)
```
