# Speed-to-Lead v4

**AI-powered lead response system for small car dealerships in BC, Canada.**

Speed-to-Lead automatically responds to new leads within 60 seconds via SMS or phone call, helping dealerships convert more website visitors into test drives.

## What It Does

- Monitors dealership websites for new leads
- Responds instantly via SMS or AI phone call
- Schedules test drives automatically
- Provides a simple dashboard to track leads
- Runs 24/7 with zero manual work

## Tech Stack

- **Backend:** Python 3.12, FastAPI
- **Database:** PostgreSQL (production) / SQLite (local dev)
- **AI:** OpenRouter (Gemini, Claude, etc.)
- **SMS/Voice:** Twilio
- **Deployment:** Render.com ($7/mo for 24/7 uptime)
- **Frontend:** Jinja2 templates + HTMX (no separate frontend build)

---

## Quick Start (Local Development)

### Prerequisites

- Python 3.12 installed (download from python.org)
- A code editor (VS Code recommended)

### Step 1: Clone and install

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/speed-to-lead-v4.git
cd speed-to-lead-v4

# Create a virtual environment (keeps dependencies isolated)
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -e ".[inventory]"
```

### Step 2: Set up environment variables

```bash
# Copy the example file
copy .env.example .env   # Windows
cp .env.example .env     # Mac/Linux

# Edit .env and fill in:
# - TWILIO_ACCOUNT_SID (from twilio.com)
# - TWILIO_AUTH_TOKEN (from twilio.com)
# - OPENROUTER_API_KEY (from openrouter.ai)
# - PUBLIC_BASE_URL (use http://localhost:8000 for local dev)
```

### Step 3: Run the app

```bash
# Start the server
uvicorn app.main:app --reload --port 8000

# Open in browser: http://localhost:8000
```

The app will create a SQLite database automatically (`local.db`).

### Step 4: Test with Twilio webhooks (optional)

To test SMS/calls locally, you need a public URL. Use ngrok:

```bash
# Install ngrok (https://ngrok.com)
ngrok http 8000

# Copy the https URL (e.g. https://abc123.ngrok.io)
# Update PUBLIC_BASE_URL in .env with this URL
```

---

## Deploy to Render (Production)

**Cost:** $7/month for 24/7 uptime (free tier available for testing)

### Step 1: Push to GitHub

```bash
# Create a new repo on GitHub (github.com/new)
# Name it: speed-to-lead-v4

# Push your code
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/speed-to-lead-v4.git
git push -u origin main
```

### Step 2: Deploy on Render

1. Go to [render.com](https://render.com) and sign up/log in
2. Click **"New"** → **"Blueprint"**
3. Connect your GitHub account
4. Select the `speed-to-lead-v4` repo
5. Click **"Apply"** — Render will create:
   - A PostgreSQL database (free for 90 days)
   - A web service (free tier, sleeps after 15 min of inactivity)

### Step 3: Set environment variables

In the Render dashboard:

1. Click on your **web service** (speed-to-lead)
2. Go to **Settings** → **Environment**
3. Add these variables:

| Variable | Where to Get It |
|----------|-----------------|
| `TWILIO_ACCOUNT_SID` | twilio.com → Console → Account Info |
| `TWILIO_AUTH_TOKEN` | twilio.com → Console → Account Info |
| `OPENROUTER_API_KEY` | openrouter.ai → API Keys |
| `OPENROUTER_MODEL` | `google/gemini-2.0-flash-001` (or your choice) |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` |
| `OUTBOUND_ENABLED` | Set to `"true"` when ready to send messages |

4. Click **"Save Changes"** — the app will redeploy automatically

### Step 4: Update PUBLIC_BASE_URL

After the first deploy, Render gives you a URL (e.g. `https://speed-to-lead.onrender.com`).

1. Go to **Settings** → **Environment**
2. Update `PUBLIC_BASE_URL` to your Render URL
3. Save and redeploy

### Step 5: Configure Twilio webhooks

