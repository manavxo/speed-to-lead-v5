# Implementation Tasks

Ordered tasks for completing Speed to Lead v4. Each task is self-contained with a verification step.

**Working directory:** The v4 project root.
**Test command:** `pytest -q --tb=short`
**Run command:** `uvicorn app.main:app --reload`

---

## Task 1: Wire Dashboard Routes to Real Data

**Objective:** Replace mock data in dashboard templates with live database queries.

**Files to modify:**
- `app/dashboard/__init__.py` — Add/update routes
- `app/dashboard/templates/leads.html` — Use Jinja2 variables instead of hardcoded data
- `app/dashboard/templates/lead_detail.html` — Same
- `app/dashboard/templates/stats.html` — Same

**What to build:**

1. Update the `/dashboard/leads` route to query all leads for the current dealer:
```python
@router.get("/leads")
def leads_page(request: Request, db: Session = Depends(get_session)):
    leads = db.query(Lead).filter(Lead.dealer_id == DEFAULT_DEALER_ID).order_by(Lead.created_at.desc()).all()
    active_count = sum(1 for l in leads if l.state not in (LeadState.SOLD, LeadState.LOST, LeadState.OPTED_OUT))
    appt_count = sum(1 for l in leads if l.state == LeadState.APPT_SET)
    sold_count = sum(1 for l in leads if l.state == LeadState.SOLD)
    return templates.TemplateResponse("leads.html", {
        "request": request, "leads": leads,
        "total_leads": len(leads), "active_leads": active_count,
        "appt_leads": appt_count, "sold_leads": sold_count,
    })
```

2. Update the `/dashboard/leads/{lead_id}` route to load a single lead with messages and appointments:
```python
@router.get("/leads/{lead_id}")
def lead_detail_page(lead_id: int, request: Request, db: Session = Depends(get_session)):
    lead = db.get(Lead, lead_id)
    messages = db.query(Message).filter(Message.lead_id == lead_id).order_by(Message.created_at).all()
    events = db.query(LeadEvent).filter(LeadEvent.lead_id == lead_id).order_by(LeadEvent.created_at).all()
    appointments = db.query(Appointment).filter(Appointment.lead_id == lead_id).order_by(Appointment.scheduled_for).all()
    return templates.TemplateResponse("lead_detail.html", {
        "request": request, "lead": lead, "messages": messages,
        "events": events, "appointments": appointments,
    })
```

3. Add a `/dashboard/stats` route:
```python
@router.get("/stats")
def stats_page(request: Request, db: Session = Depends(get_session)):
    leads = db.query(Lead).filter(Lead.dealer_id == DEFAULT_DEALER_ID).all()
    messages = db.query(Message).join(Lead).filter(Lead.dealer_id == DEFAULT_DEALER_ID).all()
    appointments = db.query(Appointment).join(Lead).filter(Lead.dealer_id == DEFAULT_DEALER_ID).all()
    return templates.TemplateResponse("stats.html", {
        "request": request, "leads": leads, "messages": messages, "appointments": appointments,
    })
```

4. Update each template to use `{% for lead in leads %}` instead of hardcoded HTML rows.

**Verification:**
```bash
# Start the app
uvicorn app.main:app --reload

# Visit http://localhost:8000/dashboard/leads — should show real leads (or empty table)
# Visit http://localhost:8000/dashboard/leads/1 — should show lead detail with messages
# Visit http://localhost:8000/dashboard/stats — should show stats page

# Run tests
pytest -q --tb=short
# Expected: 126+ passed (dashboard tests should now pass too)
```

---

## Task 2: Merge Scheduler into FastAPI Lifespan

**Objective:** Eliminate the separate scheduler process. Run APScheduler inside FastAPI.

**Files to modify:**
- `app/main.py` — Add lifespan context manager
- `app/scheduler.py` — Expose a `start_scheduler()` function

**What to build:**

1. In `app/main.py`, create a lifespan handler:
```python
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from app.scheduler import register_jobs

scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    from app.db import init_db
    init_db()
    register_jobs(scheduler)
    scheduler.start()
    yield
    # Shutdown
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
```

2. In `app/scheduler.py`, create `register_jobs(scheduler)` that adds all jobs:
```python
def register_jobs(scheduler):
    """Register all background jobs with the given scheduler."""
    scheduler.add_job(check_escalations, "interval", minutes=1, id="escalation_check")
    scheduler.add_job(send_followups, "interval", minutes=5, id="followup_check")
    scheduler.add_job(sync_inventory, "interval", hours=6, id="inventory_sync")
```

3. Update `start.sh` to remove the separate scheduler process:
```bash
#!/usr/bin/env bash
set -euo pipefail
python -c "from app.db import init_db; init_db()"
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
```

