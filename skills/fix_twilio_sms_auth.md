# Skill: Fix Twilio SMS Auth (401 / credential mismatch)

## Purpose
Restore outbound SMS when Twilio sends fail with **HTTP 401 Unauthorized**. The
usual cause: the `TWILIO_AUTH_TOKEN` on Render does not match
`TWILIO_ACCOUNT_SID` (they are not a valid key pair). A correct pair is almost
always already sitting in the repo's `.env.local`.

## When to run this skill
- Outbound SMS / AI auto-replies stop sending
- Render logs show `401` / `Authenticate` errors from Twilio
- After rotating the Twilio auth token
- After someone edits Twilio env vars on Render

---

## Constants

| Variable | Value |
|---|---|
| Render service id | `srv-d8misim7r5hc739rf7sg` |
| Customer/AI sender (BC) | `+17787623122` (area code 778 = British Columbia) |
| Secondary number (not sender) | `+12097972694` (US 209) |
| Account SID | `AC9c402b4729de1e43469b7d21f3eeb58a` |
| Local creds | `<repo>/.env.local` (never commit) |
| Landing page | `https://speed-to-lead-v5.onrender.com/` |
| Script | `skills/fix_twilio_sms_auth.py` |

Secrets are NOT in this file. The script reads Twilio creds from `.env.local`
and the Render API key from the `RENDER_API_KEY` env var.

---

## Execution steps

### Step 1 — Diagnose (always safe, mutates nothing)
```bash
export RENDER_API_KEY=<render_api_key>
python skills/fix_twilio_sms_auth.py
```
Reads the local pair and (if `RENDER_API_KEY` is set) the Render pair, tests both
against Twilio, and prints `200` (valid) or `401` (mismatch) for each.

**Decision gate — read the output:**
| Local pair | Render pair | Action |
|---|---|---|
| 200 | 401 | Local token works, Render is stale → **Step 2 (--apply)**. |
| 200 | 200 | Already healthy. Stop. (Maybe the issue is elsewhere.) |
| 401 | any | Local token is ALSO bad → **ESCALATE** (see below). Do not --apply. |

### Step 2 — Apply the fix (mutates Render, then deploys)
```bash
python skills/fix_twilio_sms_auth.py --apply
```
This refuses to run unless the local pair tests `200`, then PUTs
`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_PHONE_NUMBER` (the BC
number) to Render, triggers a deploy, and polls until `live`.

### Step 3 — Verify with a real SMS (recipient is a required argument)
```bash
python skills/fix_twilio_sms_auth.py --test-sms +1XXXXXXXXXX
```
Send to the **operator's own phone**, passed explicitly. Never hardcode a
recipient. The script waits for a terminal status and prints `delivered`.

### One-shot (fix + verify together)
```bash
python skills/fix_twilio_sms_auth.py --apply --test-sms +1XXXXXXXXXX
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Local pair returns 401 | `.env.local` token is also stale/wrong | ESCALATE — needs a fresh token from the Twilio console (a human/console step) |
| `RENDER_API_KEY env var not set` | Key not exported | `export RENDER_API_KEY=...` before `--apply` |
| Deploy never goes live | Build failure unrelated to Twilio | Check Render dashboard logs |
| SMS status `undelivered`/`failed` with error 21610/21408 | Number/region/opt-out issue, not auth | Read the printed Twilio error code — auth is fine, this is a messaging-policy problem |
| Auth 200 but still no customer texts | Webhook/routing issue, not creds | Different skill — check webhook + dealer config |

---

## Key facts Hermes needs to know
- **A 401 is an auth-pair problem, not a per-message problem.** The SID and token
  must come from the same account. Test the pair directly before touching Render.
- **The correct token is usually already in `.env.local`.** Check it before
  assuming a Twilio console trip is needed — that browser step is rarely required.
- **`+17787623122` (BC) is the customer/AI sender.** Do not switch to the 209
  number without a human decision.
- **`--apply` self-guards:** it will not push a pair that fails the `200` check.
- Diagnose mode is read-only and safe to run anytime.

---

## When to ESCALATE to the creative engine (Manav + Claude)
Hermes executes; it does **not** make these calls. Stop and escalate when:
- The local pair ALSO fails (401) — a new token must be obtained from the Twilio
  console (login/2FA = human), or the account itself may be the problem.
- The fix would **change which phone number** customers see, add/remove a number,
  or alter messaging behavior (templates, opt-in flow, regions).
- Diagnose shows auth is healthy (200) but SMS still isn't reaching customers —
  the root cause is elsewhere (webhook, routing, dealer config) and needs a
  judgment call about where to look next.
- Anything involves spending money, porting numbers, or A2P/10DLC registration.

> Rule of thumb: **mechanical + reversible + already-decided → Hermes runs it.
> Novel + outward-facing + a real choice → bring it to Manav and Claude.**

---

## Files
| File | Purpose |
|---|---|
| `skills/fix_twilio_sms_auth.py` | Automation (diagnose / apply / test-sms) |
| `.env.local` | Local Twilio creds (never commit) |
| `NOTES/HERMES_TWILIO_FIX.md` | Narrative record of the 2026-06-21 incident |
