# Email Channel Strategy — Speed to Lead v5

> **For:** AI agents implementing email lead handling
> **Prerequisite:** Read CODEBASE_AUDIT.md and REFACTORING_GUIDE.md first
> **Decision source:** Manav, Jun 19 planning session

---

## The Principle

Email leads from listing sites (AutoTrader, CarGurus, Kijiji) are CAPTURED via email, then FOLLOWED UP via SMS/WhatsApp — the channels where the AI engine already works. Email is not a conversation channel. It's a lead capture mechanism.

For leads with no phone number: AI sends one follow-up email, notifies rep, hands off. The rep judges whether it's worth pursuing. Low-intent leads waste salespeople's time — the system surfaces them, but the human decides.

---

## Routing Fork

One function, two branches. Lives in `tools/route_lead.py` after the email is parsed into a NormalizedLead.

```
Email lead parsed
      ↓
  Has usable phone?
  ↓ YES              ↓ NO
  SMS/WhatsApp       One AI email
  full pipeline      follow-up
  (existing code)    → ASSIGNED to rep
                     → dashboard (no Telegram ping)
```

**If the email-only customer replies:**
- System catches the reply (IMAP polling)
- Matches sender email → existing lead
- Right rep gets Telegram notification (with email-specific framing)
- Rep handles manually via dashboard
- AI is not involved after the one follow-up

---

## What Needs Building

### 1. Inbound Email Receiving

**Option A — IMAP polling (recommended for MVP):**
- Poll a dedicated inbox (e.g. `leads@premierautogroup.com`) every 60 seconds
- Parse new emails since last check (track by message ID or timestamp)
- Works with any email provider, no DNS changes
- Latency: ~60 seconds (acceptable — 60-second SLA starts when email arrives)

**Option B — Inbound webhook (for scale later):**
- Set up SendGrid Inbound Parse or Mailgun Routes
- Dealer forwards listing notifications to a dedicated address
- Webhook hits server instantly
- Requires DNS changes per dealer

Start with IMAP. Switch to webhooks when scaling past 50 dealers.

### 2. Site-Specific Parsers

Current `email_lead.py` uses generic regex. AutoTrader, CarGurus, Kijiji each have different templates.

```
app/adapters/intake/email_parsers/
    __init__.py          # registry + fallback
    autotrader_ca.py     # AutoTrader.ca templates
    cargurus.py          # CarGurus templates
    kijiji.py            # Kijiji templates
    generic.py           # LLM fallback for unknown templates
```

Each parser takes raw email body (subject + text/html) and returns a NormalizedLead.

**Known field patterns:**

AutoTrader.ca:
- "Customer Name:", "Phone:", "Email:", "Vehicle:", "Message:", "Ref #:"

CarGurus:
- "Customer Name:", "Phone:", "Email:", "Stock #:", "Listing ID:", "Message:"

Kijiji:
- Less standardized — use LLM fallback for unknown Kijiji formats
- Phone often embedded in body text, not labeled

### 3. Bugs to Fix in Existing Email Adapter

`app/adapters/intake/email_lead.py`:

**Bug 1 — Phone masking at parse time (line 49):**
```python
# WRONG — masks phone, breaks lookups
phone = mask_phone(_normalize_phone(phone_match.group(1).strip()))

# RIGHT — store as-is, mask at display time
phone = normalize_phone(phone_match.group(1).strip())
```

**Bug 2 — consent=False blocks follow-ups (line 79):**
```python
# WRONG — blocks all follow-ups
consent=False

# RIGHT — listing site inquiries are implied consent
# Customer filled out a form on AutoTrader saying "contact me"
consent=True
```

### 4. Routing Fork in `route_lead.py`

Add a new function for the no-phone email path. Lives after the existing `ingest_lead()` phone branch.

