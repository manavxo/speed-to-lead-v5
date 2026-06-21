cd /c/Speed\ to\ Lead\ v5 && claude -p "$(cat <<'END_PROMPT'
COST WARNING: Twilio balance is low (~$9). Steps 3-6 in the verification MUST use dry-run mode. Do NOT send real SMS/WhatsApp messages.

SETTING: OUTBOUND_ENABLED=false is already set on Render (deploy live). This means ALL sends are dry-run — messages are logged in the DB with DRYRUN_ SIDs but NO real messages go out via Twilio. This is the correct mode for debugging.

CRITICAL: You are verifying the core pipeline of Speed to Lead v5. This is the heartbeat of the system. If a real dealer's customer submits a web form and doesn't get an immediate SMS reply, the system is broken.

YOUR JOB — run EVERY step below, in order. If anything fails, trace through the codebase, find the root cause, fix it, then re-run. Do NOT stop at "it failed."

Step 1 — Auth & Config Health
  RENDER_API_KEY=***REMOVED-RENDER-API-KEY*** python skills/fix_twilio_sms_auth.py
  Expected: Local 200, Render 200, PHONE_NUMBER = +17787623122

Step 2 — Landing page is live
  curl -s -o /dev/null -w "%{http_code}" https://speed-to-lead-v5.onrender.com/
  Expected: 200

Step 3 — Submit a fresh lead (dry-run — won't send real SMS)
  First, delete any existing leads for +16048392870 from the DB:
    python -c "
import sys; sys.path.insert(0,'.'); import os
os.environ['DATABASE_URL']='postgresql+psycopg://speedtoleadv5:SzVZWqSHaT6U9lA9faFxQC1leTAVKVoo@dpg-d8qc97og4nts7386i000-a.oregon-postgres.render.com/speedtoleadv5'
from app.db import get_session_factory, init_db; init_db()
session=get_session_factory()()
from app.models import Lead, Message, ConsentLog, LeadEvent
from sqlalchemy import select, delete as sa_delete
phone='+16048392870'
leads=session.execute(select(Lead).where(Lead.phone==phone)).scalars().all()
for l in leads:
  session.execute(sa_delete(LeadEvent).where(LeadEvent.lead_id==l.id))
  session.execute(sa_delete(Message).where(Message.lead_id==l.id))
  session.execute(sa_delete(ConsentLog).where(ConsentLog.lead_id==l.id))
  session.delete(l); print(f'Deleted lead#{l.id}')
session.commit(); session.close()
"
  Then submit (this will create the lead, auto-reply is dry-run, AI follow-up is dry-run):
  curl -s -X POST "https://speed-to-lead-v5.onrender.com/webhook/form/premier-auto-group-token" \
    -H "Content-Type: application/json" \
    -d '{"full_name":"Manav","phone":"+16048392870","email":"manav@gmail.com","consent":true,"vehicle_of_interest":"PAG005","message":"Hi interested in the Tesla Model 3","referrer":"premier-auto","inquiry_type":"general"}'
  Expected: {"status":"ok","lead_id":<N>,"state":"ENGAGED","dealer":"premier-auto"}

Step 4 — Verify messages logged in DB (dry-run mode)
  python -c "
import sys; sys.path.insert(0,'.'); import os
os.environ['DATABASE_URL']='postgresql+psycopg://speedtoleadv5:SzVZWqSHaT6U9lA9faFxQC1leTAVKVoo@dpg-d8qc97og4nts7386i000-a.oregon-postgres.render.com/speedtoleadv5'
from app.db import get_session_factory, init_db; init_db()
session=get_session_factory()()
from app.models import Message, Lead
from sqlalchemy import select
phone='+16048392870'
lead=session.execute(select(Lead).where(Lead.phone==phone).order_by(Lead.id.desc())).scalars().first()
if lead:
  msgs=session.execute(select(Message).where(Message.lead_id==lead.id).order_by(Message.id)).scalars().all()
  print(f'Lead #{lead.id} state={lead.state}')
  for m in msgs:
    print(f'  msg#{m.id}  dir={m.direction}  channel={m.channel}  ai={m.ai_generated}  sid={m.provider_sid[:30]}  body={m.body[:80]}')
else:
  print('No lead found')
session.close()
"
  CRITICAL: Must show 2 messages (auto-reply + AI follow-up). Both must have DRYRUN_ SIDs (proving they didn't actually hit Twilio). The channel must be 'sms' (NOT 'whatsapp'). The body must mention Manav by name.

Step 5 — Simulate customer reply (dry-run — creates lead message + triggers AI, won't send real SMS)
  curl -s -X POST "https://speed-to-lead-v5.onrender.com/webhook/twilio/sms" \
    -d "To=%2B17787623122&From=%2B16048392870&Body=What+do+you+have+that%27s+similar+to+the+Tesla&MessageSid=TEST_$(date +%s)"
  Expected: Returns TwiML (200). Then check DB for the AI's reply dry-run message.

Step 6 — Verify AI response to reply in DB
  Same python script as Step 4. Should show a 3rd message: AI's response to "What do you have that's similar to the Tesla" with DRYRUN_ SID and channel='sms'.

IF ANY STEP FAILS:
- Read the relevant source files (app/main.py, tools/route_lead.py, tools/send_sms.py, app/engine/conversation.py, dealers/premier-auto.yaml)
- Find the root cause. Check the code path carefully.
- Fix it
- Deploy: curl -X POST https://api.render.com/v1/services/srv-d8misim7r5hc739rf7sg/deploys -H "Authorization: Bearer ***REMOVED-RENDER-API-KEY***" -H "Content-Type: application/json" -d '{}'
- Poll for 'live': curl -s "https://api.render.com/v1/services/srv-d8misim7r5hc739rf7sg/deploys?limit=1" -H "Authorization: Bearer ***REMOVED-RENDER-API-KEY***" -H "Accept: application/json" | python -c "import sys,json; print(json.load(sys.stdin)[0]['deploy']['status'])"
- Re-run the failed step to confirm

REPORT: At the end, state in plain terms: what passed, what failed, what you fixed, and whether a real customer hitting the landing page would get an SMS right now (assuming OUTBOUND_ENABLED=true).
END_PROMPT
)" --allowedTools "Read,Write,Edit,Bash,Bash(rm *)" --max-turns 35 --model sonnet --dangerously-skip-permissions
