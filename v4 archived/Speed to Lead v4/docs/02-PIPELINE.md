# Lead Pipeline — The Core Lifecycle

Every lead follows this exact flow. Each step is a transition in the state machine.

```
NEW → AUTO_REPLIED → ASSIGNED → CLAIMED → ENGAGED → APPT_SET → SHOWED → SOLD
                                                        ↘ LOST
                  ↘ ESCALATED (reassignment)
                  ↘ OPTED_OUT (STOP keyword)
```

---

## Step 1: Intake

**What happens:** A lead arrives from any channel (web form, SMS, email, missed call).
**Which file:** `app/main.py` (webhook route) → `app/adapters/intake/*.py` (normalize)
**Data flow:**
```
Raw webhook payload
  → IntakeAdapter.parse(payload) → NormalizedLead(source, name, phone, email, vehicle_ref, consent)
```

**Example (web form):**
```python
# app/main.py — POST /webhook/form/{token}
payload = await request.json()
lead_data = WebFormAdapter().parse(payload)  # → NormalizedLead
lead = ingest_lead(session, dealer, lead_data)
```

**Example (inbound SMS):**
```python
# app/main.py — POST /webhook/twilio/sms
lead_data = TwilioSmsAdapter().parse(payload)  # → NormalizedLead
lead = ingest_lead(session, dealer, lead_data)
```

**Key files:**
- `app/main.py` — webhook routes (lines 205-393)
- `app/adapters/intake/__init__.py` — `NormalizedLead` model, `IntakeAdapter` base class
- `app/adapters/intake/webform.py` — Web form adapter
- `app/adapters/intake/twilio_sms.py` — SMS adapter

---

## Step 2: Normalize & Persist

**What happens:** `ingest_lead()` deduplicates, resolves vehicle reference, persists the Lead row.
**Which file:** `tools/route_lead.py` → `ingest_lead()`
**Data flow:**
```
NormalizedLead
  → Check for duplicate (same phone + dealer, last 24h)
  → resolve_vehicle() → match vehicle_ref against Vehicle table
  → INSERT Lead (state=NEW)
  → INSERT ConsentLog if consent=True
```

**The function:**
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
```

**Key rule:** If a lead with the same phone and dealer exists within 24 hours, return the existing lead (dedup). Don't create a duplicate.

---

## Step 3: Auto-Reply

**What happens:** The lead gets an instant SMS mentioning their name, the dealer, and the vehicle they asked about. State transitions NEW → AUTO_REPLIED.
**Which file:** `tools/route_lead.py` (orchestration) → `tools/send_sms.py` (send)
**Data flow:**
```
Lead (NEW)
  → Generate auto-reply text (with vehicle context if available)
  → lifecycle.transition(NEW → AUTO_REPLIED)
  → send_sms(to=lead.phone, body=auto_text, from_number=dealer.sms_number)
```

**The auto-reply text:**
```python
# tools/route_lead.py — _auto_reply_text()
if vehicle:
    return f"Hi! Thanks for your interest in the {vehicle.year} {vehicle.make} {vehicle.model}. ..."
return f"Hi! Thanks for reaching out to {dealer_name}. ..."
```

**Compliance gates inside send_sms:**
1. Opt-out check: skip if phone has opted out
2. Quiet hours: skip if current time is in quiet window (dealer timezone)
3. OUTBOUND_ENABLED: if false, log DRYRUN SID instead of calling Twilio

---

## Step 4: Assign (Round-Robin)

**What happens:** The next active sales rep gets a WhatsApp ping. State transitions AUTO_REPLIED → ASSIGNED.
**Which file:** `app/engine/router.py` → `assign_lead()`
**Data flow:**
```
Lead (AUTO_REPLIED)
  → next_rep() picks from active reps using Dealer.round_robin_pointer
  → lifecycle.transition(AUTO_REPLIED → ASSIGNED)
  → send_whatsapp(to=rep.whatsapp, body="New lead assigned... Reply 1 to claim, 2 to pass.")
  → Lead.assigned_rep = rep.name
