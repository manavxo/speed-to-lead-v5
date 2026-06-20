# Call Detection & Missed-Call SMS Follow-Up

## Overview

When a customer calls a dealer and nobody answers, our system detects the missed call and triggers an SMS follow-up conversation powered by the AI agent.

**Key principle:** The AI does NOT answer calls. It only detects missed calls and initiates SMS conversations.

## Detection Options

Three options exist. Per-dealer deployment picks the right combo based on their situation.

### Option A: Always-On Call Forwarding (Primary)

**How it works:**
- Dealer forwards their business number to our Twilio number 24/7
- All calls route through Twilio
- During business hours: Twilio forwards to dealer's phone (sales staff answers)
- After hours or no-answer: Twilio fires webhook → we trigger SMS follow-up

**Setup:**
1. We provision a Twilio number for the dealer
2. Dealer activates call forwarding: `*72` + our Twilio number (carrier-specific)
3. Twilio is configured to forward incoming calls to dealer's cell/landline
4. If no answer after X rings → Twilio fires `/webhook/twilio/voice` → we send SMS

**Pros:** Simplest setup, works on landlines, we see every call
**Cons:** Dealer loses direct voicemail (or we configure Twilio voicemail)

**Best for:** Dealers willing to forward calls, new dealers onboarding

### Option B: Time-Based Call Forwarding

**How it works:**
- Dealer forwards to our Twilio number ONLY during off-hours
- During business hours: calls go directly to dealer's phone (no forwarding)
- After hours: forwarding activates → Twilio catches missed calls → SMS follow-up

**Setup:**
1. We provision a Twilio number for the dealer
2. Dealer sets up conditional forwarding (carrier-specific):
   - Most carriers support "forward when busy/no-answer" (`*71` + number)
   - Some support time-based forwarding via carrier portal
3. Twilio configured same as Option A

**Pros:** Dealer keeps normal business-hours call flow
**Cons:** More complex setup, carrier-dependent, harder to test

**Best for:** Dealers who want to keep their daytime call flow unchanged

### Option C: Carrier Voicemail Notification (Backup)

**How it works:**
- No forwarding at all. Dealer keeps everything as-is.
- When customer leaves voicemail, carrier sends email/SMS notification
- We parse the notification → extract caller number → trigger SMS follow-up

**Setup:**
1. Dealer enables voicemail-to-email on their carrier account
2. Emails forward to our parsing endpoint
3. We extract caller phone number from email body
4. Trigger SMS follow-up via our pipeline

**Pros:** Zero friction for dealer, no call forwarding needed
**Cons:** Fragile (carrier-specific email formats), delayed, misses hang-ups who don't leave voicemail

**Best for:** Backup only, dealers who refuse forwarding

## Decision Matrix

| Dealer Situation | Recommended Combo |
|---|---|
| New dealer, willing to forward | Option A (always-on) |
| Existing dealer, wants to keep daytime flow | Option B (time-based) |
| Dealer refuses any forwarding | Option C (voicemail notification) |
| High-volume dealer | Option A + B (always-on with business-hours fallback) |

## Technical Implementation

### Twilio Configuration

For Options A and B, the Twilio number needs:
- Voice webhook: `POST https://your-domain.com/webhook/twilio/voice`
- Status callback: `POST https://your-domain.com/webhook/twilio/status`
- Ring timeout: 20-30 seconds (configurable)
- Fallback URL: None (we want the webhook to fire on no-answer)

### Webhook Payload

Twilio sends these fields on call completion:
```
CallSid: unique call ID
From: caller's phone number
To: dealer's Twilio number
CallStatus: completed|no-answer|busy|failed|canceled
CallDuration: seconds (0 for no-answer)
```

### Our Response

On `CallStatus` in `(no-answer, busy, failed)`:
1. Look up dealer by `To` number
2. Create Lead (source=PHONE, state=NEW)
3. Send SMS text-back via Twilio
4. Log Message row
5. Transition lead to AUTO_REPLIED

### Dealer YAML Config

```yaml
channels:
  voice_number: "+141****8886"  # Twilio number for call forwarding
  call_detection: "always_on"   # always_on | time_based | voicemail_notify
  ring_timeout_sec: 25          # how long to ring before no-answer
```

## Testing

For development/testing:
- Use Twilio sandbox number as the dealer's voice number
- Simulate missed calls by calling the sandbox and not answering
- Verify webhook fires and SMS follow-up is sent
- Cost: FREE (sandbox) or ~$0.005/call (production)

## Cost

- Twilio number: ~$1/month
- Incoming call: ~$0.0085/min
- SMS follow-up: ~$0.0079/msg (SMS) or ~$0.005/msg (WhatsApp)
- Total per missed call: ~$0.02-0.03

## Phase Provisions

This document describes the architecture. Actual implementation:
- `app/main.py`: `/webhook/twilio/voice` handler
- `tools/detect_missed_call.py`: Call detection logic (NEW)
- `tools/notify_rep.py`: Rep notification on missed call (REUSE)
- `dealers/*.yaml`: `voice_number` and `call_detection` config
