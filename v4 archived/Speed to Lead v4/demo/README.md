# Demo — Real-World Testing Package

This folder contains everything needed to run a live end-to-end test of the Speed-to-Lead system with real phones.

## What's in here

| File | Purpose |
|------|---------|
| `dealers/test-drive-motors.yaml` | Dealer config — fill in real phone numbers for your test sales team |
| `inventory.csv` | 20 vehicles (Honda, Ford, Toyota, Tesla, BMW, etc.) |
| `website/index.html` | Full dealership website — open in browser, send to friends |

## How to run a live test

### 1. Set up Twilio (one-time)

1. Create a Twilio account → [twilio.com](https://www.twilio.com)
2. Buy a **Canadian** SMS-capable number (~$1.15/month)
3. Enable WhatsApp sandbox (free) for testing, or set up WhatsApp Business sender
4. Copy the Account SID + Auth Token → paste into Render env vars (service → Environment tab)

### 2. Fill in real phone numbers

Edit `demo/dealers/test-drive-motors.yaml`:

```yaml
channels:
  sms_number: "+1778XXXXXXX"      # Your Twilio number (lead-facing)
  whatsapp_sender: "+1778XXXXXXX" # Your Twilio WhatsApp sender

sales_team:
  - { name: "YourName",   whatsapp: "+1604XXXXXXX", active: true }   # Your phone
  - { name: "Friend1",    whatsapp: "+1778XXXXXXX", active: true }   # Friend's phone
  - { name: "Friend2",    whatsapp: "+1XXX XXX XXXX", active: true } # Friend's phone

routing:
  manager_phone: "+1604XXXXXXX"   # Your phone (escalation alerts)
```

### 3. Provision the dealer

```bash
python tools/provision_dealer.py demo/dealers/test-drive-motors.yaml
```

This validates the config, provisions the Twilio number link, and runs the first inventory sync.

### 4. Configure Twilio webhooks

In the Twilio console, set these webhook URLs (replace with your Render URL):

| Setting | URL |
|---------|-----|
| **SMS webhook** (Phone Numbers → your number → Messaging) | `https://YOUR-APP.onrender.com/webhook/twilio/sms` |
| **Voice webhook** (Phone Numbers → your number → Voice) | `https://YOUR-APP.onrender.com/webhook/twilio/voice` |
| **WhatsApp sender** (Messaging → WhatsApp Senders) | `https://YOUR-APP.onrender.com/webhook/twilio/whatsapp` |

### 5. Update the website webhook URL

In `demo/website/index.html`, change line ~250:

```javascript
const WEBHOOK_BASE = "https://YOUR-APP.onrender.com/webhook/form/tdm-test-token-2026";
```

### 6. Open the website & test

1. Open `demo/website/index.html` in your browser (or serve it locally with `python -m http.server 9000` from the `demo/website/` directory)
2. Send the URL to your friends
3. They browse cars → click "Get a Quote" → fill the form
4. **Watch what happens:**
   - Auto-reply SMS arrives on the lead's phone within seconds
   - Round-robin WhatsApp ping goes to the next sales rep
   - Rep replies `1` to claim → lead moves to CLAIMED state
   - If no claim within 5 min → escalation to the next rep, then to manager

### Test scenarios to try

| Scenario | What to do | Expected result |
|----------|-----------|-----------------|
| **Happy path** | Fill form with real phone, consent checked | Instant SMS auto-reply, WhatsApp ping to first rep |
| **Round-robin** | Submit 3 leads in a row | Rep 1 gets first ping, Rep 2 gets second, Rep 3 gets third |
| **Claim** | Rep replies `1` via WhatsApp | "Lead claimed!" confirmation, lead moves to CLAIMED |
| **Pass** | Rep replies `2` via WhatsApp | Lead passes to next rep in rotation |
| **Opt-out** | Send `STOP` to the Twilio number | "You have been unsubscribed" reply, lead → OPTED_OUT |
| **Missed call** | Call the Twilio number, don't answer | Text-back: "Hi! We missed your call to Test Drive Motors..." |
| **Escalation** | Don't claim a lead for 5 minutes | Manager gets notified, lead escalates |
| **After-hours** | Submit a lead outside business hours | AI is fully autonomous — qualifies and books without rep |
| **Dashboard** | Visit `https://YOUR-APP.onrender.com/dashboard/leads` | See all leads, their states, messages, timeline |

### Running the website locally

```bash
cd demo/website
python -m http.server 9000
```

Then open http://localhost:9000 in your browser.

For the webhook to work, update `WEBHOOK_BASE` in the HTML to point at your Render deployment URL.
