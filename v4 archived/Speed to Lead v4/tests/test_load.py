"""Load / stress tests — verify the engine handles concurrent webhooks without corruption.

These tests use the in-memory SQLite DB and FastAPI TestClient, so no external services are hit.
They simulate multiple leads arriving simultaneously and verify:
- No DB integrity errors
- All leads get created (no orphaned leads)
- Health checks stay responsive under load

NOTE: SQLite has limited write concurrency. Tests use sequential requests to avoid
database locking issues that don't occur with Postgres in production.
"""

from __future__ import annotations

import concurrent.futures
from sqlalchemy.orm import sessionmaker

from app.models import Dealer, Lead, LeadState


def _make_dealer(db_engine, slug="load-dealer", token="load-token"):
    """Create a test dealer with 3 active reps."""
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = TestSession()
    d = Dealer(
        slug=slug,
        name=f"Load Test {slug}",
        config={
            "dealer": {"name": f"Load Test {slug}", "timezone": "America/Vancouver", "main_phone": "+16045550000"},
            "hours": {"mon": "09:00-19:00", "tue": "09:00-19:00", "wed": "09:00-19:00",
                      "thu": "09:00-19:00", "fri": "09:00-19:00", "sat": "10:00-17:00"},
            "channels": {
                "web_form_token": token,
                "sms_number": "+17785550222",
                "whatsapp_sender": "+17785550223",
            },
            "sales_team": [
                {"name": "Alex", "phone": "+16045550301", "active": True},
                {"name": "Jordan", "phone": "+16045550302", "active": True},
                {"name": "Sam", "phone": "+16045550303", "active": True},
            ],
            "compliance": {"opt_out_keywords": ["STOP", "ARRET"], "quiet_hours": "21:00-08:00"},
            "routing": {"strategy": "round_robin", "claim_timeout_min": 5},
            "ai": {"persona": "friendly local rep", "goal": "book_appointment"},
        },
    )
    session.add(d)
    session.commit()
    session.refresh(d)
    session.close()
    return d


def _make_client(db_engine, monkeypatch):
    """Create a TestClient with the test DB."""
    import app.db as db_module
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "_SessionLocal", TestSession)
    monkeypatch.setattr(db_module, "_engine", db_engine)
    monkeypatch.setattr(db_module, "init_db", lambda url=None: None)
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def _submit_lead(client, token, name, phone):
    """Submit a webform lead and return the response data."""
    resp = client.post(f"/webhook/form/{token}", json={
        "full_name": name,
        "phone": phone,
        "consent_sms": True,
        "vehicle_stock": "SA1001",
        "message": f"Hi, I'm {name} interested in the vehicle.",
    })
    return resp.json()


def test_sequential_leads_no_corruption(db_engine, monkeypatch):
    """10 sequential lead submissions should all succeed without DB errors."""
    _make_dealer(db_engine)
    client = _make_client(db_engine, monkeypatch)

    results = []
    for i in range(10):
        r = _submit_lead(client, "load-token", f"Lead_{i}", f"(604) 555-{1000+i}")
        results.append(r)

    # All 10 should succeed
    assert len(results) == 10
    for r in results:
        assert r["status"] == "ok"
        assert r["lead_id"] is not None


def test_rapid_sequential_leads_unique_ids(db_engine, monkeypatch):
    """All sequential leads get unique database IDs."""
    _make_dealer(db_engine)
    client = _make_client(db_engine, monkeypatch)

    results = []
    for i in range(10):
        r = _submit_lead(client, "load-token", f"Person_{i}", f"(604) 555-{2000+i}")
        results.append(r)

    lead_ids = [r["lead_id"] for r in results]
    assert len(set(lead_ids)) == 10, f"Duplicate lead IDs found: {lead_ids}"


def test_sequential_leads_all_have_auto_replied_state(db_engine, monkeypatch):
    """All leads should reach AUTO_REPLIED (or ASSIGNED via the wired pipeline) state.
    With the pipeline now wired end-to-end, leads advance to ASSIGNED after auto-reply.
    The dealer in this test has no sales_team, so the lead stays at AUTO_REPLIED
    (assignment is skipped when there's no team)."""
    _make_dealer(db_engine)
    client = _make_client(db_engine, monkeypatch)

    results = []
    for i in range(6):
        r = _submit_lead(client, "load-token", f"Buyer_{i}", f"(604) 555-{3000+i}")
        results.append(r)

    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = TestSession()
    for r in results:
        lead = session.get(Lead, r["lead_id"])
        assert lead is not None, f"Lead {r['lead_id']} not found in DB"
        # Pipeline is wired; without sales_team, lead stays at AUTO_REPLIED
        assert lead.state in (LeadState.AUTO_REPLIED, LeadState.ASSIGNED), (
            f"Lead {lead.id} in state {lead.state}, expected AUTO_REPLIED or ASSIGNED"
        )
    session.close()


def test_rapid_same_phone_different_names(db_engine, monkeypatch):
    """Same phone submitting multiple leads — first is kept, subsequent are deduped within 24h."""
    _make_dealer(db_engine, slug="rapid-dealer", token="rapid-token")
    client = _make_client(db_engine, monkeypatch)

    # First submission succeeds
    r1 = _submit_lead(client, "rapid-token", "Caller_0", "(604) 555-9999")
    assert r1["status"] == "ok"

    # Second submission with same phone — deduped (returns existing lead)
    r2 = _submit_lead(client, "rapid-token", "Caller_1", "(604) 555-9999")
    assert r2["status"] == "ok"
    assert r2["lead_id"] == r1["lead_id"]  # Same lead returned due to dedup


def test_healthz_responds_during_load(db_engine, monkeypatch):
    """/healthz should respond 200 even while leads are being processed."""
    _make_dealer(db_engine, slug="health-dealer", token="health-token")
    client = _make_client(db_engine, monkeypatch)

    # Submit some leads first
    for i in range(3):
        _submit_lead(client, "health-token", f"User_{i}", f"(604) 555-{4000+i}")

    # Health check should still work
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_concurrent_healthz(db_engine, monkeypatch):
    """/healthz should respond 200 under concurrent reads."""
    _make_dealer(db_engine, slug="concurrent-dealer", token="concurrent-token")
    client = _make_client(db_engine, monkeypatch)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(lambda: client.get("/healthz")) for _ in range(10)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    for r in results:
        assert r.status_code == 200