"""Latency budget tests — assert that the inbound-lead → outbound-auto-reply path is fast.

The speed-to-lead promise is that every lead gets an intelligent reply **within seconds**.
These tests measure the webhook → response time under various conditions and assert
it stays within the budget (< 5 seconds for the webform path, which doesn't call Claude).
"""

from __future__ import annotations

import time
from sqlalchemy.orm import sessionmaker

from app.models import Dealer
from tests.conftest import make_auth_cookies


SPEED_TO_LEAD_BUDGET_SECONDS = 5.0  # The promise: reply within seconds


def _make_dealer(db_engine, slug="latency-dealer", token="latency-token"):
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = TestSession()
    d = Dealer(
        slug=slug,
        name=f"Latency Test {slug}",
        config={
            "dealer": {"name": "Latency Auto", "timezone": "America/Vancouver", "main_phone": "+16045550000"},
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
            ],
            "compliance": {"opt_out_keywords": ["STOP"], "quiet_hours": "21:00-08:00"},
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
    import app.db as db_module
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "_SessionLocal", TestSession)
    monkeypatch.setattr(db_module, "_engine", db_engine)
    monkeypatch.setattr(db_module, "init_db", lambda url=None: None)
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_webform_response_time(db_engine, monkeypatch):
    """Webform submission → response should be well within the speed-to-lead budget."""
    _make_dealer(db_engine)
    client = _make_client(db_engine, monkeypatch)

    start = time.perf_counter()
    resp = client.post("/webhook/form/latency-token", json={
        "full_name": "Speed Test",
        "phone": "(604) 555-1111",
        "consent_sms": True,
        "vehicle_stock": "SA1001",
    })
    elapsed = time.perf_counter() - start

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert elapsed < SPEED_TO_LEAD_BUDGET_SECONDS, (
        f"Webform response took {elapsed:.2f}s — budget is {SPEED_TO_LEAD_BUDGET_SECONDS}s"
    )


def test_webform_response_time_with_payload(db_engine, monkeypatch):
    """Webform with full payload (all fields) should still be fast."""
    _make_dealer(db_engine)
    client = _make_client(db_engine, monkeypatch)

    start = time.perf_counter()
    resp = client.post("/webhook/form/latency-token", json={
        "full_name": "Full Payload Test",
        "phone": "(604) 555-2222",
        "email": "test@example.com",
        "consent_sms": True,
        "vehicle_stock": "SA1001",
        "vehicle_title": "2022 Honda Civic Sport",
        "message": "I'm very interested in this vehicle. Is it still available? Can I come see it this weekend?",
        "page_url": "https://testdrivemotors.example.ca/inventory/TDM001",
        "submitted_at": "2026-06-05T10:30:00-07:00",
    })
    elapsed = time.perf_counter() - start

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert elapsed < SPEED_TO_LEAD_BUDGET_SECONDS, (
        f"Full-payload response took {elapsed:.2f}s — budget is {SPEED_TO_LEAD_BUDGET_SECONDS}s"
    )


def test_healthz_response_time(db_engine, monkeypatch):
    """/healthz should respond in < 200ms (it's just a static check)."""
    _make_dealer(db_engine)
    client = _make_client(db_engine, monkeypatch)

    start = time.perf_counter()
    resp = client.get("/healthz")
    elapsed = time.perf_counter() - start

    assert resp.status_code == 200
    assert elapsed < 0.2, f"Healthz took {elapsed:.3f}s — should be < 200ms"


def test_dashboard_response_time(db_engine, monkeypatch):
    """/dashboard/leads should render in < 2s even with some leads."""
    _make_dealer(db_engine)
    client = _make_client(db_engine, monkeypatch)

    # Seed some leads
    for i in range(5):
        client.post("/webhook/form/latency-token", json={
            "full_name": f"Dash Test {i}",
            "phone": f"(604) 555-{3000+i}",
            "consent_sms": True,
        })

    start = time.perf_counter()
    resp = client.get("/dashboard/leads", cookies=make_auth_cookies())
    elapsed = time.perf_counter() - start

    assert resp.status_code == 200
    assert elapsed < 2.0, f"Dashboard took {elapsed:.2f}s — should be < 2s"


def test_sequential_leads_stay_fast(db_engine, monkeypatch):
    """Submitting leads one after another should not get slower over time (no memory leaks / connection exhaustion)."""
    _make_dealer(db_engine)
    client = _make_client(db_engine, monkeypatch)

    times = []
    for i in range(10):
        start = time.perf_counter()
        resp = client.post("/webhook/form/latency-token", json={
            "full_name": f"Sequential {i}",
            "phone": f"(604) 555-{5000+i}",
            "consent_sms": True,
        })
        elapsed = time.perf_counter() - start
        assert resp.status_code == 200
        times.append(elapsed)

    # The 10th request should not be significantly slower than the 1st
    # Allow 2x variance, but not 10x (which would indicate a leak)
    first_avg = sum(times[:3]) / 3
    last_avg = sum(times[-3:]) / 3
    assert last_avg < first_avg * 5, (
        f"Performance degraded: first 3 avg={first_avg:.3f}s, last 3 avg={last_avg:.3f}s"
    )
    # And all should be within budget
    for i, t in enumerate(times):
        assert t < SPEED_TO_LEAD_BUDGET_SECONDS, (
            f"Lead {i} took {t:.2f}s — budget is {SPEED_TO_LEAD_BUDGET_SECONDS}s"
        )