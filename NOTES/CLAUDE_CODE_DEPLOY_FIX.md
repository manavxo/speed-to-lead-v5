# Speed to Lead v5 — Fix Twilio SMS + Send Test Message

## The Problem
Speed to Lead v5 is deployed and the pipeline works (lead creation, AI conversation, everything), but **Twilio SMS is not sending**. The Twilio credentials on Render are mismatched — the Account SID and Auth Token don't belong to the same key pair, causing 401 authentication errors.

The **browser is required** to log into the Twilio console, grab the correct matching credentials, then update Render via API, deploy, and test.

## What We're Building
Speed to Lead v5 is a dealership lead response system:
- **Customer** submits a form on the website
- **AI** auto-replies via SMS within 60 seconds (THIS IS BROKEN)
- **AI** qualifies the customer through SMS conversation
- **AI** books a test drive appointment
- **Rep** gets Telegram notification
- **Manager** sees everything in the dashboard

The missing piece: Twilio credentials need to be a matching pair so the system can actually send SMS messages.

## What You Need To Do

### Step 1: Open Twilio Console in Browser
- Navigate to https://console.twilio.com
- Ask the user to log in if needed (they'll provide 2FA codes if required)
- Once logged in, look at the main Dashboard page
- Find **Account SID** (starts with AC...) and **Auth Token** (long hex string) at the top right
- **CRITICAL:** These two values MUST come from the same account on the same page. Copy both.

### Step 2: Update Render Environment Variables
Use the Render API to update the three Twilio env vars:

```
Service ID: srv-d8misim7r5hc739rf7sg
API Key: ***REMOVED-RENDER-API-KEY***
```

For each variable, make a PATCH request:
```bash
curl -s -X PATCH "https://api.render.com/v1/services/srv-d8misim7r5hc739rf7sg/env-vars" \
  -H "Authorization: Bearer ***REMOVED-RENDER-API-KEY***" \
  -H "Content-Type: application/json" \
  --data-raw '{"TWILIO_ACCOUNT_SID":"THE_AC_SID_FROM_CONSOLE"}'
```

Then:
```bash
curl -s -X PATCH "..." --data-raw '{"TWILIO_AUTH_TOKEN":"THE_TOKEN_FROM_CONSOLE"}'
```

Then:
```bash
curl -s -X PATCH "..." --data-raw '{"TWILIO_PHONE_NUMBER":"+12097972694"}'
```

### Step 3: Trigger Deploy
```bash
curl -s -X POST "https://api.render.com/v1/services/srv-d8misim7r5hc739rf7sg/deploys" \
  -H "Authorization: Bearer ***REMOVED-RENDER-API-KEY***" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Step 4: Wait for Deploy
Poll until status is "live":
```bash
curl -s "https://api.render.com/v1/services/srv-d8misim7r5hc739rf7sg/deploys?limit=1" \
  -H "Authorization: Bearer ***REMOVED-RENDER-API-KEY***"
```

### Step 5: Send Test SMS to Manav
Use the Twilio Python SDK to send a test message:

```python
from twilio.rest import Client
client = Client("AC_SID_FROM_CONSOLE", "AUTH_TOKEN_FROM_CONSOLE")
msg = client.messages.create(
    body="🚗 Speed to Lead v5 is LIVE! SMS pipeline verified.",
    from_="+12097972694",
    to="+16048392870"
)
print(f"Sent! SID: {msg.sid}, Status: {msg.status}")
```

### Step 6: Verify End-to-End
1. Open https://speed-to-lead-v5.onrender.com/ in the browser
2. The landing page should load (200 OK)
3. Submit the contact form with a test phone number
4. Confirm the webhook processes it

## Success Criteria
- Manav receives an SMS at +16048392870 saying the system is live
- The app is serving the landing page
- All 168 tests pass locally (`pytest tests/ -x`)

## Note to Claude Code
- Don't modify any Python, HTML, YAML, or configuration files
- This is purely about fixing Twilio credentials on Render
- The browser is for logging into Twilio console — everything else is via curl/API
- If the user needs to provide 2FA codes or login credentials, ask them clearly
- When done, print: "✅ SMS pipeline fixed. Manav should receive a test message at +16048392870"
