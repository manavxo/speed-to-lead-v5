# Architecture

## File Structure

```
Speed to Lead v4/
├── app/
│   ├── main.py                    # FastAPI app, webhook endpoints, lifespan
│   ├── config.py                  # Settings (env) + DealerConfig (per-dealer YAML)
│   ├── db.py                      # Database connection (get_session_factory, init_db)
│   ├── scheduler.py               # APScheduler jobs (escalation, followups, inventory)
│   ├── models/
│   │   └── __init__.py            # All SQLModel tables (Lead, Vehicle, Message, etc.)
│   ├── engine/
│   │   ├── lifecycle.py           # State machine (transition validation + LeadEvent)
│   │   ├── router.py              # Round-robin assignment + claim/pass handling
│   │   ├── conversation.py        # AI orchestration (OpenRouter tool-calling loop)
│   │   └── escalation.py          # Timeout handler (reassign on SLA breach)
│   ├── adapters/
│   │   ├── intake/
│   │   │   ├── __init__.py        # NormalizedLead model + IntakeAdapter base class
│   │   │   ├── webform.py         # Web form → NormalizedLead
│   │   │   ├── twilio_sms.py      # Inbound SMS → NormalizedLead
│   │   │   └── email_lead.py      # Parsed email → NormalizedLead
│   │   ├── inventory/
│   │   │   ├── base.py            # InventoryAdapter base class
│   │   │   ├── feed.py            # CSV/TSV/XML feed parser
│   │   │   ├── mapping.py         # Column mapping logic
│   │   │   └── discovery.py       # Auto-detect inventory platform
│   │   └── organization/
│   │       ├── native.py          # Our dashboard IS the system of record
│   │       └── webhook.py         # Push LeadEvents to external webhook
│   ├── dashboard/
│   │   ├── __init__.py            # Dashboard routes (leads, lead detail)
│   │   └── templates/
│   │       ├── base.html          # Layout: sidebar, topbar, CSS custom properties
│   │       ├── login.html         # Login page
│   │       ├── leads.html         # Lead pipeline overview
│   │       ├── lead_detail.html   # Lead detail + conversation timeline
│   │       ├── team.html          # Sales team management
│   │       ├── settings.html      # Dealer settings
│   │       └── stats.html         # Stats & reporting
│   └── api/                       # (planned) REST API endpoints
├── tools/
│   ├── route_lead.py              # Core ingest: persist → auto-reply → assign
│   ├── send_sms.py                # SMS/WhatsApp chokepoint (compliance + OUTBOUND gate)
│   ├── check_inventory.py         # Vehicle search against DB
│   └── book_appointment.py        # Appointment creation
├── dealers/
│   ├── _schema.md                 # Human docs for the YAML config
│   └── example-dealer.yaml        # Filled example
├── workflows/
│   └── qualify_and_book.md        # AI conversation SOP (injected into system prompt)
├── tests/
│   └── ...                        # pytest suite (126 passing)
├── docs/                          # This documentation
├── Dockerfile
├── start.sh
├── render.yaml
├── .env.example
└── README.md
```

---

## Three-Axis Adapter Model

Every dealership varies in three ways. The adapter model isolates that variation:

**Axis 1 — Inventory** (how they list cars)
- Source: CSV feed, website scrape, DMS API, schema.org, manual upload
- Adapters normalize to the canonical `Vehicle` table
- Config: `dealers/<slug>.yaml` → `inventory.source`, `inventory.url`

**Axis 2 — Organization** (where they track leads)
- Sink: Native dashboard, CRM sync, Google Sheet, webhook, email digest
- Adapters consume `LeadEvent` rows and push to the dealer's system
- Config: `dealers/<slug>.yaml` → `lead_org.mode`, `lead_org.target`

**Axis 3 — Intake** (where leads come from)
- Source: Web form, SMS, email, Facebook Messenger, phone
- Adapters normalize to a `NormalizedLead` → persisted as `Lead`
- Config: `dealers/<slug>.yaml` → `channels.*`

**The core engine only ever sees canonical types** (Lead, Vehicle, LeadEvent). Adding a new source or sink = one adapter file + zero core changes.

---

## Database Schema

All tables defined in `app/models/__init__.py` using SQLModel.

### Dealer
```sql
CREATE TABLE dealer (
    id              INTEGER PRIMARY KEY,
    slug            VARCHAR UNIQUE NOT NULL,     -- kebab-case tenant key
    name            VARCHAR NOT NULL,
    timezone        VARCHAR DEFAULT 'America/Vancouver',
    sms_number      VARCHAR,                     -- indexed, tenant resolution
    whatsapp_sender VARCHAR,                     -- indexed, tenant resolution
    web_form_token  VARCHAR UNIQUE,              -- indexed, tenant resolution
    config          JSON,                        -- full DealerConfig dict
    round_robin_pointer INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT now()
);
```

### Vehicle
```sql
CREATE TABLE vehicle (
    id        INTEGER PRIMARY KEY,
    dealer_id INTEGER REFERENCES dealer(id),
    stock_no  VARCHAR,        -- indexed
    vin       VARCHAR,        -- indexed
    year      INTEGER,
    make      VARCHAR,
    model     VARCHAR,
    trim      VARCHAR,
    body      VARCHAR,
    mileage   INTEGER,
    price     FLOAT,
    status    VARCHAR DEFAULT 'available',  -- available | sold | removed
    url       VARCHAR,
    photos    JSON DEFAULT '[]',
    raw       JSON DEFAULT '{}',            -- original source payload
    synced_at TIMESTAMP DEFAULT now()
);
```

