# Speed to Lead v5

## Architecture
- FastAPI + SQLAlchemy + PostgreSQL (Render hosted)
- Twilio for SMS/WhatsApp/Voice
- OpenRouter (Gemini 2.5 Flash) for AI conversation
- Deployed: https://speed-to-lead-v5.onrender.com

## Key Commands
- `uvicorn app.main:app --reload` — dev server
- `pytest` — run tests
- `python -c "from app.config import settings; print(settings)"` — check config

## Current Issue
WhatsApp AI responses not working. Root causes:
1. `app/transports/twilio.py` was missing (just created as adapter)
2. Env vars on Render may be missing (OPENROUTER_API_KEY, OUTBOUND_ENABLED, PUBLIC_BASE_URL)
3. Twilio sandbox webhook URL may not point to /webhook/twilio/whatsapp

## Code Structure
- `app/main.py` — FastAPI app, webhook handlers
- `app/engine/conversation.py` — AI conversation engine (OpenRouter)
- `app/config.py` — Settings (env vars) + DealerConfig (YAML)
- `tools/send_sms.py` — SMS/WhatsApp send functions (the chokepoint)
- `app/transports/twilio.py` — thin adapter bridging main.py -> tools/send_sms
- `dealers/premier-auto.yaml` — test dealer config

## Shell
Use bash syntax (git-bash/MSYS on Windows). NOT PowerShell.
