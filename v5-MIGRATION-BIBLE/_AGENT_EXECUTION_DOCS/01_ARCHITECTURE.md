# Speed to Lead v5 — Architecture & Design Principles

> **For:** AI agents executing the refactoring
> **Read this FIRST** — before CODEBASE_AUDIT.md, REFACTORING_GUIDE.md, or EMAIL_STRATEGY.md
> **Supersedes:** PRD_HUMAN.md, PRD_AGENT.md, V5_SESSION_DECISIONS.md, V5_BUILD_PLAN.md (all stale, predate Jun 19 architecture revision)

---

## Development Approach: Test-Driven Development (TDD)

Every feature MUST follow TDD:
1. Write the failing test FIRST (RED)
2. Write the minimum code to pass (GREEN)
3. Refactor if needed (REFACTOR)
4. One commit per task
5. No fabricated test results — tests must run against real code

If a task says "build X," the first step is always writing the test for X.

---

## What This System Does

Speed to Lead v5 catches dealership leads in under 60 seconds, warms them up with AI, and hands sales reps the context they need to close or dismiss. It is built for small BC dealerships (1-3 reps).

## The Core Principle

**AI does ONE touch. The rep judges intent.**

- The AI warms up the lead (auto-reply SMS/WhatsApp, or one follow-up email)
- The AI qualifies the customer (budget, timeline, vehicle interest)
- The AI books appointments when the customer is ready
- Then the rep decides: pursue, dismiss, or reassign

The AI does NOT triage leads. It does NOT decide which leads are worth pursuing. It does NOT replace the salesperson's judgment. It makes sure nobody waits hours for a response.

**Speed to Lead v5 helps sales people. It doesn't replace them.**

---

## Channel Architecture

```
                        ┌─────────────────────┐
                        │   Speed to Lead v5   │
                        │     AI Engine        │
                        └──┬──────┬──────┬────┘
                           │      │      │
              ┌────────────┤      │      ├────────────┐
              │            │      │      │            │
         ┌────▼────┐  ┌────▼────┐ │ ┌────▼────┐  ┌───▼────┐
         │  SMS    │  │WhatsApp│ │ │  Email  │  │ Webform│
         │ (Twilio)│  │(Twilio)│ │ │ (IMAP)  │  │        │
         └────┬────┘  └────┬────┘ │ └────┬────┘  └───┬────┘
              │            │      │      │            │
              └────────────┴──────┼──────┴────────────┘
                                  │
               └───────────────────────────────────┘
                                  │
                        ┌─────────▼─────────┐
                        │  Telegram Bot API  │
                        │  (dealer-facing    │
                        │   ONLY — no other  │
                        │   dealer channel)  │
                        └─────────┬─────────┘
                                  │
                   ┌──────────────┴──────────────┐
                   │                             │
          ┌────────▼────────┐           ┌────────▼────────┐
          │  Rep Dashboard  │           │ Manager Dashboard│
          │  (my leads)     │           │  (all leads)     │
          └─────────────────┘           └──────────────────┘
```

### Channel Rules

| Channel | Direction | Purpose | AI Depth |
|---------|-----------|---------|----------|
| SMS (Twilio) | Customer ↔ AI | Full conversation | Auto-reply → qualify → book → handoff |
| WhatsApp (Twilio) | Customer ↔ AI | Full conversation | Auto-reply → qualify → book → handoff |
| Email (IMAP) | Listing site → System | Lead capture | Parse → route to SMS/WhatsApp (if phone) OR one follow-up email (if no phone) |
| Webform | Customer → System | Lead capture | Same as SMS/WhatsApp pipeline |
| Telegram | System → Dealer | Notifications | No AI — rep sees context, makes judgment |

**Twilio is the customer↔AI mediator ONLY.** Twilio handles SMS and WhatsApp conversations with customers. It is NEVER used for dealer-side notifications. All dealer communication goes through Telegram.

**Telegram is the ONLY dealer-facing channel.** No WhatsApp fallback for dealers. No SMS notifications to dealers. Telegram only.

### The Routing Fork (email leads)

```
Email lead arrives
      ↓
  Has phone number?
  ↓ YES              ↓ NO
  SMS/WhatsApp       ONE AI follow-up email
  full pipeline      → assign to rep (round-robin)
  (existing code)    → dashboard (no Telegram ping yet)
  auto-reply         → WAITING_FOR_EMAIL state
  AI qualifies
  books appointment
  → ENGAGED state
```

When an email-only customer replies to the follow-up:
- System catches the reply (IMAP polling)
- Matches sender email to existing lead
- Rep gets Telegram notification with 🔵 triage framing
- Rep handles manually via dashboard
- AI is NOT involved after the one follow-up

