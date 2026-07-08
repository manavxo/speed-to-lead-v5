# WhatsApp Implementation Guide for Speed to Lead v4

**Purpose:** This document tells you everything needed to activate WhatsApp for a paying dealer. The code already supports it — you just need to configure Twilio and update the dealer YAML.

---

## Current State (SMS-Only)

Right now, all features work via SMS:
- **Customer auto-reply** → SMS (via Twilio Canadian number)
- **Rep claim pings** → SMS (reply 1 to claim, 2 to pass)
- **Escalation notifications** → SMS (to manager)
- **Follow-up messages** → SMS (AI-generated, timed cadence)
- **Daily digest** → SMS (to manager)
- **Opt-out/resubscribe** → SMS (STOP/START keywords)

WhatsApp is **preserved in the code** but dormant. The `send_whatsapp()` function exists in `tools/send_sms.py`. The WhatsApp webhook exists in `app/main.py` at `/webhook/twilio/whatsapp`. The `whatsapp_sender` field exists on the Dealer model and in the YAML config schema.

---

## What WhatsApp Adds

When activated, WhatsApp becomes the **rep-facing channel**:
- **Rep claim pings** → WhatsApp (instead of SMS)
- **Claim/pass replies (1/2)** → WhatsApp webhook (instead of SMS webhook)
- **Escalation notifications** → WhatsApp (instead of SMS)
- **Manager notifications** → WhatsApp (instead of SMS)

Customer-facing messages (auto-reply, follow-ups) stay on SMS. The split is:
- **SMS = customer-facing** (leads get texts)
- **WhatsApp = rep-facing** (sales staff get pings on WhatsApp)

---

## Prerequisites

### 1. Twilio WhatsApp Business Account

You need a **Twilio WhatsApp Business API sender**. This is NOT the same as the sandbox.