```python
def ingest_lead_email_no_phone(lead_data: NormalizedLead, dealer_config: dict, db_session):
    """Email lead with no phone number. One AI follow-up, then rep handoff."""

    # 1. Dedup by email (same email + same dealer = one lead)
    existing = db_session.query(Lead).filter(
        Lead.dealer_id == dealer_id,
        Lead.email == lead_data.email,
        Lead.state.notin_([LeadState.OPTED_OUT, LeadState.LOST, LeadState.SOLD])
    ).first()

    if existing:
        return existing  # Already handled

    # 2. Persist lead
    lead = Lead(
        dealer_id=dealer_id,
        source=Channel.EMAIL,
        name=lead_data.name,
        phone=None,
        email=lead_data.email,
        vehicle_ref=lead_data.vehicle_ref,
        state=LeadState.NEW,
        consent=True,  # Implied consent from listing site inquiry
    )
    db_session.add(lead)
    db_session.flush()

    # 3. Assign to rep (round-robin, no notification ping)
    assigned_rep = next_rep(dealer_config)
    lead.assigned_rep = assigned_rep

    # 4. AI generates follow-up email (personalized, uses vehicle inventory)
    email_body = _generate_email_followup(lead, dealer_config)

    # 5. Send one email via transactional email service
    _send_email(
        to=lead_data.email,
        from_email=dealer_config["channels"]["email_sender"],
        subject=f"Re: Your inquiry about {lead_data.vehicle_ref}",
        body=email_body,
    )

    # 6. Log the outbound email as a Message
    _record_email_message(lead, email_body, direction=Direction.OUTBOUND)

    # 7. Transition to ASSIGNED (not ENGAGED — AI is done)
    transition(lead, LeadState.ASSIGNED, db_session, reason="email_no_phone")

    # 8. No Telegram ping — lead sits in dashboard for rep to see

    db_session.commit()
    return lead
```

### 5. Outbound Email Sending

Need a transactional email service for sending follow-ups and forwarding rep replies.

