# Twilio SMS Fix — Handoff for Hermes

**Date:** 2026-06-21
**Service:** Speed to Lead v5 (Render `srv-d8misim7r5hc739rf7sg`)
**Status:** ✅ RESOLVED — SMS sending verified end-to-end (test message delivered)

---

## Symptom
Outbound SMS was failing. The AI auto-reply pipeline ran, but every Twilio
send returned **HTTP 401 Unauthorized**, so no customer ever received a text.

## Root Cause
The `TWILIO_AUTH_TOKEN` set on Render did **not** match the `TWILIO_ACCOUNT_SID`.
They were not a valid key pair. The SID was correct; the token on Render was stale.

- Stale token on Render: `kwQT7RDRBQCCPJ5zbrNRVZTjmhFpG9Vr`  → 401
- Correct token (found in repo `.env.local` / `.env`): matches SID → 200

> Lesson for next time: before assuming the Twilio console is needed, test the
> credentials directly. A correct pair often already exists in the local `.env`.

## Diagnostic (how to confirm auth is healthy)
```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  "https://api.twilio.com/2010-04-01/Accounts/<ACCOUNT_SID>.json" \
  -u "<ACCOUNT_SID>:<AUTH_TOKEN>"
# 200 = pair is valid, 401 = mismatched pair
```

## Fix Applied (Render env vars only — no code changed)
Updated via Render API (per-key PUT, which updates one var safely rather than
replacing the whole set):

| Env Var | New Value |
|---|---|
| `TWILIO_AUTH_TOKEN` | correct token from repo `.env.local` (matches SID) |
| `TWILIO_PHONE_NUMBER` | `+17787623122` |
| `TWILIO_ACCOUNT_SID` | `${TWILIO_ACCOUNT_SID}` (already correct, unchanged) |

```bash
curl -s -X PUT \
  "https://api.render.com/v1/services/srv-d8misim7r5hc739rf7sg/env-vars/TWILIO_AUTH_TOKEN" \
  -H "Authorization: Bearer <RENDER_API_KEY>" \
  -H "Content-Type: application/json" \
  --data-raw '{"value":"<TOKEN>"}'
```
Then trigger a deploy so the new env vars load:
```bash
curl -s -X POST \
  "https://api.render.com/v1/services/srv-d8misim7r5hc739rf7sg/deploys" \
  -H "Authorization: Bearer <RENDER_API_KEY>" -d '{}'
```

## Phone Number Config (IMPORTANT)
- **Customer-facing / AI-engine sender: `+17787623122`** (area code 778 = British
  Columbia). This is the number to use for all customer + AI SMS interactions.
- The account also owns `+12097972694` (US 209), but it is **not** the
  customer-facing sender. Both numbers are SMS- and voice-capable.

## Verification (all green)
- Twilio auth check: `200`
- Test SMS from `+17787623122`: delivered (Twilio status `delivered`, no error)
- Render deploy: `live`
- Landing page `https://speed-to-lead-v5.onrender.com/`: `200`

## Constraints / Conventions for Hermes
- **Never hardcode customer phone numbers.** Customers submit their info via the
  lead form once; always read the recipient number from the lead record at
  runtime. Hardcoded literals are only OK in throwaway operator-test pings.
- Secrets (auth token, Render API key) live in Render env vars and the local
  `.env` files — do not paste them into committed docs.
- This fix touched **only Render env vars** — no Python/HTML/YAML/config edits.