### Lead
```sql
CREATE TABLE lead (
    id           INTEGER PRIMARY KEY,
    dealer_id    INTEGER REFERENCES dealer(id),
    source       VARCHAR NOT NULL,           -- sms | webform | email | ...
    name         VARCHAR,
    phone        VARCHAR,                    -- indexed
    email        VARCHAR,
    vehicle_ref  VARCHAR,                    -- stock#, VIN, URL, or "2019 Honda Civic"
    vehicle_id   INTEGER REFERENCES vehicle(id),
    state        VARCHAR DEFAULT 'NEW',      -- indexed, enum LeadState
    assigned_rep VARCHAR,
    consent      BOOLEAN DEFAULT FALSE,
    created_at   TIMESTAMP DEFAULT now(),
    updated_at   TIMESTAMP DEFAULT now()
);
```

### LeadEvent
```sql
CREATE TABLE lead_event (
    id         INTEGER PRIMARY KEY,
    lead_id    INTEGER REFERENCES lead(id),     -- indexed
    dealer_id  INTEGER REFERENCES dealer(id),   -- indexed
    type       VARCHAR NOT NULL,                -- state_change | message | appointment
    payload    JSON DEFAULT '{}',
    synced     BOOLEAN DEFAULT FALSE,           -- indexed, flushed to org sink?
    created_at TIMESTAMP DEFAULT now()
);
```

### Message
```sql
CREATE TABLE message (
    id              INTEGER PRIMARY KEY,
    lead_id         INTEGER REFERENCES lead(id),  -- indexed
    direction       VARCHAR NOT NULL,             -- inbound | outbound
    channel         VARCHAR NOT NULL,             -- sms | whatsapp | email | ...
    body            VARCHAR NOT NULL,
    provider_sid    VARCHAR UNIQUE,               -- Twilio SID for idempotency
    delivery_status VARCHAR,                      -- queued/sent/delivered/failed
    error_code      VARCHAR,
    ai_generated    BOOLEAN DEFAULT FALSE,
    approved_by     VARCHAR,
    created_at      TIMESTAMP DEFAULT now()
);
```

### Appointment
```sql
CREATE TABLE appointment (
    id            INTEGER PRIMARY KEY,
    lead_id       INTEGER REFERENCES lead(id),    -- indexed
    dealer_id     INTEGER REFERENCES dealer(id),  -- indexed
    scheduled_for TIMESTAMP NOT NULL,
    status        VARCHAR DEFAULT 'set',          -- set | confirmed | showed | no_show | cancelled
    created_at    TIMESTAMP DEFAULT now()
);
```

### ConsentLog
```sql
CREATE TABLE consent_log (
    id         INTEGER PRIMARY KEY,
    dealer_id  INTEGER REFERENCES dealer(id),  -- indexed
    lead_id    INTEGER REFERENCES lead(id),
    phone      VARCHAR NOT NULL,               -- indexed
    action     VARCHAR NOT NULL,               -- granted | opted_out
    text       VARCHAR,                        -- the consent/opt-out message text
    created_at TIMESTAMP DEFAULT now()
);
```

---

## API Endpoints

### Webhooks (public, no auth)

| Method | Path                       | Purpose                                  |
| ------ | -------------------------- | ---------------------------------------- |
| POST   | `/webhook/form/{token}`    | Web form intake (JSON body)              |
| POST   | `/webhook/twilio/sms`      | Inbound SMS + STOP handling              |
| POST   | `/webhook/twilio/whatsapp` | Rep claim/pass responses                 |
| POST   | `/webhook/twilio/voice`    | Missed call → text-back                  |
| POST   | `/webhook/twilio/status`   | Delivery status callback                 |
| POST   | `/webhook/messenger`       | Facebook Messenger (stub)                |
| GET    | `/webhook/messenger`       | Facebook webhook verification            |

### Health

| Method | Path       | Purpose                           |
| ------ | ---------- | --------------------------------- |
| GET    | `/healthz` | Liveness (always 200)             |
| GET    | `/readyz`  | Readiness (checks DB connection)  |

### Dashboard (session auth, planned)

| Method | Path                   | Purpose                           |
| ------ | ---------------------- | --------------------------------- |
| GET    | `/dashboard`           | Redirect to `/dashboard/leads`    |
| GET    | `/dashboard/leads`     | Lead pipeline overview            |
| GET    | `/dashboard/leads/:id` | Lead detail + conversation        |
| GET    | `/dashboard/team`      | Sales team management (planned)   |
| GET    | `/dashboard/settings`  | Dealer settings (planned)         |
| GET    | `/dashboard/stats`     | Stats & reporting (planned)       |

---

## Key Design Decisions

1. **Single send chokepoint.** All SMS/WhatsApp goes through `tools/send_sms.py`. This is where compliance lives. Never send a message outside this module.

2. **State machine is immutable.** `app/engine/lifecycle.py` defines the allowed transitions. Every state change creates a LeadEvent. The transition map is the single source of truth.

3. **Tenant resolution on every webhook.** Each inbound webhook resolves the dealer by matching the destination number/token against indexed columns on the Dealer table. Fallback scans JSON config for legacy rows.

4. **Dry-run mode by default.** When `OUTBOUND_ENABLED=false`, `send_sms.py` returns synthetic DRYRUN SIDs and persists Message rows. The full pipeline runs without Twilio creds.

5. **Idempotent webhooks.** Every inbound webhook checks for an existing Message with the same `provider_sid`. Duplicate deliveries are silently dropped.

6. **Hybrid AI autonomy.** Business hours → AI drafts, rep approves. After hours → AI sends autonomously. Controlled by `is_business_hours()` in `app/engine/conversation.py`.