### Notification Framing

Same Telegram bot, different message templates:

**Hot lead (SMS/WhatsApp customer replied):**
```
🟢 HOT LEAD — John Smith
📱 +1 604-555-1234
🚗 2022 Honda Civic, $18,900
💬 "Can I come Saturday at 2pm?"
🤖 AI Status: READY TO BOOK

[View + Book Test Drive]
```

**Triage lead (email-only customer replied):**
```
🔵 EMAIL REPLY — Sarah Lee
(no phone available)
🚗 Inquired about 2022 Honda Civic on AutoTrader

💬 Their reply:
"I'm interested but want to know if financing
 is available first. My budget is around $15k."

⚡ Low intent — no phone, listing site lead

[View Thread + Reply]
```

🟢 = hot, close it. 🔵 = triage, judge if it's worth pursuing.

---

## Cascade Timing

| Channel | Rep timeout | Cascade | Manager notify |
|---------|------------|---------|----------------|
| SMS/WhatsApp | 5 min | 3 min | 15 min total |
| Email (no phone) | 24 hours | 12 hours | 48 hours total |

Why different: SMS/WhatsApp customers are waiting NOW. Email customers may not reply for days.

---

## Rep Assignment Model

**SMS/WhatsApp leads:** Rep assignment is DEFERRED to appointment booking. AI qualifies first, books appointment, THEN assigns rep. This is deliberate — don't waste rep time on unqualified leads.

**Email leads (no phone):** Rep is assigned IMMEDIATELY via round-robin. No Telegram ping yet — lead sits in dashboard. When customer replies, the assigned rep gets the Telegram notification.

Why different: Email leads are low-intent. The rep needs to see them in their queue and decide whether to invest time. No point waiting for AI qualification that may never happen (customer may never reply).

---

## Roles: Manager vs Rep

Two distinct roles with different access levels. Login via dealer name + PIN. No user table needed — reps are in dealer YAML config.

### Rep Profile
- Sees ONLY their assigned leads + unassigned leads
- Cannot see other reps' leads
- Can claim unassigned leads
- Can request lead transfer (goes to manager for approval)
- Can mark lead outcome (SOLD, LOST, NOT_INTERESTED)
- Sees their own stats (leads handled, appointments, close rate)
- Gets Telegram notifications for their leads only

### Manager Profile
- Sees ALL leads across the dealership
- Can filter by rep
- Can reassign leads (with reason + audit trail)
- Can approve/reject transfer requests
- Sees team performance (all reps, comparison)
- Can manage dealer settings
- Gets Telegram notifications for escalations (3 passes, stuck leads)
- Can add/edit/remove reps in the system

### Login Flow
```
Dealer: [premier-auto-group dropdown]
Rep: [Mike | Sarah | Manager]
PIN: [****]

Session stores: {dealer_slug, rep_name, role}
```

Manager PIN is separate from rep PINs. Manager sees a different dashboard with team-wide visibility.

---

## UI/UX Standard

The dashboard must look and feel like a premium software product. Not a generic admin panel — a real product that a business pays for.

### Principles
1. **Utility first.** Every pixel must serve a purpose. If it looks good but hurts usability, remove it.
2. **Modern, not trendy.** Clean typography, proper spacing, consistent colors. No gratuitous animations or gradients.
3. **Information density.** Reps need to see a lot at a glance. Don't waste space on decoration.
4. **Mobile-responsive.** Reps check leads on their phone. Desktop-first but mobile must work.
5. **Fast.** Page loads under 1 second. No heavy JS frameworks. Server-rendered HTML with minimal client-side.

### Design System
- Typography: Inter or system font stack. Clear hierarchy (h1/h2/h3/body/caption).
- Colors: Neutral base (white/gray-50), one accent color (dealer-configurable), semantic colors (green=warm, blue=cold, red=dead, yellow=attention).
- Spacing: 4px grid. Consistent padding/margins.
- Cards: Subtle shadows, rounded corners (8px). Lead cards show key info at a glance.
- Tables: Zebra striping, sticky headers, sortable columns.
- Buttons: Primary (filled), secondary (outlined), danger (red). Clear hover/active states.
- Forms: Labels above inputs, inline validation, loading states on submit.
- Dashboard: Clean sidebar nav, breadcrumbs, page title, action buttons top-right.

### What NOT to Do
- No Bootstrap-looking generic UI
- No excessive whitespace that pushes content below the fold
- No decorative elements that don't serve a function
- No slow client-side rendering (keep it server-rendered)
- No complex state management (keep it simple, Jinja2 templates + minimal JS)

