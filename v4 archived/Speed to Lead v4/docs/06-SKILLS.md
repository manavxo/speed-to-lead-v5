# Skills Reference for Speed to Lead v4

This document compiles specialized knowledge from proven workflows. Read this before implementing any feature.

---

## 1. Lead Response System Architecture

### The Speed-to-Lead Principle

Industry data (InsideSales.com, Cox Automotive, NADA):
- Dealers who respond in <5 minutes are 100x more likely to connect
- Average dealership response time: 5+ hours
- 47% of internet leads come after business hours — when nobody answers
- 1 in 5 dealer leads never get a response at all
- 78% of customers buy from the first dealer to respond

Your system's ENTIRE value proposition is: respond in <60 seconds, 24/7. Every feature, every optimization, every decision should serve this.

### Response Time Breakdown

```
Lead arrives (T+0)
  → Normalize + persist (T+0.1s)
  → SMS auto-reply sent (T+2-5s)         ← THIS IS THE MAGIC
  → Vehicle lookup in reply (T+3-6s)
  → Round-robin assignment (T+5-8s)
  → WhatsApp claim ping to rep (T+6-10s)
  → Rep claims (T+30-300s) or escalates
```

The auto-reply is what makes this product work. Everything else is enhancement.

### Multi-Channel Lead Capture

Leads arrive from these sources. Each needs an intake adapter:

| Source | Delivery Method | Adapter |
|--------|----------------|---------|
| Website forms | Webhook POST | intake_webform |
| Twilio SMS | Webhook POST | intake_sms |
| Email (AutoTrader, CarGurus, Kijiji) | Email forwarding → parse | intake_email |
| Facebook Messenger | Webhook POST | (future) |
| Phone calls | Twilio call webhook | (future) |
| Instagram DMs | Graph API webhook | (future) |

**Key insight:** Almost every listing site delivers leads via email. A single email forwarding rule captures AutoTrader + CarGurus + Kijiji + website forms + chat widgets.

**Future-proofing:** The three-axis adapter model (intake / inventory / organization) means new sources are just new adapter files. No core code changes.

### Compliance Rules (Non-Negotiable)