**Verification:**
```bash
# Start the app
uvicorn app.main:app --reload

# Check logs for "Scheduler started" message
# Check that escalation and followup jobs are registered

# Run tests
pytest -q --tb=short
# Expected: All tests pass (scheduler is now in-process, no external dependency)
```

---

## Task 3: Add Simple Auth

**Objective:** Protect the dashboard with username/password login.

**Files to modify:**
- `app/main.py` — Add auth middleware
- `app/config.py` — Add `DASHBOARD_USER` and `DASHBOARD_PASSWORD` settings
- `app/dashboard/__init__.py` — Add login route

**What to build:**

1. Add settings to `app/config.py`:
```python
DASHBOARD_USER: str = "admin"
DASHBOARD_PASSWORD: str = ""
```

2. Add login route to `app/dashboard/__init__.py`:
```python
from fastapi.responses import RedirectResponse

@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == settings.DASHBOARD_USER and password == settings.DASHBOARD_PASSWORD:
        response = RedirectResponse("/dashboard/leads", status_code=302)
        response.set_cookie("session", "authenticated", httponly=True, max_age=86400)
        return response
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})
```

3. Add auth check middleware:
```python
from fastapi import Cookie

def require_auth(session: str = Cookie(None)):
    if session != "authenticated":
        raise HTTPException(status_code=302, headers={"Location": "/dashboard/login"})
```

4. Add logout route:
```python
@router.get("/logout")
def logout():
    response = RedirectResponse("/dashboard/login")
    response.delete_cookie("session")
    return response
```

**Verification:**
```bash
# Set env vars
export DASHBOARD_USER=admin
export DASHBOARD_PASSWORD=test123

# Start app
uvicorn app.main:app --reload

# Visit http://localhost:8000/dashboard/leads — should redirect to /dashboard/login
# Login with admin/test123 — should redirect to leads page
# Visit /dashboard/logout — should redirect back to login

# Run tests
pytest -q --tb=short
```

---

## Task 4: Build "Needs Attention" Widget

**Objective:** Top-of-dashboard widget showing the 5-10 most urgent items for the GM.

**Files to modify:**
- `app/dashboard/__init__.py` — Add route or embed in existing route
- `app/dashboard/templates/leads.html` — Add widget at the top

**What to build:**

1. Create a helper function that computes attention items:
```python
from datetime import datetime, timedelta, timezone

def get_attention_items(db: Session, dealer_id: str) -> list[dict]:
    items = []
    now = datetime.now(timezone.utc)
    
    # Unclaimed leads (ASSIGNED > 2 hours)
    unclaimed = db.query(Lead).filter(
        Lead.dealer_id == dealer_id,
        Lead.state == LeadState.ASSIGNED,
        Lead.updated_at < now - timedelta(hours=2)
    ).all()
    for lead in unclaimed:
        hours = (now - lead.updated_at).total_seconds() / 3600
        items.append({"type": "unclaimed", "lead": lead, "message": f"Unclaimed for {hours:.0f}h", "urgency": "high"})
    
    # Going cold (ENGAGED with no activity in 48h)
    cold = db.query(Lead).filter(
        Lead.dealer_id == dealer_id,
        Lead.state == LeadState.ENGAGED,
        Lead.updated_at < now - timedelta(hours=48)
    ).all()
    for lead in cold:
        items.append({"type": "cold", "lead": lead, "message": "No activity in 48h+", "urgency": "medium"})
    
    return sorted(items, key=lambda x: {"high": 0, "medium": 1}[x["urgency"]])[:10]
```

2. Pass `attention_items` to the leads template.
3. Add a styled alert section at the top of leads.html.

**Verification:**
```bash
# Create a test lead in ASSIGNED state with updated_at 3+ hours ago
# Visit /dashboard/leads — should show "Unclaimed for 3h" in the attention widget
# Create a test lead in ENGAGED state with updated_at 3+ days ago
# Should show "No activity in 48h+" in the attention widget
```

---

## Task 5: Build Response Time Metrics

**Objective:** Show average response time and percentage of leads responded to within 5 minutes.

**Files to modify:**
- `app/dashboard/__init__.py` — Compute metrics
- `app/dashboard/templates/stats.html` — Display metrics

**What to build:**