1. Go to [twilio.com](https://twilio.com) → Console → Phone Numbers
2. Click on your Twilio phone number
3. Under "Voice & Fax" → "A Call Comes In":
   - Set to: `https://YOUR_RENDER_URL/voice/incoming`
   - Method: POST
4. Under "Messaging" → "A Message Comes In":
   - Set to: `https://YOUR_RENDER_URL/sms/incoming`
   - Method: POST
5. Save

**Done!** Your app is live. Test by submitting a lead through a dealership's website form.

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string (Render provides automatically) |
| `ENVIRONMENT` | No | `development` | `production` or `development` |
| `PUBLIC_BASE_URL` | Yes | `http://localhost:8000` | Public URL for webhooks (Render URL or ngrok) |
| `TWILIO_ACCOUNT_SID` | Yes | — | From twilio.com console |
| `TWILIO_AUTH_TOKEN` | Yes | — | From twilio.com console |
| `TWILIO_PHONE_NUMBER` | No | — | Your Twilio phone number (E.164: +1234567890) |
| `OPENROUTER_API_KEY` | Yes | — | From openrouter.ai |
| `OPENROUTER_MODEL` | No | `google/gemini-2.0-flash-001` | AI model to use |
| `OPENROUTER_BASE_URL` | No | `https://openrouter.ai/api/v1` | OpenRouter API endpoint |
| `OUTBOUND_ENABLED` | No | `false` | **Safety gate:** set to `"true"` to enable sending SMS/calls |
| `PORT` | No | `8000` | Port for web server (Render sets this automatically) |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      Render.com                              │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Web Service (Docker Container)                      │   │
│  │                                                      │   │
│  │  ┌──────────────┐    ┌──────────────────────────┐   │   │
│  │  │  FastAPI      │    │  Background Scheduler    │   │   │
│  │  │  (uvicorn)    │    │  (via lifespan)          │   │   │
│  │  │              │    │  - Checks for new leads   │   │   │
│  │  │  /healthz    │    │  - Sends SMS/calls        │   │   │
│  │  │  /readyz     │    │  - Runs every minute      │   │   │
│  │  └──────┬───────┘    └──────────────────────────┘   │   │
│  │         │                                            │   │
│  └─────────┼────────────────────────────────────────────┘   │
│            │                                                │
│  ┌─────────▼─────────┐                                      │
│  │  PostgreSQL        │                                      │
│  │  (Managed DB)      │                                      │
│  └───────────────────┘                                      │
└─────────────────────────────────────────────────────────────┘
         │                           │
         ▼                           ▼
   ┌───────────┐              ┌───────────┐
   │  Twilio   │              │ OpenRouter │
   │ (SMS/     │              │ (AI/LLM)   │
   │  Voice)   │              └───────────┘
   └───────────┘
```

**How it works:**
1. Dealership website submits new lead → hits your FastAPI endpoint
2. Scheduler (runs every minute) picks up new leads
3. For each lead: AI generates personalized response → sends via Twilio SMS or makes a phone call
4. Lead status updates in database → visible in dashboard

---

## Troubleshooting

### "Database connection failed"
- Check `DATABASE_URL` is set correctly
- For local dev: use SQLite (`sqlite:///./local.db`)
- For Render: use the auto-provided `DATABASE_URL` from the database service

### "Twilio authentication failed"
- Verify `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` are correct
- Check twilio.com console for the right values

### "OpenRouter API error"
- Verify `OPENROUTER_API_KEY` is valid
- Check you have credits at openrouter.ai

### App is sleeping (Render free tier)
- Free tier sleeps after 15 min of inactivity
- Upgrade to "Starter" ($7/mo) for 24/7 uptime
- Or use a cron job to ping `/healthz` every 10 min

### SMS/calls not sending
- Check `OUTBOUND_ENABLED` is set to `"true"`
- Verify `PUBLIC_BASE_URL` is correct (Render URL, not localhost)
- Check Twilio webhook URLs are configured correctly

---

## Cost Breakdown

| Service | Free Tier | Paid (Recommended) |
|---------|-----------|-------------------|
| Render Web Service | $0 (sleeps after 15 min) | $7/mo (24/7) |
| Render PostgreSQL | $0 (90 days) | $7/mo |
| Twilio SMS | ~$0.0079/msg | Pay per use |
| Twilio Voice | ~$0.014/min | Pay per use |
| OpenRouter (AI) | Varies by model | ~$0.10-0.50/1000 leads |

**Total for production:** ~$14-21/month + per-message costs

---

## Support

Questions? Issues? Open an issue on GitHub or contact Manav.

---

**Built for BC car dealerships. Ship fast, respond faster.**