**Recommended: SendGrid (free tier: 100/day)**
- Dealer forwards listing notifications to `leads@inbound.yourdomain.com`
- System sends follow-ups from `sales@premierautogroup.com` (dealer's actual email or a custom domain)

**Alternative: Mailgun (5000/month free)**

**Functions to build:**

```python
# app/transports/email.py
class EmailTransport:
    def send_email(self, to: str, from_email: str, subject: str, html_body: str) -> str:
        """Send email via SendGrid/Mailgun. Returns message ID."""
        pass

    def reply_to_email(self, original_message_id: str, body: str, from_email: str) -> str:
        """Reply to an existing email thread. Threading header logic."""
        pass
```

### 6. AI Email Follow-Up Generation

The one follow-up email must be personalized. Uses the same AI engine (OpenRouter) but a different prompt.

```python
def _generate_email_followup(lead: Lead, dealer_config: dict) -> str:
    """Generate a warm, personalized email follow-up for a listing site inquiry."""

    vehicle_info = resolve_vehicle(lead.vehicle_ref, dealer_config["dealer_slug"], session)

    system_prompt = f"""You are a salesperson at {dealer_config['name']}.
A customer inquired about a vehicle on a listing site. Write a warm,
personalized email follow-up. Reference the vehicle they asked about.
Keep it under 150 words. Include the vehicle price and key details.
Offer a specific time for a test drive. Include your phone number.
Do NOT sound like a chatbot. Sound like a real person."""

    user_prompt = f"""Customer: {lead.name}
Vehicle: {vehicle_info.make} {vehicle_info.model} {vehicle_info.year}
Price: ${vehicle_info.price:,.0f}
Original inquiry: {lead.vehicle_ref or 'general inquiry'}
Listing source: {lead.source.value}

Write the email body."""

    return call_openrouter(system_prompt, user_prompt)
```

### 7. Email Reply Detection

When the customer replies to the AI's follow-up email, the system needs to catch it and notify the rep.

**How it works:**
- IMAP polling checks for new emails in the same inbox
- When a reply arrives, the system matches the sender email address to existing leads
- If a match is found, the reply is stored as a new Message (sender_role="customer")
- The rep gets a Telegram notification with the reply content

**Matching logic:**
```python
def _find_lead_by_email(from_email: str, dealer_id: int, session) -> Lead | None:
    """Find existing lead by email address."""
    return session.query(Lead).filter(
        Lead.dealer_id == dealer_id,
        Lead.email == from_email,
        Lead.state.notin_([LeadState.OPTED_OUT, LeadState.LOST, LeadState.SOLD])
    ).first()
```

**Value cases:**
- Customer replies with questions → rep sees, responds via dashboard
- Customer says "not interested" → rep marks LOST, done
- No reply within 48h → lead sits in dashboard, no further action
- Reply comes weeks later → system catches it whenever it arrives

### 8. Telegram Notification for Email Replies

When an email-only lead replies, the rep gets a Telegram notification that's visually distinct from hot SMS leads. Different color code, different framing, different prompt.

**Hot SMS lead (customer replied to AI):**
```
🟢 HOT LEAD — John Smith
📱 +1 604-555-1234
🚗 2022 Honda Civic, $18,900
💬 "Can I come Saturday at 2pm?"
🤖 AI Status: READY TO BOOK

[View + Book Test Drive]
```

**Email reply (low intent, triage):**
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

Same Telegram bot. Same notification function. Different framing.

**Implementation in `notify_rep.py`:**
```python
def _build_email_reply_body(lead: Lead, reply_text: str) -> str:
    """Build Telegram notification for email reply (low-intent framing)."""
    vehicle = resolve_vehicle(lead.vehicle_ref, lead.dealer_slug)
    return f"""🔵 EMAIL REPLY — {lead.name or 'Unknown'}
(no phone available)
🚗 {vehicle or 'Vehicle inquiry'}
{f'💬 {reply_text[:200]}' if reply_text else ''}

⚡ Low intent — listing site lead

[View Thread + Reply]"""
```

### 9. Rep Handling of Email Replies

When the rep clicks "View Thread + Reply" in Telegram:
1. Dashboard opens to lead detail view
2. Email reply is visible as a message in the conversation thread
3. Rep types a reply
4. System sends the reply via email (from dealer's email address)
5. Rep marks the outcome: INTERESTED / LOW_INTENT / NOT_WORTH_PURSUING
6. If no response within 48h, system deprioritizes

**Note:** The rep replies from the dashboard, not from their personal email. The system sends on behalf of the dealer. This keeps everything tracked and auditable.

### 10. Edge Cases

**Edge case 1 — Email lead has phone but SMS fails:**
```
Has phone → try SMS auto-reply
    ↓ SMS fails
    Fall back to email follow-up path
    (same as no-phone: one attempt + rep handoff)
```

**Edge case 2 — Same customer via email AND SMS/WhatsApp:**
Phone-based dedup already handles this. Same phone number = same lead, regardless of source.

**Edge case 3 — Customer emails twice (different listings):**
Email-based dedup handles this for no-phone leads. Same email + same dealer = one lead.

**Edge case 4 — Customer replies weeks later:**
IMAP polling catches it whenever it arrives. Lead may be dormant. System surfaces it, rep decides whether to re-engage.

**Edge case 5 — Listing site sends multiple notifications for same inquiry:**
Cross-day dedup handles this. Same phone or email + same dealer = one lead.

---

## Cascade Timing (Email-Specific)

Email leads cascade more slowly than SMS/WhatsApp. Customers who inquire via listing sites are not waiting by their phone.

```python
EMAIL_CASCADE_TIMING = {
    "rep_timeout_hours": 24,      # 24h before cascade to next rep
    "rep_timeout_2_hours": 12,    # 12h before cascade after reassign
    "manager_notify_hours": 48,   # 48h total before manager
    "auto_deprioritize_hours": 72 # 72h no reply → EMAIL_NO_REPLY status
}
```

For comparison, SMS/WhatsApp:
```python
SMS_CASCADE_TIMING = {
    "rep_timeout_minutes": 5,     # 5 min (customer is waiting NOW)
    "rep_timeout_2_minutes": 3,
    "manager_notify_minutes": 15,
}
```

---

## Dashboard Impact

Minimal changes needed. Email leads already show up as source=email.

**New additions:**
- Lead detail: show original email content as first "message" in conversation thread
- Email reply detection: if customer replied to follow-up email, show reply as a message
- Lead badge: "No phone" indicator on email-only leads
- Rep can type reply in lead detail view, system sends via email

**Existing features work unchanged:**
- Lead list with filters
- Health indicators (Hot/Warm/Cold/Dead)
- Attention widget (shows leads without activity)
- Rep leaderboard
- Appointment calendar

---

## What NOT to Build

- Email conversation threading (keep it simple: one follow-up, manual replies via dashboard)
- Email AI conversation engine (the AI does one follow-up, then rep owns it)
- Multiple follow-up emails (one shot only — don't chase low-intent leads)
- Email auto-reply (redundant — the one follow-up IS the auto-reply)
- Email signature customization (use dealer name from config, keep it simple)

---

## One-Shot Enforcement

The system MUST guarantee only ONE email is sent per no-phone lead. Implement a guard:

```python
def ingest_lead_email_no_phone(lead_data, dealer_config, db_session):
    # ... dedup logic ...

    # GUARD: prevent duplicate sends
    existing = db_session.query(Lead).filter(
        Lead.dealer_id == dealer_id,
        Lead.email == lead_data.email,
        Lead.source == Channel.EMAIL,
    ).first()
    if existing:
        return existing  # Already handled — do NOT send another email

    # ... persist + send ...
```

Also add a `first_email_sent_at` timestamp to the Lead model for audit trail.

---

## CASL Compliance for Email

Under CASL, listing site inquiries are implied consent (customer initiated contact). But email follow-ups must:

1. **Reference the original inquiry** — "Hi John, about the 2022 Honda Civic you inquired about on AutoTrader..."
2. **Include dealer identity** — dealer name, address, phone number
3. **Include unsubscribe link** — standard email footer with one-click unsubscribe
4. **Include STOP language** — "Reply STOP to opt out of further emails"

The customer filled out a form on the listing site saying "contact me." That's sufficient consent for ONE follow-up. No additional consent collection needed.

If the customer replies "STOP" or "unsubscribe," mark `consent=False` and `opt_out=True` on the lead. Do not send further emails.

---

## Error Handling

### SendGrid/Mailgun failure
```python
def _send_email(to, from_email, subject, body):
    try:
        sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
        message = Mail(from_email=from_email, to_emails=to, subject=subject, html_content=body)
        response = sg.send(message)
        return response.status_code
    except Exception as e:
        # Log error, do NOT crash the pipeline
        logger.error(f"Email send failed: {e}")
        # Lead is still persisted — rep can see it in dashboard and follow up manually
        return None
```

If email sending fails, the lead is still in the dashboard. The rep can see it and follow up manually. Email failure should NOT block lead persistence.

### IMAP polling failure
```python
def poll_inbox(dealer_config):
    try:
        # connect + fetch
    except imaplib.IMAP4.error as e:
        logger.error(f"IMAP poll failed: {e}")
        # Do NOT crash the scheduler. Next poll will retry.
        return
```

### Email reply matching failure
If a reply comes in but doesn't match any existing lead (sender email not in DB), log it as an unmatched email and surface it in the dashboard under a "Unmatched Emails" section. The rep can manually assign it to a lead.

---

## Rate Limiting

Prevent the system from sending excessive emails:

```python
# In scheduler.py or wherever email sends are triggered
MAX_EMAILS_PER_HOUR = 50   # Per dealer
MAX_EMAILS_PER_DAY = 200   # Per dealer
```

If the limit is hit, log a warning and queue remaining emails for the next hour. Do NOT silently drop them.

For MVP: hard limits in config. For scale: use SendGrid's built-in rate limiting.

---

## Build Order

```
1. Fix email parser bugs (masking + consent)              5 min
2. Build site-specific email parsers (AutoTrader, etc.)   2 hours
3. Build IMAP polling for inbound email                   2 hours
4. Build outbound email transport (SendGrid)              1 hour
5. Build AI email follow-up generation                    1 hour
6. Build routing fork (phone vs no-phone branch)          30 min
7. Build email reply detection                            2 hours
8. Build Telegram notification for email replies          30 min
9. Build dashboard changes (email reply display)          1 hour
                                                     ────────
                                                     ~10 hours
```

**Critical path (email leads stop falling through cracks):**
Steps 1–6 = ~7 hours → email leads are captured and followed up

Steps 7–9 add reply detection and rep workflow — important for triage but not blocking.

---

*Last updated: 2026-06-19.*