1. Compute response time from Message table:
```python
def get_response_metrics(db: Session, dealer_id: str) -> dict:
    """Compute response time metrics from message history."""
    from sqlalchemy import func
    
    # Get first inbound and first outbound message time for each lead
    subq = db.query(
        Message.lead_id,
        func.min(Message.created_at).filter(Message.direction == "inbound").label("first_inbound"),
        func.min(Message.created_at).filter(Message.direction == "outbound").label("first_outbound"),
    ).join(Lead).filter(Lead.dealer_id == dealer_id).group_by(Message.lead_id).all()
    
    response_times = []
    within_5_min = 0
    for row in subq:
        if row.first_inbound and row.first_outbound:
            delta = (row.first_outbound - row.first_inbound).total_seconds()
            response_times.append(delta)
            if delta <= 300:  # 5 minutes
                within_5_min += 1
    
    avg_seconds = sum(response_times) / len(response_times) if response_times else 0
    pct_within_5 = (within_5_min / len(response_times) * 100) if response_times else 0
    
    return {
        "avg_response_seconds": avg_seconds,
        "avg_response_display": f"{avg_seconds:.0f}s" if avg_seconds < 60 else f"{avg_seconds/60:.1f}m",
        "pct_within_5_min": pct_within_5,
        "total_with_response": len(response_times),
    }
```

2. Pass metrics to stats template.
3. Display as prominent stat cards with color coding (green <60s, yellow <5min, red >5min).

**Verification:**
```bash
# Create test leads with inbound and outbound messages at known times
# Visit /dashboard/stats — should show correct avg response time
# Verify color coding: <60s = green, <5min = yellow, >5min = red
```

---

## Task 6: Build Lead Health Indicators

**Objective:** Each lead in the list gets a color-coded health badge.

**Files to modify:**
- `app/dashboard/__init__.py` — Compute health for each lead
- `app/dashboard/templates/leads.html` — Display health badges

**What to build:**

1. Compute health status:
```python
def get_lead_health(lead: Lead) -> str:
    now = datetime.now(timezone.utc)
    age_hours = (now - lead.updated_at).total_seconds() / 3600
    
    if lead.state == LeadState.APPT_SET:
        return "hot"
    if lead.state == LeadState.ENGAGED and age_hours < 24:
        return "warm"
    if age_hours < 48:
        return "warm"
    if age_hours < 72:
        return "cold"
    return "dead"
```

2. Add health to each lead in the template context.
3. Display as colored badges: 🟢 Hot, 🟡 Warm, 🔴 Cold, ⚫ Dead.

**Verification:**
```bash
# Create leads with different activity ages
# Visit /dashboard/leads — each lead should have the correct health badge
# Leads with appointments = green, recent activity = yellow, stale = red
```

---

## Task 7: Build Source/Channel Breakdown

**Objective:** Show lead volume and conversion rate by source channel.

**Files to modify:**
- `app/dashboard/__init__.py` — Aggregate by source
- `app/dashboard/templates/stats.html` — Display breakdown

**What to build:**

1. Aggregate leads by source:
```python
def get_source_breakdown(db: Session, dealer_id: str) -> list[dict]:
    leads = db.query(Lead).filter(Lead.dealer_id == dealer_id).all()
    sources = {}
    for lead in leads:
        src = lead.source or "unknown"
        if src not in sources:
            sources[src] = {"total": 0, "sold": 0, "appt_set": 0}
        sources[src]["total"] += 1
        if lead.state == LeadState.SOLD:
            sources[src]["sold"] += 1
        if lead.state in (LeadState.APPT_SET, LeadState.SHOWED, LeadState.SOLD):
            sources[src]["appt_set"] += 1
    
    return [
        {"source": src, "total": d["total"],
         "conversion_pct": (d["sold"] / d["total"] * 100) if d["total"] else 0,
         "appt_pct": (d["appt_set"] / d["total"] * 100) if d["total"] else 0}
        for src, d in sorted(sources.items(), key=lambda x: x[1]["total"], reverse=True)
    ]
```

2. Display as a horizontal bar chart or table in stats.html.

**Verification:**
```bash
# Create test leads from different sources (webform, sms, email)
# Visit /dashboard/stats — should show breakdown by source
# Verify percentages are correct
```

---

## Task 8: Build Conversion Funnel

**Objective:** Visual funnel showing lead count at each pipeline stage.

**Files to modify:**
- `app/dashboard/__init__.py` — Count leads per state
- `app/dashboard/templates/stats.html` — Display funnel

**What to build:**

1. Count leads per state:
```python
def get_conversion_funnel(db: Session, dealer_id: str) -> list[dict]:
    from sqlalchemy import func
    
    counts = db.query(Lead.state, func.count(Lead.id)).filter(
        Lead.dealer_id == dealer_id
    ).group_by(Lead.state).all()
    
    state_counts = {state: count for state, count in counts}
    total = sum(state_counts.values()) or 1
    
    stages = [
        ("NEW", "New Leads"),
        ("AUTO_REPLIED", "Auto-Replied"),
        ("ASSIGNED", "Assigned"),
        ("CLAIMED", "Claimed"),
        ("ENGAGED", "Engaged"),
        ("APPT_SET", "Appointment Set"),
        ("SHOWED", "Showed"),
        ("SOLD", "Sold"),
    ]
    
    return [
        {"state": state, "label": label, "count": state_counts.get(state, 0),
         "pct": (state_counts.get(state, 0) / total * 100)}
        for state, label in stages
    ]
```

