# Deployment — Render.com

## Step-by-Step Deploy

### 1. Create Render Account

Go to [render.com](https://render.com) and sign up (GitHub login recommended).

### 2. Create Postgres Database

1. Dashboard → New → PostgreSQL
2. Name: `speed-to-lead-db`
3. Plan: Free (for testing) or $7/mo (for production)
4. Region: Oregon (closest to BC)
5. Click "Create Database"
6. Copy the **Internal Database URL** (looks like `postgresql://...`)

### 3. Create Web Service

1. Dashboard → New → Web Service
2. Connect your GitHub repo (`speed-to-lead-v4`)
3. Settings:
   - **Name:** `speed-to-lead`
   - **Region:** Oregon
   - **Runtime:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `./start.sh`
   - **Plan:** Hobby ($7/mo) for testing, Standard ($25/mo) for production

### 4. Set Environment Variables

In the Render dashboard → your web service → Environment:

| Variable                  | Value                                | Notes                           |
| ------------------------- | ------------------------------------ | ------------------------------- |
| `DATABASE_URL`            | *(link from Postgres service)*       | Use "Internal Database URL"     |
| `TWILIO_ACCOUNT_SID`      | `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` | From Twilio console             |
| `TWILIO_AUTH_TOKEN`        | `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`   | From Twilio console             |
| `OPENROUTER_API_KEY`      | `sk-or-xxxxxxxxxxxx`                 | From openrouter.ai              |
| `OPENROUTER_MODEL`        | `google/gemini-2.0-flash-001`        | Default, change if needed       |
| `PUBLIC_BASE_URL`         | `https://speed-to-lead.onrender.com` | Your Render URL                 |
| `OUTBOUND_ENABLED`        | `false`                              | **Keep false until Twilio verified** |
| `REQUIRE_TWILIO_SIGNATURE` | `false`                             | Enable in production            |
| `MESSAGE_TAGS_ENABLED`    | `false`                              | Staging only, OFF in production |
| `ENVIRONMENT`             | `production`                         |                                 |

### 5. Deploy

Push to GitHub. Render auto-deploys from the connected branch.

```bash
git add .
git commit -m "deploy to render"
git push origin main
```

Render will build and deploy automatically. Check the deploy logs for errors.

---

## How to Flip OUTBOUND_ENABLED

**Safety gate:** No real SMS sends until this is `true`.

### Pre-requisites before flipping:
1. Twilio account is set up with a Canadian SMS number
2. `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` are set in Render env vars
3. The dealer's `sms_number` is configured in their YAML config
4. You've tested with `OUTBOUND_ENABLED=false` and verified DRYRUN SIDs appear in logs

### To enable:
1. Render dashboard → your web service → Environment
2. Find `OUTBOUND_ENABLED`
3. Change from `false` to `true`
4. Save (triggers a redeploy)

### To verify it's working:
1. Check Render logs for `Auto-reply sent for lead#X sid=SM...` (real SID, not DRYRUN)
2. Check Twilio console → Messaging → Logs for sent messages
3. Send a test SMS to the dealer's number and verify the auto-reply arrives

### Emergency disable:
Change `OUTBOUND_ENABLED` back to `false` in Render environment. Redeploy. All sends stop immediately.

---

## Environment Variables Reference

```bash
# .env.example — copy to .env for local development

# Database
DATABASE_URL=postgresql+psycopg://localhost/speedtolead

# Twilio
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=

# OpenRouter (AI)
OPENROUTER_API_KEY=
OPENROUTER_MODEL=google/gemini-2.0-flash-001
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# App
PUBLIC_BASE_URL=http://localhost:8000
ENVIRONMENT=development

# Safety gates
OUTBOUND_ENABLED=false
REQUIRE_TWILIO_SIGNATURE=false
MESSAGE_TAGS_ENABLED=false
```

---

## start.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

# Normalize Render's DATABASE_URL to psycopg3 format if needed
export DATABASE_URL="${DATABASE_URL/postgresql:/postgresql+psycopg:}"

echo "Starting Speed to Lead..."
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
```

---

## render.yaml

```yaml
services:
  - type: web
    name: speed-to-lead
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: ./start.sh
    healthCheckPath: /healthz
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: speed-to-lead-db
          property: connectionString
      - key: OUTBOUND_ENABLED
        value: "false"
      - key: ENVIRONMENT
        value: "production"
    plan: hobby

databases:
  - name: speed-to-lead-db
    plan: free
    databaseName: speedtolead
```

---

## Post-Deploy Checklist

After every deploy, verify:

```
[ ] 1. GET /healthz returns {"ok": true}
[ ] 2. GET /readyz returns {"ok": true, "db": "connected"}
[ ] 3. GET /dashboard loads (should redirect to /dashboard/leads)
[ ] 4. Render logs show no errors on startup
[ ] 5. OUTBOUND_ENABLED is "false" (check logs for DRYRUN messages)
```

When going live with a real dealer:

```
[ ] 6. Twilio creds are set and verified
[ ] 7. Canadian SMS number is provisioned
[ ] 8. OUTBOUND_ENABLED is flipped to "true"
[ ] 9. Send test SMS to dealer number → verify auto-reply arrives
[ ] 10. Send test SMS from lead's phone → verify lead appears in dashboard
[ ] 11. Rep receives WhatsApp claim ping
[ ] 12. Rep replies "1" → lead transitions to CLAIMED
[ ] 13. Opt-out test: send "STOP" → verify lead goes to OPTED_OUT
[ ] 14. Check Twilio delivery status callbacks are working (Message rows have delivery_status)
[ ] 15. Verify quiet hours: send during quiet window → no outbound
```

---

## Database Schema Drift — The Silent Killer

### What happened (June 2026)

After pushing new code that added columns to the `Lead` model (`assigned_rep`, `pass_count`,
`consent`, `vehicle_id`) and `Dealer` model (`sms_number`, `whatsapp_sender`, `web_form_token`,
`config`), the dashboard returned 500 on every page that queried leads.

**Root cause:** The Render Postgres DB was created by an earlier deploy using `init_db()`
(SQLModel's `create_all`). When the new code was pushed:
- `create_all` does NOT alter existing tables — it only creates tables that don't exist
- Alembic's initial `CREATE TABLE` failed because tables already existed
- The startup script caught the error silently (`|| echo "WARNING"`)

So the DB was stuck with the old schema while the code expected new columns.
SQLAlchemy threw `f405` ("column does not exist") on every query.

### The fix (in start.sh)

Before Alembic runs, `start.sh` now executes a Python script that:
1. Connects to Postgres directly using `DATABASE_URL`
2. Queries `information_schema.columns` to see what actually exists
3. Runs `ALTER TABLE ADD COLUMN` for every missing column
4. This is idempotent — safe to run on every deploy

### How to diagnose if this happens again

**Symptom:** Dashboard shows "Internal Server Error" but `/healthz` and `/readyz` work.

**Steps:**
1. Check Render logs for `sqlalche.me/e/20/f405` — this means "column does not exist"
2. The log before it should show `Existing lead columns: [...]` — compare with the model
3. If the column is missing, the `ALTER TABLE` in `start.sh` either didn't run or didn't cover it

**To add a new column safely:**
1. Add it to the SQLAlchemy/SQLModel model in `app/models/__init__.py`
2. Add it to the `additions` dict in `start.sh` (with its SQL type and default)
3. Generate an Alembic migration: `alembic revision --autogenerate -m "add X column"`
4. Push — `start.sh` handles both the SQL fixup and the migration

**Nuclear option (if schema is too far gone):**
1. Go to Render Dashboard → PostgreSQL → speed-to-lead-db → Info
2. Copy the Internal Database URL
3. Connect with `psql` and run `DROP TABLE lead, dealer, vehicle, message, leadevent, appointment, consentlog, alembic_version CASCADE;`
4. Redeploy — `init_db()` will recreate everything from scratch

### Key principle

`create_all` is a one-shot. It creates tables on first deploy and never touches them again.
Every schema change after that MUST go through either:
- Alembic migration (preferred for production)
- The `ALTER TABLE` fixup in `start.sh` (safety net for existing DBs)

Never assume that pushing new model code will update the production database.

---

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run with hot-reload
uvicorn app.main:app --reload

# Run tests
pytest

# Run the scheduler (separate terminal, until merged into lifespan)
python -m app.scheduler
```

The app starts on `http://localhost:8000`. Dashboard at `http://localhost:8000/dashboard`.