```

**If no active reps:** Lead stays in AUTO_REPLIED. The AI handles it (after-hours or AI-only mode).

**The function:**
```python
# app/engine/router.py
def assign_lead(
    session: Session,
    lead: Lead,
    dealer: Dealer,
    sales_team: list[dict],
    *,
    fake_twilio=None,
    whatsapp_sender: str | None = None,
) -> Lead | None:
```

---

## Step 5: Claim

**What happens:** Rep replies "1" on WhatsApp to claim the lead, or "2" to pass. State transitions ASSIGNED → CLAIMED.
**Which file:** `app/main.py` (WhatsApp webhook) → `app/engine/router.py` → `handle_claim()` / `handle_pass()`
**Data flow:**
```
WhatsApp inbound ("1" or "2")
  → Find the rep by their WhatsApp number
  → Find the most recent ASSIGNED lead for that rep
  → If "1": handle_claim() → ASSIGNED → CLAIMED
  → If "2": handle_pass() → reassign to next rep (ASSIGNED again)
```

**SLA escalation:** If no claim within `claim_timeout_min` (default 5 min), `app/engine/escalation.py` reassigns to the next rep or notifies the manager. This runs as a scheduled job in `app/scheduler.py`.

---

## Step 6: Converse

**What happens:** The AI handles the SMS conversation — qualifies the lead, answers questions, drives toward booking.
**Which file:** `app/engine/conversation.py` → `handle_turn()`
**Data flow:**
```
Inbound SMS from lead
  → Find existing lead (not SOLD/LOST/OPTED_OUT)
  → AUTO_REPLIED → ENGAGED on first customer reply
  → handle_turn(session, lead, inbound_text, dealer_config, vehicle)
  → Returns {mode: "send"|"draft", text: "...", tools_used: [...]}
  → Business hours: mode="draft" (rep approves)
  → After hours: mode="send" (autonomous via TwiML)
```

**AI tools available:**
- `check_inventory` — search the dealer's vehicle database
- `book_appointment` — create an appointment slot

**The function:**
```python
# app/engine/conversation.py
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
    # Returns: {"mode": "send"|"draft", "text": "...", "is_business_hours": bool, "tools_used": [...]}
```

**Grounding rule:** The AI can only state facts returned by tools. It must never invent a car, price, or availability. Tools are the only path to side effects.

---

## Step 7: Book Appointment

**What happens:** When the AI qualifies the lead and they agree to a visit, it calls the `book_appointment` tool. State transitions ENGAGED → APPT_SET.
**Which file:** `tools/book_appointment.py` → `book_appointment()`
**Data flow:**
```
AI tool call: book_appointment(date_time="2025-01-15T14:00:00")
  → INSERT Appointment row
  → INSERT LeadEvent (type="appointment")
  → lifecycle.transition(ENGAGED → APPT_SET)
  → AI confirms the booking to the customer
```

---

## State Transition Map

This is defined in `app/engine/lifecycle.py` — the single source of truth:

```python
TRANSITIONS: dict[LeadState, set[LeadState]] = {
    LeadState.NEW:          {AUTO_REPLIED, OPTED_OUT},
    LeadState.AUTO_REPLIED: {ASSIGNED, ENGAGED, OPTED_OUT},
    LeadState.ASSIGNED:     {CLAIMED, ESCALATED, ENGAGED, OPTED_OUT},
    LeadState.ESCALATED:    {ASSIGNED, CLAIMED, ENGAGED, OPTED_OUT},
    LeadState.CLAIMED:      {ENGAGED, APPT_SET, LOST, OPTED_OUT},
    LeadState.ENGAGED:      {APPT_SET, LOST, OPTED_OUT},
    LeadState.APPT_SET:     {SHOWED, LOST, OPTED_OUT},
    LeadState.SHOWED:       {SOLD, LOST},
    LeadState.SOLD:         set(),   # terminal
    LeadState.LOST:         set(),   # terminal
    LeadState.OPTED_OUT:    set(),   # terminal
}
```

**Every transition creates a LeadEvent.** This append-only event stream is what Axis 2 (organization sinks) mirrors to external systems.

---

## Special Flows

### Opt-Out (STOP/ARRET)
```
Inbound SMS body in ["STOP", "STOPALL", "UNSUBSCRIBE", "ARRET"]
  → INSERT ConsentLog (action="opted_out")
  → lifecycle.transition(current → OPTED_OUT)
  → Reply: "You have been unsubscribed. Reply START to resubscribe."
```

### Missed Call Text-Back
```
Twilio Voice webhook (CallStatus=no-answer|busy|failed)
  → Check ConsentLog for opt-out
  → Reply: "Hi! We missed your call to {dealer_name}. Text us here..."
```

### Delivery Status Updates
```
Twilio status callback (POST /webhook/twilio/status)
  → Find Message by provider_sid
  → Update delivery_status + error_code
```
