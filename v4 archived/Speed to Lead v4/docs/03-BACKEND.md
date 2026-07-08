# Backend — Implementation Patterns

## Key Function Signatures

### lifecycle.transition()

Moves a Lead from one state to another. Validates the transition is legal. Creates a LeadEvent.

```python
# app/engine/lifecycle.py

def can_transition(current: LeadState, target: LeadState) -> bool:
    """Check if a state transition is allowed."""
    return target in TRANSITIONS.get(current, set())

def transition(
    session: Session,
    lead: Lead,
    target: LeadState,
    *,
    reason: str | None = None,
    meta: dict | None = None,
) -> LeadEvent:
    """Move a Lead to `target`, validating the edge.

    Args:
        session: SQLAlchemy session.
        lead: The lead to transition.
        target: The desired new state.
        reason: Human-readable reason for the transition.
        meta: Extra data to store in the event payload.

    Returns:
        The created LeadEvent.

    Raises:
        ValueError: If the transition is illegal.
    """
```

**Usage:**
```python
from app.engine.lifecycle import transition
transition(session, lead, LeadState.AUTO_REPLIED, reason="auto_reply",
           meta={"reply_text": auto_text})
```

---

### router.assign_lead()

Picks the next active rep via round-robin, sends WhatsApp claim ping, transitions to ASSIGNED.

```python
# app/engine/router.py

def next_rep(dealer: Dealer, sales_team: list[dict]) -> dict | None:
    """Return the next active rep in rotation and advance the dealer's pointer.

    Returns the rep dict {name, whatsapp, active} or None if no active reps.
    """

def assign_lead(
    session: Session,
    lead: Lead,
    dealer: Dealer,
    sales_team: list[dict],
    *,
    fake_twilio=None,
    whatsapp_sender: str | None = None,
) -> Lead | None:
    """Assign lead to the next rep, send WhatsApp claim ping, transition to ASSIGNED.

    If no active reps, returns None and lead stays in AUTO_REPLIED (AI-only path).
    """

def handle_claim(session: Session, lead: Lead, rep_name: str) -> Lead:
    """Handle rep's claim (reply '1'). Transitions ASSIGNED -> CLAIMED."""

def handle_pass(
    session: Session,
    lead: Lead,
    dealer: Dealer,
    sales_team: list[dict],
    rep_name: str,
    *,
    fake_twilio=None,
    whatsapp_sender: str | None = None,
) -> Lead | None:
    """Handle rep's pass (reply '2'). Reassigns to the next rep."""
```

---

### conversation.handle_turn()

Produce the next AI response for a lead. Loads the workflow SOP, calls OpenRouter with tool definitions, executes tool calls, returns the assistant text.

```python
# app/engine/conversation.py

def is_business_hours(dealer_config: dict, now: datetime | None = None) -> bool:
    """True if `now` falls inside the dealer's open hours (dealer timezone)."""

def build_system_prompt(dealer_config: dict, vehicle_context: str | None = None) -> str:
    """Assemble system prompt from dealer config + workflow SOP + vehicle context."""

def handle_turn(
    session: Session,
    lead,
    inbound_text: str,
    *,
    dealer_config: dict,
    vehicle=None,
    fake_llm=None,
    now: datetime | None = None,
) -> dict:
    """Produce the next assistant turn for a lead.

    Returns:
        {
            "mode": "send" | "draft",   # "draft" during business hours
            "text": "...",               # the reply text
            "is_business_hours": bool,
            "tools_used": ["check_inventory", "book_appointment"],
        }
    """
```

**AI tools registered:**
- `check_inventory` — search vehicles by query, max_price, body style
- `book_appointment` — book an appointment with date_time and notes

**Grounding rule:** The model may only state facts returned by tools. Never invents vehicles, prices, or availability.

---

### send_sms.send_sms()

The ONLY function that sends SMS. All compliance checks happen here.

```python
# tools/send_sms.py

def send_sms(
    session: Session,
    to: str,
    body: str,
    from_number: str,
    *,
    dealer_slug: str = "",
    dealer_config: dict | None = None,
    lead: Lead | None = None,
    fake_twilio=None,
    now: datetime | None = None,
) -> str | None:
    """Send a lead-facing SMS. Returns Twilio message SID, or None if suppressed.

    Enforces:
    1. Opt-out check — skip if recipient has opted out
    2. Quiet hours — skip if in quiet window (dealer timezone)
    3. OUTBOUND_ENABLED gate — when False, log DRYRUN SID instead of calling Twilio

    Returns:
        Twilio message SID (or DRYRUN_xxx), or None if suppressed.
    """

def send_whatsapp(
    to: str,
    *,
    body: str = "",
    template: str | None = None,
    variables: dict | None = None,
    from_number: str = "",
    lead: Lead | None = None,
    session: Session | None = None,
    role: str = "REP",
    recipient_name: str | None = None,
    fake_twilio=None,
) -> str | None:
    """Send a rep-facing WhatsApp message.

    Business-initiated pings must use an approved template (Twilio requirement).
    When OUTBOUND_ENABLED is false, returns DRYRUN SID and logs.
    """
```