## What to Keep (reuse as-is)

These are working and aligned with the new direction:

| Component | File | Why it works |
|-----------|------|-------------|
| Lead ingestion pipeline | `tools/route_lead.py` | Dedup → persist → auto-reply → AI follow-up → ENGAGED. Solid architecture. Add email branch. |
| Rep notification chokepoint | `tools/notify_rep.py` | Multi-backend dispatch. Add Telegram backend. |
| Round-robin assignment | `app/engine/router.py` | Works. No changes needed. |
| AI conversation engine | `app/engine/conversation.py` | OpenRouter via openai SDK. Good. Fix greeting_only bypass. |
| State machine | `app/engine/lifecycle.py` | DEFERRED assignment is correct. Keep. |
| Dashboard templates | `app/dashboard/templates/` | leads.html, lead_detail.html, settings.html. Good UI foundation. |
| Data models | `app/models/__init__.py` | 7 models, PostgreSQL. Add `pass_count` column. |
| Vehicle resolution | `tools/route_lead.py` | Matches inventory against DB. Good. |

## What to Replace

| Component | File | What's wrong | Replace with |
|-----------|------|-------------|-------------|
| Email parser | `app/adapters/intake/email_lead.py` | Generic regex, masking bug, consent=False | Site-specific parsers (AutoTrader, CarGurus, Kijiji) |
| WhatsApp test handler | `app/main.py` | ~180 lines of prod code in test handler | Route through existing SMS handler |
| Direct state assignment | `app/engine/conversation.py` | `lead.state = ASSIGNED` bypasses lifecycle | Use `transition()` function |
| Daily digest | `app/scheduler.py` | Undefined `dealer` variable, will crash | Fix variable reference |
| `notify_rep` default | `tools/notify_rep.py` | Defaults to `twilio_whatsapp` | Default to `telegram`, remove WhatsApp backend entirely. Telegram is the ONLY dealer channel. |

## What to Build New

| Component | File | Purpose |
|-----------|------|---------|
| Telegram transport | `app/transports/telegram.py` | Thin wrapper around Telegram Bot API |
| Email parsers | `app/adapters/intake/email_parsers/` | AutoTrader, CarGurus, Kijiji specific parsers |
| IMAP polling | `app/adapters/intake/email_ingest.py` | Poll inbox every 60s, parse new emails |
| Outbound email | `app/transports/email.py` | SendGrid/Mailgun for follow-up emails and rep replies |
| Routing fork | `tools/route_lead.py` | Branch: phone → SMS/WhatsApp, no phone → email follow-up |
| Email reply detection | `app/adapters/intake/email_ingest.py` | Match replies to existing leads, surface to dashboard |

---

## The Stale Documents

The following documents predate the Jun 19 architecture revision and contain conflicting information. They are HISTORICAL — do not use as source of truth:

| Document | Date | What's stale |
|----------|------|-------------|
| `PRD_HUMAN.md` | Pre-Jun 19 | Doesn't mention Telegram, email routing fork, or notification framing |
| `PRD_AGENT.md` | Pre-Jun 19 | Same — built for WhatsApp-only dealer notifications |
| `V5_SESSION_DECISIONS.md` | Jun 9 | Says "WhatsApp for dealer comms" (now Telegram), "email cut" (now core) |
| `V5_BUILD_PLAN.md` | Jun 9 | Builds WhatsApp as default dealer channel, doesn't know about Telegram |
| `V5_MIGRATION_LOG.md` | Jun 9 | Migration details may still be valid, but verify against current code |

The source of truth documents are:
1. `ARCHITECTURE.md` (this file) — vision, principles, channel architecture
2. `CODEBASE_AUDIT.md` — current state of the code
3. `REFACTORING_GUIDE.md` — execution instructions (9 phases)
4. `EMAIL_STRATEGY.md` — email channel detailed design

---

## Environment & Config

```
DATABASE_URL          — PostgreSQL on Render
OPENROUTER_API_KEY    — AI conversation engine
TWILIO_ACCOUNT_SID    — Customer SMS/WhatsApp
TWILIO_AUTH_TOKEN     — Customer SMS/WhatsApp
TELEGRAM_BOT_TOKEN    — Dealer notifications (to build)
SENDGRID_API_KEY      — Outbound email (to build)
EMAIL_INBOX_URL       — IMAP connection string (to build)
OUTBOUND_ENABLED      — false (DRYRUN by default)
PUBLIC_BASE_URL       — https://speed-to-lead-v5.onrender.com
```

---

*Last updated: 2026-06-19. Based on live GitHub codebase (origin/main, commit c4ca0ff).*