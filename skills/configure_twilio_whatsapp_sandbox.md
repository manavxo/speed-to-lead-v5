# Skill: Configure Twilio WhatsApp Sandbox Webhook

## Purpose
Wire the Twilio WhatsApp sandbox (+14155238886) to the Speed to Lead v5 webhook endpoint so inbound WhatsApp messages reach the app.

## When to run this skill
- First-time setup of the sandbox
- After rotating TWILIO_AUTH_TOKEN
- After the Render service URL changes
- When WhatsApp messages stop arriving at the webhook

---

## Constants

| Variable | Value |
|---|---|
| Sandbox number | `+14155238886` |
| Webhook URL | `https://speed-to-lead-v5.onrender.com/webhook/twilio/whatsapp` |
| Credentials file | `C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5/.env.local` |
| Console URL | `https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn` |

---

## Execution steps

### Step 1 — Run the automated configurator
```
cd "C:/Users/manav.LAPTOP-TTEINC4O/Desktop/Speed to Lead v5"
python configure_twilio_sandbox.py
```

The script will:
1. Load creds from `.env.local`
2. Health-check `GET /webhook/twilio/whatsapp` → expects 405 (POST-only)
3. Send a Twilio-signed test POST → expects 200 or 400 (NOT 403)
4. Attempt auto-config via Twilio REST API (will gracefully skip if unsupported)
5. Print exact manual Console steps if auto-config fails

### Step 2 — One manual step in the Twilio Console (unavoidable)

**Why:** Twilio's WhatsApp Sandbox webhook is intentionally not exposed via REST API — it must be set in the Console sandbox settings page.

1. Open: `https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn`
2. Scroll to **Sandbox Configuration**
3. Set **"WHEN A MESSAGE COMES IN"** to:
   ```
   https://speed-to-lead-v5.onrender.com/webhook/twilio/whatsapp
   ```
   Method: **POST**
4. Click **Save**

### Step 3 — Verify
```
python configure_twilio_sandbox.py --verify-only
```

Expected output:
- `[OK]  Endpoint live — GET→405 (correct, POST-only webhook)`
- `[OK]  Endpoint accepted signed POST → 200` or `→ 400` (400 = no dealer matched yet, endpoint is working)

### Step 4 — Test end-to-end (optional)
Send a WhatsApp message to `+14155238886` from a phone that has joined the sandbox.
Check the Render logs for the incoming webhook call.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Signed test returns 403 | `TWILIO_AUTH_TOKEN` in `.env.local` doesn't match Render env var | Sync auth token on Render dashboard |
| Signed test returns 400 | No dealer has `whatsapp_sender = +14155238886` in their config | Add sandbox number to a dealer YAML under `channels.whatsapp_sender` |
| Health check returns 0 (unreachable) | Render service is sleeping | Visit `https://speed-to-lead-v5.onrender.com/healthz` to wake it |
| Messages not arriving after Console config | Wrong URL set in Console | Re-check and re-save the sandbox webhook URL |

---

## Key facts Hermes needs to know

- **The Twilio WhatsApp Sandbox webhook CANNOT be configured via the REST API.** This is a platform constraint, not a bug. The manual Console step is always required once.
- The webhook at `/webhook/twilio/whatsapp` validates `X-Twilio-Signature` — requests without a valid signature always return 403 by design.
- The dealer lookup in the webhook uses `whatsapp_sender` column — the sandbox number must appear in a dealer's config for messages to route correctly.
- `configure_twilio_sandbox.py --verify-only` is safe to run at any time (read-only, no side effects).

---

## Files

| File | Purpose |
|---|---|
| `configure_twilio_sandbox.py` | Main automation script (run this) |
| `app/main.py:869` | WhatsApp webhook handler |
| `app/main.py:327` | Twilio signature validation |
| `.env.local` | Local credentials (never commit) |