**Never send messages outside this module.** This is the single chokepoint for compliance.

---

### route_lead.ingest_lead()

The full intake pipeline: deduplicate → persist → resolve vehicle → auto-reply → assign.

```python
# tools/route_lead.py

def ingest_lead(
    session: Session,
    dealer,
    lead_data: NormalizedLead,
    *,
    fake_twilio=None,
    now: datetime | None = None,
) -> Lead:
    """Persist + start the speed-to-lead flow for a new lead.

    Steps:
    1. Deduplicate (same phone + dealer within 24h → return existing)
    2. Resolve vehicle_ref against Vehicle table
    3. INSERT Lead (state=NEW)
    4. Log consent if provided (ConsentLog)
    5. Transition NEW → AUTO_REPLIED + send auto-reply SMS
    6. Assign round-robin + WhatsApp claim ping (ASSIGNED)

    Returns the persisted Lead.
    """
```

---

## FastAPI + APScheduler Lifespan Pattern

Currently the scheduler runs as a separate process (`python -m app.scheduler`). The plan is to merge it into the FastAPI lifespan so there's one process to deploy.

**Current pattern (separate process):**
```python
# app/scheduler.py — runs as: python -m app.scheduler
def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler()
    # ... add jobs ...
    scheduler.add_job(_run_escalation_sweep, 'interval', minutes=1, id='escalation-sweep')
    scheduler.add_job(_run_inventory_sync, 'interval', minutes=180, id='inventory-sync')
    scheduler.add_job(_run_stuck_lead_sweep, 'interval', minutes=5, id='stuck-lead-sweep')
    scheduler.add_job(_run_org_sink_flush, 'interval', minutes=15, id='org-sink-flush')
    return scheduler
```

**Target pattern (merged into lifespan):**
```python
# app/main.py — merged into FastAPI lifespan
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Start DB + scheduler on startup, shut down cleanly."""
    init_db()

    # Add scheduled jobs
    from app.scheduler import _run_escalation_sweep, _run_inventory_sync, \
        _run_stuck_lead_sweep, _run_org_sink_flush

    scheduler.add_job(_run_escalation_sweep, 'interval', minutes=1, id='escalation-sweep')
    scheduler.add_job(_run_inventory_sync, 'interval', minutes=180, id='inventory-sync')
    scheduler.add_job(_run_stuck_lead_sweep, 'interval', minutes=5, id='stuck-lead-sweep')
    scheduler.add_job(_run_org_sink_flush, 'interval', minutes=15, id='org-sink-flush')

    scheduler.start()
    logger.info("Scheduler started inside FastAPI lifespan")

    yield

    scheduler.shutdown(wait=True)
    logger.info("Scheduler shut down")

app = FastAPI(title="Speed-to-Lead", version="0.2.0", lifespan=lifespan)
```

**Key change:** Use `AsyncIOScheduler` instead of `BlockingScheduler`. The job functions themselves stay the same (they create their own DB sessions).

**Start command change:** Remove `python -m app.scheduler` from `start.sh`. The scheduler now starts automatically with the web server.

---

## Database Access Pattern

Every route/tool creates its own session and closes it in a `finally` block:

```python
session = get_session_factory()()
try:
    # ... do work ...
    session.commit()
finally:
    session.close()
```

**Never pass sessions across module boundaries.** Each function that needs DB access creates its own session, or receives one as a parameter.

---

## Error Handling Pattern

Webhooks catch all exceptions and return safe responses (empty TwiML or error dict). They never raise to the caller:

```python
@app.post("/webhook/twilio/sms")
async def webhook_twilio_sms(request: Request) -> Response:
    session = _get_session()
    try:
        # ... process ...
    except Exception:
        logger.exception("webhook_twilio_sms error")
        return _empty_twiml()  # Always return valid TwiML
    finally:
        session.close()
```

---

## Tenant Resolution Pattern

Every webhook resolves the dealer by matching the destination:

```python
# By SMS number
dealer = _find_dealer_by_sms(session, to_number)

# By WhatsApp sender
dealer = _find_dealer_by_whatsapp(session, to_number)

# By web form token (URL path)
dealer = _find_dealer_by_token(session, token)
```

Each resolver tries the indexed column first, then falls back to scanning the JSON config for legacy rows.