**Steps:**
1. Go to [Twilio Console → Messaging → Senders → WhatsApp senders](https://console.twilio.com/us1/develop/sms/senders/whatsapp-senders)
2. Click "New WhatsApp Sender"
3. You need:
   - A **dedicated phone number** (not the sandbox). Can be a Twilio number or your own.
   - A **Facebook Business Manager account** (verified)
   - A **WhatsApp Business Account** (linked to your Facebook Business Manager)
4. Submit for approval (takes 1-3 business days)
5. Once approved, you get a WhatsApp sender like `+14155238886` (or whatever number you registered)

**Cost:** ~$0.005 per WhatsApp message (inbound and outbound). Much cheaper than SMS for rep notifications.

### 2. Facebook Business Verification

If you don't have a verified Facebook Business Manager:
1. Go to [business.facebook.com](https://business.facebook.com)
2. Create a Business Manager account
3. Submit business verification documents (business license, utility bill, etc.)
4. Approval takes 1-5 business days

### 3. WhatsApp Business API Access

Twilio handles the API layer. You just need:
- The WhatsApp sender phone number (from step 1)
- Twilio Account SID and Auth Token (already have these)
- The sender must be registered and approved on Twilio

---

## Configuration Steps

### Step 1: Update the Dealer YAML

In `dealers/<slug>.yaml`, add the WhatsApp sender to channels:

```yaml
channels:
  sms_number: "+177****3122"       # 778 BC local number (customer-facing + rep-facing via SMS)
  whatsapp_sender: "+14155238886"  # NEW: WhatsApp sender (rep-facing)
  web_form_token: "premier-auto-45c531"
```

### Step 2: Update Sales Team Phone Numbers

Make sure each rep's phone number is registered on WhatsApp. The `phone` field is used for both SMS and WhatsApp — the system routes based on the channel.

```yaml
sales_team:
  - name: "Manav"
    phone: "+16041232870"    # must be on WhatsApp
    active: true
  - name: "Jagdeep"
    phone: "+16045551111"    # must be on WhatsApp
    active: true
```

### Step 3: Configure Twilio Webhook

In the Twilio Console, configure the WhatsApp sender's webhook:
1. Go to [Twilio Console → Messaging → Senders → WhatsApp senders](https://console.twilio.com/us1/develop/sms/senders/whatsapp-senders)
2. Click on your approved sender
3. Set the **Inbound Message Webhook URL** to:
   ```
   https://speed-to-lead-8tfi.onrender.com/webhook/twilio/whatsapp
   ```
4. Set the **Status Callback URL** to:
   ```
   https://speed-to-lead-8tfi.onrender.com/webhook/twilio/status
   ```

### Step 4: (Optional) Update the Scheduler for WhatsApp Rep Notifications

If you want the escalation sweep and daily digest to send via WhatsApp instead of SMS, you need to modify `app/scheduler.py`. Currently both use `send_sms()`. To switch:

**In `_run_escalation_sweep()` (line ~70-94):**
```python
# Change this:
from tools.send_sms import send_sms
send_sms(...)

# To this:
from tools.send_sms import send_whatsapp
send_whatsapp(
    to=rep["phone"],
    body=manager_msg,
    from_number=whatsapp_sender,
    session=session,
    role="MANAGER",
)
```

**In `_run_daily_digest()` (line ~490-500):**
```python
# Change this:
from tools.send_sms import send_sms as _send_sms
_send_sms(...)

# To this:
from tools.send_sms import send_whatsapp as _send_wa
_send_wa(
    to=manager_phone,
    body=body,
    from_number=whatsapp_sender,
    session=session,
    role="MANAGER",
)
```

**NOTE:** You only need this if you want rep notifications on WhatsApp. The current SMS approach works fine for small teams (2-3 reps). WhatsApp is better for larger teams or reps who prefer WhatsApp.

### Step 5: Deploy

```bash
cd "/c/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v4"
git add -A
git commit -m "feat: enable WhatsApp rep notifications for <dealer-slug>"
git push origin master
# Render auto-deploys
```

---

## How the Code Routes Messages

The routing logic is already built:

| Message | Channel | Direction | Handler |
|---------|---------|-----------|---------|
| Customer form submission | SMS | Outbound | `tools/send_sms.py::send_sms()` |
| Customer SMS reply | SMS | Inbound | `app/main.py::webhook_twilio_sms()` |
| Rep claim ping | SMS **or WhatsApp** | Outbound | `app/engine/router.py::assign_lead()` |
| Rep claim/pass reply (1/2) | SMS **or WhatsApp** | Inbound | SMS webhook or WhatsApp webhook |
| Escalation notification | SMS **or WhatsApp** | Outbound | `app/engine/escalation.py::on_claim_timeout()` |
| Follow-up message | SMS | Outbound | `app/scheduler.py::_handle_followup()` |
| Daily digest | SMS **or WhatsApp** | Outbound | `app/scheduler.py::_run_daily_digest()` |

The code checks `dealer_config.get("channels", {}).get("whatsapp_sender")` to decide whether to use WhatsApp. If it's `None` or empty, it falls back to SMS.

---

## Testing WhatsApp

### Sandbox Testing (Free)

For quick testing before getting a real WhatsApp Business sender:

1. Go to [Twilio Console → Messaging → Try it out → Send a WhatsApp message](https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn)
2. Join the sandbox by sending the join code (e.g., "hello-h") to +14155238886
3. Set the sandbox webhook to your Render URL
4. Update the dealer YAML with `whatsapp_sender: "+14155238886"`
5. Test claim/ping flow

**Limitations:**
- Sandbox is shared (other people can see messages if they join the same sandbox)
- Only works for numbers that have joined the sandbox
- Not suitable for production

### Production Testing

Once you have an approved WhatsApp sender:
1. Update the YAML with the real sender number
2. Deploy
3. Submit a test lead via the web form
4. Verify the rep gets a WhatsApp message with claim instructions
5. Reply "1" to claim — verify the lead transitions to CLAIMED
6. Reply "2" to pass — verify the lead moves to the next rep

---

## Cost Comparison

| Channel | Per Message | Monthly (100 leads) | Notes |
|---------|------------|---------------------|-------|
| SMS (Canada) | ~$0.0075 | ~$0.75 | Customer-facing |
| WhatsApp | ~$0.005 | ~$0.50 | Rep-facing only |
| **Total** | | ~$1.25 | Plus Twilio number rental ($2/mo) |

WhatsApp is cheaper per message but requires Facebook Business verification. SMS works immediately.

---

## Troubleshooting

### "No dealer found for WhatsApp to=..."
- Check that `channels.whatsapp_sender` in the YAML matches the Twilio WhatsApp sender exactly (E.164 format, e.g., `+14155238886`)

### Reps not getting WhatsApp messages
- Verify the rep's phone number is on WhatsApp
- Check Twilio logs at [console.twilio.com → Monitor → Logs → Messaging](https://console.twilio.com/us1/monitor/logs/messaging)
- Verify the webhook URL is correct and accessible

### "WhatsApp send failed" in logs
- Check that the WhatsApp sender is approved and active in Twilio
- Verify the rep's phone number format (must be E.164, e.g., `+16041232870`)
- Check Twilio error codes in the logs

### Fallback to SMS
If WhatsApp fails for any reason, the system does NOT automatically fall back to SMS. You would need to add fallback logic if desired. The current design is: if `whatsapp_sender` is configured, use WhatsApp; otherwise use SMS.

---

## What's Already Built (No Code Changes Needed)

These features are ready to use once WhatsApp is configured:

- ✅ `send_whatsapp()` function in `tools/send_sms.py` (lines 316-381)
- ✅ WhatsApp webhook at `/webhook/twilio/whatsapp` in `app/main.py` (lines 646-742)
- ✅ WhatsApp sender field on Dealer model (`whatsapp_sender` column)
- ✅ WhatsApp sender field in YAML config schema (`channels.whatsapp_sender`)
- ✅ Rep detection in WhatsApp webhook (matches by phone number)
- ✅ Claim/pass handling via WhatsApp (reply 1 or 2)
- ✅ Auto-provisioning reads `whatsapp_sender` from YAML
- ✅ `send_whatsapp()` uses Twilio Content API for template-based messages

## What Needs Manual Change When Activating

1. **Dealer YAML:** Add `whatsapp_sender` to `channels`
2. **Twilio Console:** Configure WhatsApp webhook URL
3. **Optional:** Switch scheduler jobs from `send_sms` to `send_whatsapp` for rep notifications
4. **Optional:** Update test fixtures if you want tests to cover WhatsApp path

---

## Summary

**To activate WhatsApp for a dealer, you need:**
1. A Twilio WhatsApp Business sender (approved)
2. The sender's phone number in the dealer YAML under `channels.whatsapp_sender`
3. The Twilio webhook pointing to your Render server
4. Reps with WhatsApp-capable phone numbers

**Everything else is already built.** The code detects the WhatsApp sender and routes accordingly. No core logic changes needed.
