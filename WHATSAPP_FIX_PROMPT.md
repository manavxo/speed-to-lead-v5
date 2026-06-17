# TASK: Fix WhatsApp message delivery — customer auto-reply not reaching phone

## The Problem
A webform lead is successfully created (lead_id=1, state=ASSIGNED, dealer=premier-auto) but the customer never receives a WhatsApp message on their phone (+16048392870).

Render logs show: `TwilioRestException: HTTP 400 error: Unable to create record: 'From' +17785550111 is not a Twilio phone number or Short Code country mismatch`

The number +17785550111 is the **fake SMS number** from the dealer config (`channels.sms_number`). It should NOT be used for WhatsApp — WhatsApp should use `channels.whatsapp_sender` which is +14155238886 (the real Twilio sandbox).

## Root Cause Analysis Needed
Something in the code path is using the wrong `from_number`. Trace these paths:

### Path 1: Webform → auto-reply (route_lead.py)
File: `tools/route_lead.py` lines 138-178
- Line 140: `whatsapp_sender = channels.get("whatsapp_sender", "")`
- Line 147: `if whatsapp_sender:` → should send via WhatsApp
- Line 151: calls `send_whatsapp(to=lead_data.phone, body=auto_text, from_number=whatsapp_sender, ...)`
- **This path looks correct on paper.** But verify the `dealer_config` dict being passed has the right channels.

### Path 2: WhatsApp inbound → AI reply (main.py)
File: `app/main.py` lines 718-824
- Function: `_handle_customer_whatsapp_test`
- Line 806: `whatsapp_sender = dealer_config.get("channels", {}).get("whatsapp_sender")`
- Line 809: calls `send_whatsapp(to_number=from_number, from_number=whatsapp_sender, ...)`
- **Check:** Is `dealer_config` the full YAML dict or something else?

### Path 3: Rep notification (notify_rep.py)
File: `tools/notify_rep.py` lines 305-336
- Line 307: `from_phone = dealer_config.get("channels", {}).get("whatsapp_sender", "")`
- This uses the correct sender BUT the rep phone numbers are fake (+16045550121 etc.)
- **Expected to fail** — not the customer-facing issue.

### Path 4: Transport adapter (app/transports/twilio.py)
File: `app/transports/twilio.py` — thin bridge
- Strips `whatsapp:` prefix, calls `tools.send_sms.send_whatsapp`
- **Check:** Does it pass `role="CUSTOMER"` for customer messages? Default is "REP".

### Path 5: send_whatsapp itself (tools/send_sms.py)
File: `tools/send_sms.py` lines 343-408
- Line 389: `to` → `f"whatsapp:{to}"` ✓
- Line 390: `from_` → `f"whatsapp:{from_number}"` ✓
- **Check:** Is `from_number` actually +14155238886 or is it getting +17785550111 somehow?

## Key Config (dealers/premier-auto.yaml)
```yaml
channels:
  sms_number: "+17785550111"        # FAKE — Twilio doesn't own this
  whatsapp_sender: "+14155238886"   # REAL — Twilio sandbox
  web_form_token: "premier-auto-group-token"
```

## Environment (Render)
- `OUTBOUND_ENABLED=true` (verified set)
- `SEED_SECRET=acb5b750776ddf40b213aba2504b2a81`
- Twilio sandbox joined by user at +16048392870 today

## What To Do

1. **Add diagnostic logging** to `send_whatsapp()` in `tools/send_sms.py` — log the exact `from_number` value at the top of the function (before any processing).

2. **Trace the webform path end-to-end**: Fire the webform locally or add logging at each step:
   - `route_lead.py:ingest_lead` → what is `dealer_config["channels"]`?
   - The `send_whatsapp` call → what `from_number` arrives?

3. **Check if the error is from rep notification, not customer auto-reply.** The 400 error about +17785550111 might be from `notify_rep.py` trying to send via SMS backend (line 325: `from_phone = dealer_config.get("channels", {}).get("sms_number", "")`). If so, the customer WhatsApp might actually be working — verify by checking if a WhatsApp message was sent BEFORE the SMS error.

4. **If the SMS rep notification is the only problem**, either:
   - Skip rep notification when numbers are fake (555 prefix)
   - Or make rep notification best-effort (catch and log, don't crash the pipeline)

5. **If the customer WhatsApp is actually broken**, check:
   - Is `OUTBOUND_ENABLED` actually `True` at runtime? (add a log line)
   - Is the `from_number` reaching `send_whatsapp` the sandbox number?
   - Is the Twilio sandbox still active? (user joined today at 2:34 PM)

6. **After fixing**, commit and push to main. Then fire this test:
   ```bash
   curl -X POST https://speed-to-lead-v5.onrender.com/webhook/form/premier-auto-group-token \
     -d "full_name=Test Lead" \
     -d "phone=+16048392870" \
     -d "consent_sms=true"
   ```
   User should receive WhatsApp message on +16048392870 within 30 seconds.

## Constraints
- Do NOT change the dealer YAML (sms_number is intentionally fake for demo)
- Do NOT disable rep notification entirely — just make it resilient to fake numbers
- The Twilio sandbox (+14155238886) is the only real number — all outbound WhatsApp must use it
- Push to `origin/main` (auto-deploys to Render)
- Use `git diff` after changes to verify before pushing
