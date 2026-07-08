"""Phase 14 - End-to-end smoke test."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.models import ConsentLog, Dealer, Lead, LeadState


@pytest.fixture
def client(db_engine, monkeypatch):
    import app.db as db_module
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "_SessionLocal", TestSession)
    monkeypatch.setattr(db_module, "_engine", db_engine)
    monkeypatch.setattr(db_module, "init_db", lambda url=None: None)
    from app.main import app
    return TestClient(app)


@pytest.fixture
def dealer(db_engine):
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = TestSession()
    d = Dealer(slug="smoke-test", name="Smoke Auto", config={
        "dealer": {"name": "Smoke Auto", "timezone": "America/Vancouver", "main_phone": "+160****0000"},
        "hours": {"mon": "09:00-19:00", "tue": "09:00-19:00", "wed": "09:00-19:00",
                  "thu": "09:00-19:00", "fri": "09:00-19:00", "sat": "10:00-17:00"},
        "channels": {
            "web_form_token": "smoke-token",
            "sms_number": "+177****0222",
            "whatsapp_sender": "+177****0223",
        },
        "sales_team": [
            {"name": "Alex", "phone": "+160****0301", "active": True},
            {"name": "Jordan", "phone": "+160****0302", "active": True},
        ],
        "compliance": {"opt_out_keywords": ["STOP", "ARRET"], "quiet_hours": "21:00-08:00"},
        "routing": {"strategy": "round_robin", "claim_timeout_min": 5},
        "ai": {"persona": "friendly local rep", "goal": "book_appointment"},
    })
    session.add(d)
    session.commit()
    session.refresh(d)
    session.close()
    return d


def test_full_happy_path(client, db_engine, dealer):
    """Webform -> auto-reply -> assign -> WhatsApp claim."""
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)

    # Step 1: Submit webform
    resp = client.post("/webhook/form/smoke-token", json={
        "full_name": "Jane Smith",
        "phone": "(778) 555-9999",
        "consent_sms": True,
        "vehicle_stock": "SA1001",
        "message": "I am interested in the Civic",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    # Pipeline is wired end-to-end: NEW -> AUTO_REPLIED -> ASSIGNED
    assert data["state"] in ("AUTO_REPLIED", "ASSIGNED")
    lead_id = data["lead_id"]

    # Step 2: Verify lead in DB
    session = TestSession()
    lead = session.get(Lead, lead_id)
    assert lead is not None
    assert lead.name == "Jane Smith"
    assert lead.phone == "+177****9999"
    assert lead.consent is True
    # Wired pipeline advances to ASSIGNED
    assert lead.state in (LeadState.AUTO_REPLIED, LeadState.ASSIGNED)

    # Step 3: Ensure assigned_rep is Alex (round-robin may have picked either; the test
    # sets it explicitly so the WhatsApp claim flow has a known rep to match)
    lead.assigned_rep = "Alex"
    session.commit()
    lead.assigned_rep = "Alex"
    session.commit()
    session.close()

    # Step 4: Rep claims via WhatsApp
    resp = client.post("/webhook/twilio/whatsapp", data={
        "From": "whatsapp:+160****0301",
        "To": "whatsapp:+177****0223",
        "Body": "1",
    })
    assert resp.status_code == 200
    assert "claimed" in resp.text.lower()

    # Step 5: Verify CLAIMED
    session = TestSession()
    lead = session.get(Lead, lead_id)
    assert lead.state == LeadState.CLAIMED
    session.close()


def test_opt_out_suppression(client, db_engine, dealer):
    """STOP keyword -> OPTED_OUT."""
    resp = client.post("/webhook/form/smoke-token", json={
        "full_name": "Opt Out User",
        "phone": "(778) 555-8888",
        "consent_sms": True,
    })
    lead_id = resp.json()["lead_id"]

    resp = client.post("/webhook/twilio/sms", data={
        "From": "+177****8888",
        "To": "+177****0222",
        "Body": "STOP",
    })
    assert "unsubscribed" in resp.text.lower()

    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = TestSession()
    lead = session.get(Lead, lead_id)
    assert lead.state == LeadState.OPTED_OUT

    opt = session.query(ConsentLog).filter(
        ConsentLog.phone == "+177****8888",
        ConsentLog.action == "opted_out",
    ).first()
    assert opt is not None
    session.close()


def test_voice_missed_call_textback(client, db_engine, dealer):
    resp = client.post("/webhook/twilio/voice", data={
        "From": "+177****7777",
        "To": "+177****0222",
        "CallStatus": "no-answer",
    })
    assert resp.status_code == 200
    assert "Smoke Auto" in resp.text


def test_dashboard_renders(client, db_engine, dealer, auth_cookies):
    resp = client.get("/dashboard/leads", cookies=auth_cookies)
    assert resp.status_code == 200
    assert "Lead Pipeline" in resp.text


def test_dashboard_shows_leads(client, db_engine, dealer, auth_cookies):
    client.post("/webhook/form/smoke-token", json={
        "full_name": "Dashboard Test",
        "phone": "(778) 555-6666",
        "consent_sms": True,
    })
    resp = client.get("/dashboard/leads", cookies=auth_cookies)
    assert resp.status_code == 200
    assert "Dashboard Test" in resp.text


def test_dashboard_lead_detail(client, db_engine, dealer, auth_cookies):
    resp = client.post("/webhook/form/smoke-token", json={
        "full_name": "Detail Test",
        "phone": "(778) 555-5555",
        "consent_sms": True,
    })
    lead_id = resp.json()["lead_id"]
    resp = client.get(f"/dashboard/leads/{lead_id}", cookies=auth_cookies)
    assert resp.status_code == 200
    assert "Detail Test" in resp.text


def test_team_leaderboard(client, db_engine, dealer, auth_cookies):
    """Team page shows rep performance leaderboard with real data."""
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)

    # Create leads in various states for different reps
    session = TestSession()
    leads_data = [
        ("Alex", LeadState.SOLD),
        ("Alex", LeadState.ENGAGED),
        ("Alex", LeadState.LOST),
        ("Jordan", LeadState.APPT_SET),
        ("Jordan", LeadState.SHOWED),
        ("Jordan", LeadState.SOLD),
        ("Jordan", LeadState.SOLD),
        (None, LeadState.NEW),  # Unassigned
    ]
    for rep, state in leads_data:
        lead = Lead(
            dealer_id=dealer.id,
            source="webform",
            name=f"Lead {rep or 'Unassigned'} {state.value}",
            phone=f"+177****{len(leads_data):04d}",
            assigned_rep=rep,
            state=state,
        )
        session.add(lead)
    session.commit()
    session.close()

    # GET the team page
    resp = client.get("/dashboard/team", cookies=auth_cookies)
    assert resp.status_code == 200
    html = resp.text

    # Leaderboard heading present
    assert "Rep Performance Leaderboard" in html

    # Jordan has 3 sold (should rank #1), Alex has 1 sold
    jordan_idx = html.index("Jordan")
    alex_idx = html.index("Alex")
    assert jordan_idx < alex_idx, "Jordan (3 sold) should rank above Alex (1 sold)"

    # TOP badge appears for #1 rank
    assert "TOP" in html

    # Conversion percentages are rendered
    assert "%" in html

    # Stats cards are rendered
    assert "Active Reps" in html
    assert "Overall Conversion" in html
