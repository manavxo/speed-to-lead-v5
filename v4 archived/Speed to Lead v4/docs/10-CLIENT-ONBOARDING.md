# Speed to Lead v4 — Client Onboarding Guide

> **Goal:** Onboard a new used-car dealer in under 30 minutes with zero code changes.
> **How:** Fill out the onboarding form at `/dashboard/onboarding` → it generates a validated YAML config + DB record → dealer is live.

---

## Table of Contents

1. [Onboarding Overview](#1-onboarding-overview)
2. [Web Form Fields](#2-web-form-fields)
3. [YAML Generation Logic](#3-yaml-generation-logic)
4. [Provisioning Flow](#4-provisioning-flow)
5. [Twilio Setup Checklist](#5-twilio-setup-checklist)
6. [Per-Client Testing Steps](#6-per-client-testing-steps)
7. [Post-Onboarding Checklist](#7-post-onboarding-checklist)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Onboarding Overview

### The "Drop-In" Model

Speed to Lead uses a **config-driven multi-tenant model**:
- Each dealer gets a YAML config file at `dealers/<slug>.yaml`
- The YAML declares every behavior (channels, sales team, AI personality, hours, compliance)
- Validated by Pydantic's `DealerConfig` model at load time
- A `Dealer` row in the DB indexes key fields for fast tenant resolution
- **No code changes needed per dealer** — just a new YAML + DB row

### Onboarding Flow

```
Admin fills form at /dashboard/onboarding
          │
          ▼
┌─────────────────────┐
│  1. Validate input   │  (Pydantic validation)
│  2. Check slug unique │  (DB + filesystem check)
│  3. Generate YAML    │  (write to dealers/<slug>.yaml)
│  4. Create DB record │  (INSERT into dealer table)
│  5. Provision Twilio │  (manual checklist)
│  6. Test all channels│  (automated + manual)
└─────────────────────┘
          │
          ▼
   Dealer is live!
```

---

## 2. Web Form Fields

The onboarding form at `/dashboard/onboarding` collects the following:

### Section 1: Business Info

| Field | Type | Required | Example | Notes |
|-------|------|----------|---------|-------|
| Business Name | text | ✅ | Sunrise Auto Sales | Display name for the dealer |
| Slug | text | ✅ | sunrise-auto | Kebab-case, unique, used in URLs and file paths |
| Timezone | select | ✅ | America/Vancouver | Dropdown of Canadian timezones |
| Main Phone | tel | ❌ | +16045550100 | E.164 format |
| Address | text | ❌ | 1234 Kingsway, Vancouver, BC | Full street address |
| Maps URL | url | ❌ | https://maps.google.com/?q=... | Google Maps link |

### Section 2: Business Hours

| Field | Type | Required | Example | Notes |
|-------|------|----------|---------|-------|
| Monday | time range | ❌ | 09:00-19:00 | Or "closed" |
| Tuesday | time range | ❌ | 09:00-19:00 | Or "closed" |
| Wednesday | time range | ❌ | 09:00-19:00 | Or "closed" |
| Thursday | time range | ❌ | 09:00-19:00 | Or "closed" |
| Friday | time range | ❌ | 09:00-19:00 | Or "closed" |
| Saturday | time range | ❌ | 10:00-17:00 | Or "closed" |
| Sunday | time range | ❌ | closed | Typically closed |

### Section 3: Sales Team

Dynamic list — admin can add/remove reps:

| Field | Type | Required | Example | Notes |
|-------|------|----------|---------|-------|
| Rep Name | text | ✅ | Mike | First name or display name |
| WhatsApp Number | tel | ✅ | +16045550121 | Must be WhatsApp-enabled on Twilio |
| Active | checkbox | ✅ | checked | Whether rep is in rotation |

### Section 4: Channels

| Field | Type | Required | Example | Notes |
|-------|------|----------|---------|-------|
| SMS Number | tel | ✅ | +17785550111 | Twilio number for lead-facing SMS |
| WhatsApp Sender | tel | ❌ | +17785550112 | Twilio WhatsApp SANDBOX or production sender |
| Lead Email Inbox | email | ❌ | leads+sunrise@domain.com | Where 3rd-party lead emails forward to |
| Facebook Page ID | text | ❌ | | Optional, via Twilio Conversations |
| Web Form Token | text | auto | sunrise-9f3a2b | Auto-generated, can be overridden |

### Section 5: Routing

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| Strategy | select | ❌ | round_robin | round_robin, by_source, single_pool |
| Claim Timeout (min) | number | ❌ | 5 | Minutes before reassignment |
| Manager Phone | tel | ❌ | | Escalation target |

### Section 6: AI Personality

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| Persona | text | ❌ | friendly, concise, no-pressure local sales rep | How the AI presents itself |
| Goal | select | ❌ | book_appointment | book_appointment, collect_info, answer_questions |
| No Price Negotiation | checkbox | ❌ | checked | Guardrail |
| No Financing Promises | checkbox | ❌ | checked | Guardrail |

### Section 7: Inventory

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| Source | select | ❌ | auto | auto, feed, dms, structured_data, website_scrape, manual, none |
| URL | url | ❌ | | Website or feed URL |
| Platform | text | ❌ | | Optional hint (dealerpull, dealercenter, etc.) |
| Refresh (min) | number | ❌ | 180 | How often to re-sync inventory |

### Section 8: Lead Organization

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| Mode | select | ❌ | native | native, crm_sync, sheet, webhook, email_digest |
| Target | text | ❌ | | CRM name, Sheet ID, or webhook URL |
| Credentials Ref | text | ❌ | | Name of secret in .env/Render vault |

### Section 9: Compliance (Canada / BC)

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| Region | select | ❌ | CA-BC | CASL/PIPA compliance region |
| Consent Text | textarea | ❌ | (auto-generated) | Text shown to leads |
| Opt-Out Keywords | text | ❌ | STOP, STOPALL, UNSUBSCRIBE, ARRET | Comma-separated |
| Quiet Hours | text | ❌ | 21:00-08:00 | No outbound during this window |

---

## 3. YAML Generation Logic

### How the Form Maps to YAML

The onboarding handler builds a `DealerConfig` Pydantic model from the form data, serializes it to YAML, and writes it to `dealers/<slug>.yaml`.

```python
# Simplified logic (actual implementation in app/dashboard/__init__.py)

from app.config import (
    DealerConfig, Dealer, Channels, SalesRep, Routing,
    AIConfig, Followups, Inventory, LeadOrg, Compliance
)
import yaml
from pathlib import Path

def generate_dealer_yaml(form_data: dict) -> str:
    """Convert form POST data to a validated DealerConfig YAML."""
    
    # 1. Build the DealerConfig from form fields
    config = DealerConfig(
        dealer=Dealer(
            slug=form_data["slug"],
            name=form_data["business_name"],
            timezone=form_data["timezone"],
            hours={
                day: form_data.get(f"hours_{day}", "closed")
                for day in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
            },
            location_address=form_data.get("address") or None,
            maps_url=form_data.get("maps_url") or None,
            main_phone=form_data.get("main_phone") or None,
        ),
        channels=Channels(
            sms_number=form_data.get("sms_number") or None,
            whatsapp_sender=form_data.get("whatsapp_sender") or None,
            lead_email_inbox=form_data.get("lead_email_inbox") or None,
            facebook_page_id=form_data.get("facebook_page_id") or None,
            web_form_token=form_data.get("web_form_token") or generate_token(form_data["slug"]),
        ),
        sales_team=[
            SalesRep(
                name=rep["name"],
                whatsapp=rep["whatsapp"],
                active=rep.get("active", True),
            )
            for rep in form_data.get("sales_team", [])
        ],
        routing=Routing(
            strategy=form_data.get("routing_strategy", "round_robin"),
            claim_timeout_min=int(form_data.get("claim_timeout_min", 5)),
            manager_phone=form_data.get("manager_phone") or None,
        ),
        ai=AIConfig(
            persona=form_data.get("ai_persona", "friendly, concise, no-pressure local sales rep"),
            goal=form_data.get("ai_goal", "book_appointment"),
            guardrails={
                "no_price_negotiation": form_data.get("no_price_negotiation", "on") == "on",
                "no_financing_promises": form_data.get("no_financing_promises", "on") == "on",
            },
        ),
        inventory=Inventory(
            source=form_data.get("inventory_source", "auto"),
            url=form_data.get("inventory_url") or None,
            platform=form_data.get("inventory_platform", ""),
            refresh_min=int(form_data.get("inventory_refresh_min", 180)),
        ),
        lead_org=LeadOrg(
            mode=form_data.get("lead_org_mode", "native"),
            target=form_data.get("lead_org_target", ""),
            credentials_ref=form_data.get("lead_org_credentials_ref", ""),
        ),
        compliance=Compliance(
            region=form_data.get("compliance_region", "CA-BC"),
            consent_text=form_data.get("consent_text", "").format(dealer_name=form_data["business_name"]),
            quiet_hours=form_data.get("quiet_hours", "21:00-08:00"),
        ),
    )
    
    # 2. Validate (Pydantic does this on construction)
    # 3. Serialize to YAML
    data = config.model_dump()
    return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)


def generate_token(slug: str) -> str:
    """Generate a unique web form token from the slug."""
    import secrets
    suffix = secrets.token_hex(3)
    return f"{slug}-{suffix}"
```

### YAML Output Example

After filling out the form for "Sunrise Auto Sales", the generated file `dealers/sunrise-auto.yaml` looks like:

```yaml
dealer:
  slug: sunrise-auto
  name: Sunrise Auto Sales
  timezone: America/Vancouver
  hours:
    mon: "09:00-19:00"
    tue: "09:00-19:00"
    wed: "09:00-19:00"
    thu: "09:00-19:00"
    fri: "09:00-19:00"
    sat: "10:00-17:00"
    sun: closed
  location_address: 1234 Kingsway, Vancouver, BC
  maps_url: "https://maps.google.com/?q=Sunrise+Auto+Sales"
  main_phone: "+16045550100"

channels:
  sms_number: "+17785550111"
  whatsapp_sender: "+17785550112"
  lead_email_inbox: "leads+sunrise@domain.com"
  facebook_page_id: ""
  web_form_token: "sunrise-9f3a2b"

sales_team:
  - name: Mike
    whatsapp: "+16045550121"
    active: true
  - name: Dana
    whatsapp: "+16045550122"
    active: true

routing:
  strategy: round_robin
  claim_timeout_min: 5
  escalation:
  - reassign
  - notify_manager
  manager_phone: "+16045550130"

ai:
  persona: friendly, concise, no-pressure local sales rep
  goal: book_appointment
  guardrails:
    no_price_negotiation: true
    no_financing_promises: true

followups:
  cadence_min:
  - 60
  - 1440
  - 4320
  - 10080

inventory:
  source: auto
  url: "https://sunriseauto.example.ca/inventory"
  platform: ""
  refresh_min: 180
  field_map: auto

lead_org:
  mode: native
  target: ""
  credentials_ref: ""

compliance:
  region: CA-BC
  consent_text: "By submitting you agree to receive texts from Sunrise Auto Sales. Reply STOP to opt out."
  opt_out_keywords:
  - STOP
  - STOPALL
  - UNSUBSCRIBE
  - ARRET
  quiet_hours: "21:00-08:00"
```

---

## 4. Provisioning Flow

### Step-by-Step

```
1. Admin navigates to /dashboard/onboarding
2. Fills out the form (9 sections)
3. Clicks "Provision Dealer"
4. Server-side:
   a. Validates all fields (Pydantic DealerConfig)
   b. Checks slug uniqueness (DB + filesystem)
   c. Auto-generates web_form_token if not provided
   d. Writes YAML to dealers/<slug>.yaml
   e. Creates Dealer DB row with:
      - slug, name, timezone
      - sms_number (indexed — used for tenant resolution)
      - whatsapp_sender (indexed)
      - web_form_token (indexed, unique)
      - config (full JSON dump of DealerConfig)
   f. Returns success page with:
      - Generated YAML preview
      - Twilio setup checklist
      - Test URLs
5. Admin follows the Twilio setup checklist
6. Tests each channel
7. Dealer goes live!
```

### Idempotency
- If a dealer with the same slug exists, the form shows an error
- The slug is the primary key for dealer identity
- Re-provisioning the same slug overwrites the YAML and updates the DB row

### Rollback
To remove a dealer:
1. Delete `dealers/<slug>.yaml`
2. Delete the `Dealer` row (and cascading `Lead`, `Message`, etc. rows)
3. Release the Twilio number back to the pool

---

## 5. Twilio Setup Checklist

### Per-Dealer Twilio Provisioning

```
□ 1. BUY A TWILIO PHONE NUMBER
   - Go to twilio.com/console/phone-numbers
   - Buy a Canadian number (BC area code preferred: 604, 778, 236)
   - This becomes the dealer's sms_number
   - Record the number: +1__________

□ 2. CONFIGURE SMS WEBHOOK
   - In Twilio console → Phone Numbers → select the new number
   - Under "Messaging":
     - "A message comes in" → Webhook
     - URL: https://speed-to-lead-8tfi.onrender.com/webhook/sms/inbound
     - Method: POST
   - Save

□ 3. SET UP WHATSAPP SANDBOX (Testing)
   - Go to twilio.com/console/sms/whatsapp/sandbox
   - Join the sandbox by sending the join code from a test phone
   - Note the sandbox number: +14155238886 (or similar)
   - This becomes the dealer's whatsapp_sender (for rep notifications)

□ 4. (OPTIONAL) WHATSAPP PRODUCTION SENDER
   - Apply for WhatsApp Business API access
   - Register a WhatsApp Business number
   - This takes 1-3 weeks for approval
   - Once approved, update whatsapp_sender in the YAML

□ 5. (OPTIONAL) EMAIL FORWARDING
   - Set up email forwarding from the dealer's lead inbox
     (e.g., leads+sunrise@domain.com) to a webhook endpoint
   - Or configure a service like SendGrid/Mailgun to POST
     to /webhook/email/inbound

□ 6. (OPTIONAL) WEB FORM EMBED
   - Share the embed code with the dealer:
     <form action="https://speed-to-lead-8tfi.onrender.com/webhook/form/{web_form_token}" method="POST">
       <input name="name" placeholder="Your name">
       <input name="phone" placeholder="Phone number">
       <input name="email" placeholder="Email">
       <input name="vehicle_ref" placeholder="Vehicle of interest">
       <button type="submit">Get Info</button>
     </form>

□ 7. VERIFY ALL NUMBERS
   - Send a test SMS FROM the dealer's sms_number TO a test phone
   - Send a test SMS TO the dealer's sms_number FROM a test phone
   - Verify the webhook fires and creates a Lead in the DB
   - Send a test WhatsApp message to the sandbox
   - Verify rep notification is received
```

### Environment Variables (Render Dashboard)
```
If each dealer uses different Twilio credentials (unlikely for v4):
  - Per-dealer credentials would go in a vault (future)
  
For shared Twilio credentials (current model):
  - TWILIO_ACCOUNT_SID = (already set)
  - TWILIO_AUTH_TOKEN = (already set)
```

---

## 6. Per-Client Testing Steps

After provisioning, test each channel systematically:

### Test Matrix

| # | Test | Steps | Expected Result |
|---|------|-------|-----------------|
| 1 | **SMS Inbound** | Send SMS to dealer's sms_number | Lead created in DB with state=NEW, auto-reply sent |
| 2 | **SMS Auto-Reply** | Verify reply received on test phone | AI-generated response within 10s |
| 3 | **Rep Notification** | Check WhatsApp for rep claim ping | Round-robin assigned rep gets WhatsApp message |
| 4 | **Rep Claim** | Reply "CLAIM" on WhatsApp | Lead state → CLAIMED, assigned to rep |
| 5 | **Business Hours** | Test during open hours | AI drafts message, sends for rep approval |
| 6 | **After Hours** | Test during closed hours | AI responds autonomously |
| 7 | **Opt-Out** | Send "STOP" to dealer number | Consent revoked, state → OPTED_OUT, confirmation sent |
| 8 | **Web Form** | Submit test form | Lead created with source=webform |
| 9 | **Follow-Up** | Wait for cold lead (or adjust cadence) | Follow-up message sent per cadence |
| 10 | **Dashboard** | Check /dashboard/leads | New lead visible with correct data |
| 11 | **Stats** | Check /dashboard/stats | Lead appears in metrics |
| 12 | **Compliance** | Verify consent text in auto-reply | Consent text present, STOP keyword works |

### Automated Test Script

```python
# tools/test_dealer.py
"""Quick smoke test for a newly provisioned dealer."""
import requests
import sys

BASE_URL = "https://speed-to-lead-8tfi.onrender.com"

def test_dealer(slug: str):
    # 1. Check YAML exists and is valid
    print(f"✓ Testing dealer: {slug}")
    
    # 2. Check health
    r = requests.get(f"{BASE_URL}/healthz")
    assert r.status_code == 200, f"Health check failed: {r.status_code}"
    print("✓ Health check passed")
    
    # 3. Submit a test web form
    # (Get the web_form_token from the YAML first)
    import yaml
    from pathlib import Path
    config = yaml.safe_load(Path(f"dealers/{slug}.yaml").read_text())
    token = config["channels"]["web_form_token"]
    
    r = requests.post(f"{BASE_URL}/webhook/form/{token}", data={
        "name": "Test Lead",
        "phone": "+12065551234",
        "email": "test@example.com",
        "vehicle_ref": "2024 Honda Civic",
    })
    assert r.status_code in (200, 201, 303), f"Form submission failed: {r.status_code}"
    print("✓ Web form submission passed")
    
    # 4. Check dashboard
    session = requests.Session()
    session.post(f"{BASE_URL}/dashboard/login", data={
        "username": "admin",
        "password": "your-password",
    })
    r = session.get(f"{BASE_URL}/dashboard/leads")
    assert "Test Lead" in r.text, "Lead not found in dashboard"
    print("✓ Dashboard shows test lead")
    
    print(f"\n✅ All tests passed for {slug}!")

if __name__ == "__main__":
    test_dealer(sys.argv[1])
```

---

## 7. Post-Onboarding Checklist

### First 24 Hours

```
□ Verify auto-replies are firing (check Message table for outbound messages)
□ Verify rep notifications are going to the right WhatsApp numbers
□ Check response time metric on /dashboard/stats
□ Verify compliance consent text is correct
□ Test opt-out (send STOP, verify it works)
□ Confirm quiet hours are respected
```

### First Week

```
□ Monitor lead volume and response times
□ Check for any failed message deliveries (dashboard attention widget)
□ Verify inventory sync is working (if applicable)
□ Get feedback from the dealer on AI response quality
□ Adjust AI persona if needed
□ Adjust follow-up cadence if needed
```

### First Month

```
□ Review conversion metrics (leads → appointments → sales)
□ Compare speed-to-lead before/after implementation
□ Get testimonial / case study from the dealer
□ Identify any config tweaks needed
□ Plan for next dealer onboarding
```

---

## 8. Troubleshooting

### Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| No auto-reply | Twilio webhook not configured | Check Twilio console webhook URL |
| Auto-reply delayed | Free tier cold start | Upgrade to Starter ($7/mo) |
| Wrong rep notified | Round-robin pointer stale | Check dealer.round_robin_pointer in DB |
| WhatsApp not working | Sandbox not joined | Re-join sandbox from the rep's phone |
| Form submission fails | Invalid web_form_token | Check token in YAML matches URL |
| Consent text wrong | Template variable not replaced | Check consent_text in YAML |
| Leads not appearing | dealer_id mismatch | Verify sms_number matches in Dealer table |
| Scheduler not running | App restarted during free tier sleep | Upgrade to Starter (24/7) |

---

*Last updated: 2026-06-06*
