# Testing Strategy — test every phase before deploy

Goal: catch problems with **demo data** long before a real lead (or a real dealer) is involved.
No live Twilio/Claude calls in the test suite — everything is mocked or runs against fixtures.

```bash
pip install -e ".[dev,inventory,docs]"
pytest -q                 # all tests
ruff check .              # lint
python tests/seed_demo.py # load a full demo dealer + inventory + sample leads into a local DB
```

## Test pyramid
- **Unit (most):** pure functions — config validation, lifecycle transitions, field mapping,
  adapter `parse()`/`fetch()` against fixtures, compliance checks.
- **Integration (some):** webhook → engine → tool, with Twilio/Claude/DB mocked or ephemeral.
- **End-to-end smoke (few):** one seeded demo dealer through the whole happy path.

## Mocking & environments
- **Twilio:** wrap the client so tests inject a fake that records calls instead of sending. Assert
  on `(to, body, from, template)` — never hit the network.
- **Claude:** inject a fake LLM that returns scripted tool-calls/messages. Conversation tests assert
  the engine's *handling* (tool execution, grounding, autonomy branch), not the model's wording.
- **Postgres:** spin up an ephemeral DB (Docker / testcontainers) or use SQLite for pure-logic
  tests. Each test gets a clean schema.
- **Clock:** inject a fake `now` so quiet-hours, business-hours, escalation timing, and the latency
  budget are deterministic.

## Demo data (in `tests/fixtures/`)
| Fixture | Exercises |
|---|---|
| `demo-dealer.yaml` | Config validation; tenant provisioning; multi-tenant resolution |
| `inventory_feed.csv` | Axis 1 rung 1 (Google Vehicle Ads / FB Catalog CSV) + field mapping |
| `inventory_jsonld.html` | Axis 1 rung 3 (schema.org JSON-LD extraction) + discovery scoring |
| `webform_payload.json` | Axis 3 webform intake → `NormalizedLead`; consent capture |
| `lead_email_cargurus.txt` | Axis 3 email-lead parsing (known template) |
| `twilio_sms_inbound.json` | Axis 3 SMS intake; `STOP`/`ARRET` opt-out path |
| `crm_expected.json` | Axis 2 `LeadEvent` → expected outbound CRM payload |

`tests/seed_demo.py` loads `demo-dealer.yaml` + `inventory_feed.csv` and creates a handful of leads
in known states so you can click through the dashboard and run the smoke test.

## What to test, phase by phase

### Phase 1 — Config & onboarding (drop-in)
- `demo-dealer.yaml` loads into a valid `DealerConfig`.
- Each invalid mutation is rejected with a clear error (missing `slug`, bad timezone, rep without
  `whatsapp`, unknown `inventory.source`, unknown `lead_org.mode`).
- `provision_dealer` runs discovery per axis and produces an onboarding summary + inventory preview.

### Phase 2 — Inventory (Axis 1) + grounding
- Each adapter fixture → expected `VehicleRecord`s (golden compare).
- `discovery.discover(url)` picks the right rung for each fixture; manual is the floor.
- `mapping.map_row` normalizes known specs; LLM-assisted mapping path is exercised with a mock.
- `sync_inventory` upserts, marks sold/removed, and on a simulated fetch error keeps last-known-good
  and sets `stale=True`.
- **Grounding:** `check_inventory.resolve_vehicle` returns None for an unknown ref; the conversation
  layer must refuse/redirect rather than invent a car (assert with the fake LLM).

### Phase 3 — Intake (Axis 3)
- Each intake adapter: raw fixture payload → expected `NormalizedLead` (name/phone/vehicle_ref/consent).
- Tenant resolution: a payload routes to the correct dealer by destination
  (`web_form_token`/`sms_number`/`facebook_page_id`).

### Phase 4 — Engine core
- **Lifecycle:** every legal transition succeeds; every illegal one raises. (See `test_lifecycle.py`.)
- **Round-robin:** N leads across M active reps rotate evenly; inactive reps skipped; empty team →
  AI-only path.
- **Escalation:** unclaimed within `claim_timeout_min` → `ESCALATED` → reassign → notify manager
  (fake clock advances the timer).
- **Autonomy switch:** `is_business_hours` true → draft for approval; false → autonomous send
  (test across the dealer's hours + timezone, incl. weekends).
- **Latency budget:** form webhook → outbound auto-reply requested within budget (fake clock).

### Phase 5 — Organization (Axis 2)
- `native` is a no-op (events stay in DB, marked synced).
- `crm_sync`/`sheet`/`webhook` map a `LeadEvent` → expected outbound payload (`crm_expected.json`).
- Sink failure → event left unsynced and retried; assert no data loss.

### Phase 6 — Compliance (Canada/BC) — gate before any real send
- Inbound `STOP`/`STOPALL`/`UNSUBSCRIBE`/`ARRET` → lead `OPTED_OUT`, `ConsentLog` written, all
  subsequent `send_sms` calls suppressed.
- Quiet-hours: outbound during the window is deferred, not sent.
- Consent: a webform without consent does not trigger outbound texting.

### Pre-deploy smoke (the gate in `.clinerules`)
Seed the demo dealer, then: submit `webform_payload.json` → assert instant auto-reply requested →
simulate a rep WhatsApp `1` (claim) → drive a scripted conversation → `book_appointment` →
lead `APPT_SET` and a `LeadEvent` queued to the org sink. Then send `STOP` and assert silence.
