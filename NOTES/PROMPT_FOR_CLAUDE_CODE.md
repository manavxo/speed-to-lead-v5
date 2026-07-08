# Prompt for Claude Code: Verify Speed to Lead v5 Core Pipeline

## Mission
Verify that the core speed-to-lead pipeline works correctly — when a real customer submits a form on the Premier Auto Group landing page, they receive an immediate AI-generated SMS response from the local BC number (+17787623122).

## Architecture
- **Form endpoint**: POST `https://speed-to-lead-v5.onrender.com/webhook/form/premier-auto-group-token`
- **SMS sender**: +17787623122 (Twilio, 778 area code, BC local number)
- **AI engine**: DeepSeek V4 Flash via direct API (api.deepseek.com)
- **Pipeline flow**: Webform → ingest_lead → send auto-reply SMS → AI generates personalized follow-up → send AI SMS → mark lead ENGAGED

## What to verify (run each step)

### 1. Auth & Config Health
```bash
cd /c/Speed\ to\ Lead\ v5
RENDER_API_KEY=${RENDER_API_KEY} python skills/fix_twilio_sms_auth.py
```
Expected: Local pair 200, Render pair 200, Render PHONE_NUMBER = +17787623122

### 2. Landing Page is Live
```bash
curl -s -o /dev/null -w "%{http_code}" https://speed-to-lead-v5.onrender.com/
```
Expected: 200

### 3. Submit a Fresh Lead
Use a phone number that can receive SMS (use +16048392870 — Manav's number). Run this and check phone within 15 seconds:
```bash
curl -s -X POST "https://speed-to-lead-v5.onrender.com/webhook/form/premier-auto-group-token" \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Test Customer",
    "phone": "+16048392870",
    "email": "test@example.com",
    "consent": true,
    "vehicle_of_interest": "PAG005",
    "message": "Hi interested in the Tesla Model 3",
    "referrer": "premier-auto",
    "inquiry_type": "general"
  }'
```
Expected: `{"status":"ok","lead_id":<N>,"state":"ENGAGED","dealer":"premier-auto"}`

### 4. Check Twilio Logs for SMS Delivery
```bash
curl -s -u "${TWILIO_ACCOUNT_SID}:${TWILIO_AUTH_TOKEN}" \
  "https://api.twilio.com/2010-04-01/Accounts/${TWILIO_ACCOUNT_SID}/Messages.json?PageSize=5" \
  | python -c "import sys,json; data=json.load(sys.stdin); [print(f'From: {m[\"from\"]}  To: {m[\"to\"]}  Status: {m[\"status\"]}  Body: {m.get(\"body\",\"\")[:80]}') for m in data.get('messages',[])]"
```
Expected: Two SMS messages from `+17787623122` to the test number, both with status `delivered` or `sent`. The messages must NOT have a `whatsapp:` prefix.

### 5. Verify AI Generated a Personalized Response
The AI follow-up should be personalized to the customer's name and vehicle of interest. Check the body of the second message — it should mention the customer's name and the Tesla Model 3 or offer an alternative.

### 6. Simulate a Customer Reply
After the lead is created, send an inbound SMS reply via the Twilio webhook to simulate the customer responding:
```bash
curl -s -X POST "https://speed-to-lead-v5.onrender.com/webhook/twilio/sms" \
  -d "To=%2B17787623122&From=%2B16048392870&Body=What+do+you+have+that%27s+similar&MessageSid=TEST_$(date +%s)"
```
Expected: Returns TwiML (200). Then check Twilio logs again — should see an AI-generated SMS reply from +17787623122 to the customer.

### 7. Check Database State (optional)
Verify the lead exists in the DB with correct state:
```bash
curl -s "https://speed-to-lead-v5.onrender.com/debug/config"
```
(If debug endpoints are disabled, skip this step.)

## Critical Checks
- [ ] SMS comes from **+17787623122**, NOT +12097972694
- [ ] SMS is sent as **SMS** (no `whatsapp:` prefix in Twilio logs)
- [ ] AI response is **personalized** (mentions customer name, vehicle interest)
- [ ] Status is **delivered** or **sent**
- [ ] Response time is under **60 seconds** (ideally under 30)
- [ ] Reply-to SMS also works (customer can text back and get an AI response)

## If something fails
- **Auth fails**: Re-run `RENDER_API_KEY=... python skills/fix_twilio_sms_auth.py --apply` to sync creds
- **SMS shows whatsapp: prefix**: Check `tools/route_lead.py` line 76 — `_send_to_customer()` should default to `channel="sms"` for webform leads
- **No SMS arrives**: Check Twilio logs via the curl command above — look for error codes
- **AI not responding to replies**: Check `app/main.py` webhook handler for SMS background task

## After verification
Report the results in a concise table: what passed, what failed, and any issues found.