**CASL (Canada's Anti-Spam Law):**
- Every SMS must include: business name + address + phone + opt-out instruction
- Consent must be recorded with source and timestamp
- STOP/ARRET must be processed within 1 message, confirmed within 1 message
- Opt-out must be logged to ConsentLog with method and timestamp

**PIPA BC (Personal Information Protection Act):**
- Collect only what you need (name, phone, email, vehicle interest)
- Store with purpose limitation (lead management only)
- Provide data access/deletion on request
- Audit trail for all data access

**Quiet Hours:**
- No outbound messages between 9:00 PM and 8:00 AM in the dealer's timezone
- Opt-out processing is exempt (always respond to STOP immediately)
- Auto-replies are exempt (the lead just texted you)

### The Compliance Gate Pattern

Every outbound message passes through this gate in `tools/send_sms.py`:

```python
def send_sms(db, lead, body, *, channel="sms", in_reply_to=None, ai_generated=False, approved_by=None):
    """The ONLY function that sends messages. All outbound traffic flows through here."""
    
    # Gate 1: OUTBOUND_ENABLED must be true
    if not settings.OUTBOUND_ENABLED:
        # Return DRYRUN SID, persist Message row, skip provider call
        return dryrun_result
    
    # Gate 2: Lead must not be opted out
    if lead.consent == ConsentStatus.OPTED_OUT:
        raise ValueError("Lead is opted out")
    
    # Gate 3: Quiet hours check (opt-out confirmations exempt)
    if not is_opt_out_confirmation and is_quiet_hours(settings.QUIET_HOURS_START, settings.QUIET_HOURS_END):
        # Queue for later, don't send now
        return queued_result
    
    # Gate 4: Append opt-out footer if not present
    final_body = append_compliance_footer(body, settings.BUSINESS_NAME, settings.BUSINESS_ADDRESS)
    
    # Gate 5: Send via Twilio
    message = client.messages.create(to=lead.phone, from_=settings.TWILIO_PHONE_NUMBER, body=final_body)
    
    # Gate 6: Persist Message row with provider SID
    persist_message(db, lead, final_body, message.sid, "sent", ai_generated, approved_by)
    
    return message.sid
```

**Anti-pattern:** Never call the Twilio SDK directly from any module other than `send_sms.py`. Every message MUST pass through the compliance gate.

---

## 2. Testing Strategy

### The Two-Dimensional Test Matrix

| | Real SMS (Twilio) | Fake SMS (FakeTwilio) |
|---|---|---|
| **Real LLM (OpenRouter)** | LIVE FIRE (production) | SMOKE TEST |
| **Fake LLM (FakeLLM)** | CHAOS MODE | UNIT TESTS (default) |

Default mode uses FakeTwilio + FakeLLM. No API keys needed, no credits burned, deterministic results.

### Fake Test Doubles

**FakeTwilio:** Drop-in replacement for the Twilio SDK. Intercepts `client.messages.create()` calls, stores them in an in-memory list. Verify message content, recipient, and count without sending real SMS.

**FakeLLM:** Drop-in replacement for the OpenAI SDK. Returns canned responses based on the conversation state. No API calls, no costs, deterministic.

### Test Categories

1. **Unit tests** — Individual functions with fake doubles. Fast, deterministic.
2. **Integration tests** — Full pipeline flow with fake doubles. Tests the wiring.
3. **Smoke tests** — App starts, endpoints respond, templates render. No external calls.
4. **E2E lifecycle tests** — Full lead lifecycle from intake to appointment. Fake doubles.
5. **Live-fire tests** — Real Twilio + real phones. Only when explicitly enabled.

### Running Tests

```bash
# Default (fake everything, fast)
pytest -q

# With verbose output
pytest -v

# Specific test file
pytest tests/test_smoke.py -v

# Live-fire (requires real Twilio credentials)
LIVE_FIRE=true TWILIO_ACCOUNT_SID=xxx TWILIO_AUTH_TOKEN=xxx pytest tests/test_live_fire.py -v
```

### Anti-Patterns

- **Don't skip tests because "it works on my machine."** Run them.
- **Don't use real API keys in tests.** Use the fake doubles.
- **Don't test the external service.** Test YOUR code's response to the service.
- **Don't leave broken tests.** Fix them or mark them as expected failures with a comment explaining why.

---

## 3. Dashboard Feature Implementation Patterns

### Computing Metrics from Existing Data

All dashboard features use read-only queries on existing tables. No new tables needed.

**Response time:** Query `Message` table for the time delta between the first inbound message and the first outbound message for each lead.

```sql
-- Average response time (seconds)
SELECT AVG(
    EXTRACT(EPOCH FROM (outbound.created_at - inbound.created_at))
) as avg_response_seconds
FROM messages outbound
JOIN messages inbound ON inbound.lead_id = outbound.lead_id
WHERE outbound.direction = 'outbound'
AND inbound.direction = 'inbound'
AND inbound.id = (
    SELECT MIN(id) FROM messages WHERE lead_id = outbound.lead_id AND direction = 'inbound'
)
AND outbound.id = (
    SELECT MIN(id) FROM messages WHERE lead_id = outbound.lead_id AND direction = 'outbound'
);
```

**Lead health indicator:** Computed from state + timestamp age.

```python
def get_lead_health(lead):
    """Returns 'hot', 'warm', 'cold', or 'dead' based on activity."""
    now = datetime.now(timezone.utc)
    age_hours = (now - lead.updated_at).total_seconds() / 3600
    
    if lead.state == LeadState.APPT_SET:
        return "hot"  # Has appointment
    if lead.state == LeadState.ENGAGED and age_hours < 24:
        return "warm"  # Active conversation
    if age_hours < 48:
        return "warm"  # Recent activity
    if age_hours < 72:
        return "cold"  # Getting stale
    return "dead"  # Needs attention
```

**"Needs Attention" priority queue:** Composite query for stuck leads.

```python
def get_attention_items(db, dealer_id):
    """Returns the top 10 most urgent items for the GM."""
    items = []
    
    # 1. Unclaimed leads (ASSIGNED > 2 hours)
    unclaimed = db.query(Lead).filter(
        Lead.dealer_id == dealer_id,
        Lead.state == LeadState.ASSIGNED,
        Lead.updated_at < datetime.now(timezone.utc) - timedelta(hours=2)
    ).all()
    for lead in unclaimed:
        items.append({"type": "unclaimed", "lead": lead, "urgency": "high"})
    
    # 2. Going cold (ENGAGED with no activity in 48h)
    cold = db.query(Lead).filter(
        Lead.dealer_id == dealer_id,
        Lead.state == LeadState.ENGAGED,
        Lead.updated_at < datetime.now(timezone.utc) - timedelta(hours=48)
    ).all()
    for lead in cold:
        items.append({"type": "going_cold", "lead": lead, "urgency": "medium"})
    
    # 3. Appointments today
    today = datetime.now(timezone.utc).date()
    appts = db.query(Appointment).join(Lead).filter(
        Lead.dealer_id == dealer_id,
        Appointment.scheduled_for >= today,
        Appointment.scheduled_for < today + timedelta(days=1)
    ).all()
    for appt in appts:
        items.append({"type": "appointment_today", "appointment": appt, "urgency": "high"})
    
    # 4. Failed message deliveries
    failed = db.query(Message).join(Lead).filter(
        Lead.dealer_id == dealer_id,
        Message.delivery_status == "failed"
    ).all()
    for msg in failed:
        items.append({"type": "delivery_failure", "message": msg, "urgency": "high"})
    
    return sorted(items, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x["urgency"]])[:10]
```

### HTMX Patterns for Dashboard

```html
<!-- Auto-refresh a section every 30 seconds -->
<div hx-get="/dashboard/leads" hx-trigger="every 30s" hx-swap="innerHTML">
    <!-- Lead table content -->
</div>

<!-- Click to update a lead status -->
<button hx-put="/dashboard/leads/1/status"
        hx-vals='{"state": "CLAIMED"}'
        hx-target="#lead-1-row"
        hx-swap="outerHTML">
    Claim Lead
</button>

<!-- Load detail view without page refresh -->
<tr hx-get="/dashboard/leads/1" hx-target="#main-content" hx-swap="innerHTML" style="cursor:pointer">
    <td>Sarah Mitchell</td>
    <td>2024 Honda CR-V</td>
</tr>
```

---

## 4. Deployment Pitfalls

### Render-Specific Issues

1. **Cold starts on free/hobby tier:** App sleeps after 15 min of inactivity. First request takes 30-60 seconds. Use a cron ping every 10 minutes during demo hours.

2. **DATABASE_URL format:** Render uses `postgresql://` but SQLAlchemy sometimes needs `postgresql+psycopg://`. Check `app/db.py`.

3. **Port binding:** Render sets `$PORT` env var. Your app MUST bind to `0.0.0.0:$PORT`, not `127.0.0.1:8000`.

4. **Static files:** Jinja2 templates are compiled at runtime, not served as static files. No CDN needed.

5. **Health check:** Render pings `/healthz` to determine if the app is alive. If this returns 503, Render restarts the container. Make sure it always returns 200 when the process is up.

### Environment Variables Checklist

```bash
# REQUIRED for basic operation
DATABASE_URL=postgresql://...        # From Render's Postgres service
ENVIRONMENT=production               # production | staging | development

# REQUIRED for SMS functionality
TWILIO_ACCOUNT_SID=ACxxxx           # From Twilio console
TWILIO_AUTH_TOKEN=xxxx              # From Twilio console
TWILIO_PHONE_NUMBER=+17787623122   # Your Twilio number
OPENROUTER_API_KEY=sk-or-xxxx      # From OpenRouter
OUTBOUND_ENABLED=false              # Set to true ONLY when Twilio is configured

# OPTIONAL
OPENROUTER_MODEL=anthropic/claude-sonnet-4  # Default model
PUBLIC_BASE_URL=https://your-app.onrender.com  # For Twilio webhooks
```

**Anti-pattern:** Never set `OUTBOUND_ENABLED=true` until Twilio is fully configured and tested. The safety gate exists for a reason.

---

## 5. Common Pitfalls and Anti-Patterns

### Code-Level

- **Never call Twilio directly.** Always go through `tools/send_sms.py`.
- **Never skip the compliance footer.** Every SMS needs business name + address + opt-out.
- **Never store raw API responses.** Normalize to canonical models first.
- **Never hardcode phone numbers.** They come from env vars or dealer config.
- **Never log PII (phone, email) at INFO level.** Use DEBUG or redact.

### Architecture-Level

- **Don't add new database tables without checking if existing tables can serve the purpose.** LeadEvent (append-only log) + Message are extremely flexible.
- **Don't create a separate scheduler process.** Merge into FastAPI lifespan.
- **Don't use React/Vue/Next.js for the dashboard.** Jinja2 + HTMX is enough.
- **Don't add Alembic for schema migrations.** SQLModel's `create_all()` is fine for now.
- **Don't add Redis, Celery, or any infrastructure that costs money.** APScheduler + Postgres is enough.

### Product-Level

- **Don't over-engineer for scale you don't have.** One dealer is not 100 dealers.
- **Don't add features just because competitors have them.** Your edge is speed + simplicity + price.
- **Don't ask for backend access.** Email forwarding + a phone number swap is all you need.
- **Don't promise AI capabilities you can't deliver.** The AI qualifies leads. It doesn't close deals.

---

## 6. QA Checklist (Per Feature)

Before marking any feature as complete:

```
[ ] Tests pass (pytest -q)
[ ] Module imports without errors
[ ] Feature works with OUTBOUND_ENABLED=false (dry-run mode)
[ ] Feature handles empty/null inputs gracefully
[ ] No hardcoded secrets in the code
[ ] No PII at INFO log level
[ ] Dashboard renders on mobile (test at 375px width)
[ ] Feature doesn't touch the core engine (lifecycle.py)
[ ] Feature uses existing data (no new tables)
[ ] HTMX partial updates work (no full page reloads for dashboard actions)
```
