# Speed to Lead v4 — Project Plan

> **Goal:** Ship a sellable AI sales assistant for car dealerships in BC.
> **Revenue target:** $5-7k/mo. **Timeline:** Build in phases, ship each one.
> **Philosophy:** Cut ruthlessly. Every file earns its place.

---

## 1. WHAT WE KEEP FROM v3

These are the battle-tested pieces — 122 tests pass, the pipeline works end-to-end. We copy them over and trim as needed.

### Core Pipeline (the money path)
- `app/engine/lifecycle.py` — The state machine. Every lead walks through this. Perfect as-is.
- `app/engine/router.py` — Round-robin assignment to salespeople. Works.
- `app/engine/conversation.py` — AI orchestration (Claude/OpenRouter). Needs simplification but the bones are right.
- `app/engine/escalation.py` — Timeout handler. If nobody responds in X minutes, escalate.

### Tools (the actions the AI can take)
- `tools/route_lead.py` — Ingest pipeline: takes webform data, validates, creates lead, starts flow.
- `tools/send_sms.py` — Messaging chokepoint. All SMS goes through here. Has compliance gates (time-of-day, opt-out). Do NOT rewrite this.
- `tools/check_inventory.py` — Vehicle search. We'll connect it to a real feed later.
- `tools/book_appointment.py` — Creates appointment slots. Solid.

### Data Layer
- `app/models/__init__.py` — Data models (Lead, Conversation, Appointment, Salesperson, etc.). Right tables, right relationships.
- `app/db.py` — Database layer. Simple, works with Postgres.
- `app/config.py` — Settings + DealerConfig schema. Environment variables and per-dealer config.

### Testing
- `tests/conftest.py` — Test infrastructure. Fixtures, mocks, helpers. This is why you have 122 tests.

### Deployment
- `Dockerfile` — Container definition. Still works.
- `start.sh` — Boot script. Keep it.
- `render.yaml` — Render.com config. We'll tweak but keep the structure.

---

## 2. WHAT WE CUT (and why)

### Adapter Stubs — DELETE ALL 10
These are empty "we'll build this someday" files. They do nothing and confuse anyone reading the code.
- `adapters/dms.py` — DMS integration (never built)
- `adapters/structured_data.py` — CSV import (never built)
- `adapters/website_scrape.py` — Website scraping (never built)
- `adapters/manual_upload.py` — Manual entry (never built)
- `adapters/phone.py` — Phone call handling (never built)
- `adapters/messenger.py` — Facebook Messenger (never built)
- + 4 more adapter stubs — all dead code

### Unused Workflow SOPs — DELETE 7 of 8
Only `sops/qualify_and_book.md` is actually loaded. The rest are dead weight.
- Delete: `sops/follow_up.md`, `sops/objection_handling.md`, `sops/price_negotiation.md`, `sops/service_booking.md`, `sops/trade_in.md`, `sops/test_drive.md`, `sops/financing.md`
- Keep: `sops/qualify_and_book.md` (this is the one that runs)

### Alembic — DELETE
Alembic is a database migration tool. In v3, you never actually ran migrations — `init_db` does `create_all` (which just creates tables from scratch). Alembic adds complexity for zero benefit at your stage. When you need migrations later, you'll add it back. Not now.

### Separate Scheduler Process — DELETE
v3 runs APScheduler as a separate process (another thing to deploy, monitor, and debug). v4 merges this into FastAPI using `BackgroundTasks` or a simple `asyncio` loop inside the same server.