2. Display as a horizontal funnel chart with percentage bars.

**Verification:**
```bash
# Create test leads in various states
# Visit /dashboard/stats — should show funnel with correct counts
# Verify the funnel narrows (NEW > AUTO_REPLIED > ASSIGNED > ...)
```

---

## Task 9: Build Rep Performance Leaderboard

**Objective:** Table showing each rep's performance metrics.

**Files to modify:**
- `app/dashboard/__init__.py` — Aggregate by rep
- `app/dashboard/templates/team.html` — Display leaderboard

**What to build:**

1. Aggregate metrics per rep:
```python
def get_rep_performance(db: Session, dealer_id: str) -> list[dict]:
    leads = db.query(Lead).filter(Lead.dealer_id == dealer_id, Lead.assigned_rep.isnot(None)).all()
    
    reps = {}
    for lead in leads:
        rep = lead.assigned_rep
        if rep not in reps:
            reps[rep] = {"assigned": 0, "engaged": 0, "appt_set": 0, "sold": 0, "lost": 0}
        reps[rep]["assigned"] += 1
        if lead.state in (LeadState.ENGAGED, LeadState.APPT_SET, LeadState.SHOWED, LeadState.SOLD):
            reps[rep]["engaged"] += 1
        if lead.state in (LeadState.APPT_SET, LeadState.SHOWED, LeadState.SOLD):
            reps[rep]["appt_set"] += 1
        if lead.state == LeadState.SOLD:
            reps[rep]["sold"] += 1
        if lead.state == LeadState.LOST:
            reps[rep]["lost"] += 1
    
    return [
        {"rep": rep, **metrics, 
         "conversion_pct": (metrics["sold"] / metrics["assigned"] * 100) if metrics["assigned"] else 0}
        for rep, metrics in sorted(reps.items(), key=lambda x: x[1]["sold"], reverse=True)
    ]
```

2. Display as a table in team.html with sortable columns.

**Verification:**
```bash
# Create test leads assigned to different reps
# Visit /dashboard/team — should show rep performance table
# Verify top performer is highlighted
```

---

## Task 10: Deploy to Render

**Objective:** Get the app running on Render's hobby plan.

**Files to modify:**
- None (deployment files already exist)

**Steps:**

1. Push code to GitHub:
```bash
git init
git add -A
git commit -m "v4 initial commit"
gh repo create speed-to-lead-v4 --private --push
```

2. Go to render.com → New → Web Service → Connect GitHub repo
3. Render auto-detects `render.yaml` — review and confirm
4. Add env vars manually:
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - `TWILIO_PHONE_NUMBER`
   - `OPENROUTER_API_KEY`
   - `OUTBOUND_ENABLED=false` (keep false until Twilio is tested)
5. Deploy. Wait for build to complete.
6. Verify:
   - `https://your-app.onrender.com/healthz` returns 200
   - `https://your-app.onrender.com/dashboard/login` shows login page
   - Login with admin/password from env vars

**Verification:**
```bash
curl -s https://your-app.onrender.com/healthz
# Expected: {"status": "ok", "db": "ok"}

curl -s https://your-app.onrender.com/readyz
# Expected: {"status": "ready"}
```

---

## Task 11: Live-Fire Test with Real Phones

**Objective:** End-to-end test with real Twilio SMS to real phone numbers.

**Prerequisites:**
- Twilio credentials configured in Render env vars
- `OUTBOUND_ENABLED=true` set in Render
- 3-4 phone numbers ready for testing

**Steps:**

1. Text the Twilio number from a test phone
2. Verify auto-reply arrives within 60 seconds
3. Verify the lead appears in the dashboard
4. Verify the rep gets a WhatsApp claim ping
5. Reply to the auto-reply with a question
6. Verify the AI responds with a relevant answer
7. Text "STOP" from the test phone
8. Verify opt-out is confirmed and logged
9. Try texting again — verify no response (opted out)

**Verification:**
```bash
# Check dashboard shows the test lead
curl -s https://your-app.onrender.com/dashboard/leads

# Check the lead's conversation history
curl -s https://your-app.onrender.com/dashboard/leads/1

# Check stats show the test data
curl -s https://your-app.onrender.com/dashboard/stats
```

**Success criteria:**
- Auto-reply arrives in <60 seconds
- AI response is relevant to the vehicle inquiry
- STOP processing works immediately
- Dashboard shows all data correctly
- No Twilio errors in logs