### Other Cuts
- Any `.env.example` files with 50 unused variables
- `docker-compose.yml` if it exists (Render doesn't use it; overcomplicates local dev)
- Dead imports, commented-out code, TODO comments older than 2 months

---

## 3. WHAT WE BUILD NEW

### A. Lexus Landing Page
A single-page marketing site that makes dealers say "I want this." Premium, attention-grabbing, mobile-first.
- Hero section with a bold value prop
- "How it works" — 3 steps, simple
- Pricing section
- Demo CTA (sends to your WhatsApp or books a call)
- Lives at: `speedtolead.ca` or a subdomain
- Tech: Static HTML + Tailwind CSS. No framework needed. One file is fine.

### B. Toyota Dashboard (upgrade)
The existing dashboard is functional but rough. We upgrade it to something you'd be proud to show a dealer.
- Lead list with filters (status, date, source)
- Conversation viewer (read the SMS thread)
- Salesperson management (add/remove, set round-robin weights)
- Settings panel (dealer config, business hours, AI tone)
- Basic stats (leads today, response time, conversion rate)
- Auth: Simple password login (not enterprise SSO — you're selling to small dealers)
- Tech: FastAPI serves Jinja2 templates + HTMX for interactivity. No React/Vue build step.

### C. Deployment Automation
One command to deploy. No manual steps.
- `render.yaml` with all services defined
- `start.sh` that runs migrations + starts the server
- Health check endpoint so Render knows it's alive

### D. Real Inventory Feed (Phase 3+)
Connect `check_inventory.py` to an actual vehicle data source. Options:
- CSV upload from dealer (simplest, works for v1)
- Dealer's website scrape (medium effort)
- DMS API integration (complex, do later)

---

## 4. SIMPLIFIED TECH STACK

| Layer | v3 | v4 | Why |
|-------|----|----|-----|
| **Web framework** | FastAPI | FastAPI | Keep. It's fast, async, has good docs. |
| **Database** | Postgres | Postgres | Keep. Render gives you a free Postgres instance. |
| **ORM** | SQLAlchemy | SQLAlchemy | Keep. Already wired. |
| **Migrations** | Alembic (unused) | DELETE | Use `create_all` + manual SQL when needed. |
| **Scheduler** | APScheduler (separate process) | In-process (FastAPI lifespan) | One fewer thing to deploy. |
| **AI** | Claude via OpenRouter | Claude via OpenRouter | Keep. Best model for conversational AI. |
| **SMS** | Twilio | Twilio | Keep. Industry standard. |
| **Templates** | Jinja2 (basic) | Jinja2 + HTMX | HTMX adds interactivity without a JS framework. |
| **CSS** | Whatever v3 had | Tailwind CSS (CDN) | One CDN link, no build step. Looks great. |
| **Auth** | None | Simple session auth | Username/password + cookie. No OAuth. |
| **Deploy** | Render | Render | Keep. Free tier works for demos. |
| **Tests** | pytest (122 passing) | pytest | Keep all existing tests. Add more. |

**What we're NOT adding:** React, Next.js, Docker Compose, Redis, Celery, GraphQL, TypeScript, or any build tooling. Every addition is a future debugging session.

---

## 5. BUILD ORDER

Ship each phase independently. Each one is a usable milestone.

### Phase 1: Clean Slate (Day 1)
**Deliverable:** v4 repo with v3's working code, minus the dead weight.
1. Create v4 repo
2. Copy over the "KEEP" files listed in Section 1
3. Delete everything listed in Section 2
4. Run tests — should still pass (fix any import errors from deleted files)
5. Verify `uvicorn` starts and the API responds

### Phase 2: Backend Polish (Day 2-3)
**Deliverable:** Same pipeline, cleaner code, scheduler merged.
1. Merge APScheduler into FastAPI lifespan (runs inside the server)
2. Simplify `conversation.py` — remove dead branches, tighten the prompt
3. Add simple auth: `/login` page, session cookie, password from env var
4. Add health check endpoint (`GET /healthz` returns `{"status": "ok"}`)
5. Add basic dashboard API endpoints:
   - `GET /api/leads` — list leads with filters
   - `GET /api/leads/{id}` — lead detail + conversation
   - `GET /api/stats` — today's numbers
6. Run tests, fix anything broken

### Phase 3: Toyota Dashboard (Day 4-7)
**Deliverable:** A dashboard you'd show a dealer.
1. Set up Jinja2 templates with a base layout (dark mode, Inter font)
2. Lead list page — table with filters, status badges, click to view
3. Lead detail page — conversation thread, lead info, action buttons
4. Salesperson management — add/remove, toggle active, set weights
5. Settings page — dealer name, business hours, AI personality, Twilio number
6. Stats page — leads/week chart, response time, conversion funnel
7. Mobile responsive — test on phone, fix layout issues
8. All HTMX for interactivity (no page reloads for actions)

### Phase 4: Lexus Landing Page (Day 8-9)
**Deliverable:** A marketing page that sells.
1. Design the page (see Section 6 for style guide)
2. Build it as static HTML + Tailwind CSS
3. Add lead capture form (submits to your own API — dogfooding)
4. Add "Book a Demo" button (link to Calendly or WhatsApp)
5. Mobile responsive
6. Deploy to a static host or serve from FastAPI

### Phase 5: Inventory & Outbound (Day 10-14)
**Deliverable:** Real inventory matching + follow-up messages.
1. CSV upload for vehicle inventory (dealer uploads a spreadsheet)
2. `check_inventory.py` reads from the uploaded data
3. Enable outbound follow-up: if lead hasn't responded in 2 hours, send a nudge
4. Draft approval flow: AI writes a message, salesperson approves before send (optional toggle)
5. Test the full loop: lead comes in → qualify → match inventory → text conversation → book appointment

### Phase 6: Deploy & Sell (Day 15+)
**Deliverable:** Live on the internet, ready for demos.
1. Finalize `render.yaml` with all services
2. Deploy to Render (web service + Postgres)
3. Point domain to Render
4. Test full flow on live environment
5. Record a demo video
6. Start pitching dealers in BC

---

## 6. DESIGN APPROACH

### Lexus Landing Page — "I want this"

Inspired by Stripe's marketing site. Premium, confident, clean.

**Style:**
- Background: White (#FFFFFF) with subtle blue-tinted shadows
- Headings: Deep navy (#0A1628), heavy weight, Inter or similar sans-serif
- Body text: Dark gray (#374151), light weight, generous line height
- Accent: Electric blue (#2563EB) for buttons and highlights
- Cards: White with soft blue shadows (`box-shadow: 0 4px 24px rgba(37, 99, 235, 0.08)`)
- Animations: Subtle fade-ins on scroll, nothing flashy

**Layout:**
1. **Hero:** Big headline ("Never miss a lead again"), subtitle explaining the product, CTA button
2. **Problem:** "Dealers lose 50% of leads because they respond too slow" — with a stat
3. **How it works:** 3 steps with icons (Lead comes in → AI responds in 30 seconds → Appointment booked)
4. **Features:** Grid of 4-6 cards (Fast response, Smart routing, Inventory matching, etc.)
5. **Pricing:** Simple — one price, what's included. No tiers confusion.
6. **CTA:** "Ready to stop losing leads?" + demo button
7. **Footer:** Contact info, links

**Mobile:** Stack everything vertically. Hero CTA stays sticky at bottom on mobile.

### Toyota Dashboard — "I can actually use this"

Inspired by Linear's app. Dark, clean, professional but not intimidating.

**Style:**
- Background: Near-black (#08090a)
- Surface: Dark gray (#111214) for cards and panels
- Borders: Semi-transparent white (`rgba(255,255,255,0.06)`)
- Text: White (#FFFFFF) for primary, gray (#8B8FA3) for secondary
- Accent: Indigo (#6366F1) for buttons, links, active states
- Font: Inter (14px body, 13px for dense UI)
- Status colors: Green (#22C55E) for new leads, Yellow (#EAB308) for waiting, Red (#EF4444) for stale

**Layout:**
- **Sidebar** (collapses on mobile): Leads, Salespeople, Settings, Stats
- **Lead list**: Compact rows with name, source, status badge, time since inquiry
- **Lead detail**: Split view — info on left, conversation on right (stacks on mobile)
- **Everything is HTMX**: Click a lead, the detail loads without page refresh. Change status, instant update.

**Mobile:** Sidebar becomes a bottom tab bar. Lead list is full-width. Detail page stacks vertically.

---

## 7. DEPLOYMENT STRATEGY

### Primary: Render.com (recommended)

**Why:** Free tier for demos, Postgres included, auto-deploys from GitHub, no DevOps.

**Services:**
1. **Web Service** — Your FastAPI app. Free tier = 750 hours/month (enough for demos).
2. **PostgreSQL** — Free tier = 90 days, then $7/mo. Fine for v1.
3. **Background Worker** (if needed) — For the scheduler. But we're merging it into the web process, so probably not needed.

**One-click setup:**
```
# render.yaml defines everything
services:
  - type: web
    name: speed-to-lead
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: ./start.sh
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: speed-to-lead-db
          property: connectionString
```

### Alternatives (if Render doesn't work out)

| Platform | Pros | Cons | Cost |
|----------|------|------|------|
| **Render** | Simple, Postgres included, auto-deploys | Free tier sleeps after 15min (slow cold start) | Free → $7/mo |
| **Railway** | Faster cold starts, good DX | No free tier anymore | ~$5-10/mo |
| **Fly.io** | Fast, edge deployment | More complex config | ~$5/mo |
| **DigitalOcean App Platform** | Predictable pricing | Less Python-native | $12/mo minimum |

**Decision:** Start with Render. If cold starts become an issue (dealors complain the app is slow), migrate to Railway. The app is a single FastAPI container — porting is straightforward.

### Domain
- Buy `speedtolead.ca` (or `.com`) — ~$15/year
- Point it to Render's DNS
- SSL is automatic on Render

---

## QUICK REFERENCE

**v4 file tree (target):**
```
speed-to-lead-v4/
├── app/
│   ├── main.py              # FastAPI app + lifespan (scheduler lives here)
│   ├── config.py             # Settings + DealerConfig
│   ├── db.py                 # Database connection
│   ├── models/
│   │   └── __init__.py       # All data models
│   ├── engine/
│   │   ├── lifecycle.py      # State machine
│   │   ├── router.py         # Round-robin assignment
│   │   ├── conversation.py   # AI orchestration
│   │   └── escalation.py     # Timeout handler
│   ├── api/
│   │   ├── leads.py          # Lead CRUD endpoints
│   │   ├── salespeople.py    # Salesperson management
│   │   ├── auth.py           # Login/session
│   │   └── stats.py          # Dashboard stats
│   └── templates/
│       ├── base.html          # Base template (dark theme)
│       ├── leads.html         # Lead list
│       ├── lead_detail.html   # Lead detail + conversation
│       ├── settings.html      # Dealer settings
│       └── login.html         # Login page
├── tools/
│   ├── route_lead.py         # Lead ingestion
│   ├── send_sms.py           # SMS chokepoint
│   ├── check_inventory.py    # Vehicle search
│   └── book_appointment.py   # Appointment creation
├── sops/
│   └── qualify_and_book.md   # The one SOP that matters
├── landing/
│   └── index.html            # Lexus landing page (static)
├── tests/
│   └── ...                   # All v3 tests + new ones
├── Dockerfile
├── start.sh
├── render.yaml
├── requirements.txt
└── README.md
```

---

*This plan is a living document. Update it as you build. Ship Phase 1 today.*
