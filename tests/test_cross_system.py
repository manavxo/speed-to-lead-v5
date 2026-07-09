"""Phase 5: Cross-system consistency verification tests.

Proves:
- Lead created via Telegram appears on dashboard
- Availability window set via Telegram is respected by booking
- No-show marked via Telegram reflected on dashboard
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.fixture
def _db(tmp_path):
    """Set up the SQLite DB with premier-auto provisioned."""
    import app.db as db
    from app.main import _auto_provision_dealers

    db_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    db.init_db(db_url)
    db.get_session_factory(db_url)
    _auto_provision_dealers()
    yield
    db._engine = None
    db._SessionLocal = None


def _make_manager_session() -> str:
    from app.dashboard import _get_serializer
    return _get_serializer().dumps({
        "role": "manager", "rep_name": "", "dealer_slug": "premier-auto", "ts": 0,
    })


@patch("app.transports.telegram.TelegramTransport.send")
def test_telegram_lead_appears_on_dashboard(mock_send, _db):
    """Lead created via Telegram appears on /dashboard/leads page."""
    with patch("app.telegram_free_text.classify_message") as mock_classify:
        mock_classify.return_value = {"intent": "new_lead", "params": {
            "name": "CrossCheck Test", "phone": "604-555-9999", "vehicle_ref": "Civic",
        }}
        payload = {
            "message": {
                "text": "new lead, CrossCheck Test, wants a Civic, 604-555-9999",
                "from": {"username": "Helly"},
                "chat": {"id": "8990699115"},
            }
        }
        client = TestClient(__import__("app.main").main.app)
        resp = client.post("/webhook/telegram", json=payload)
        assert resp.status_code == 200

    # Verify it appears on the dashboard
    cookie = _make_manager_session()
    response = client.get("/dashboard/leads", cookies={"session": cookie})
    assert response.status_code == 200
    assert "CrossCheck Test" in response.text
    assert "Civic" in response.text


@patch("app.transports.telegram.TelegramTransport.send")
def test_availability_via_telegram_respected_by_booking(mock_send, _db):
    """Availability window set via Telegram → booking respects it."""
    import app.db as db
    from app.models import Dealer, Appointment, Lead, LeadState, Channel
    import json as _json
    from sqlalchemy.orm.attributes import flag_modified
    from datetime import datetime, timezone

    # Step 1: Set availability via Telegram
    with patch("app.telegram_free_text.classify_message") as mock_classify:
        mock_classify.return_value = {"intent": "availability", "params": {
            "date": "2026-07-17", "start": "14:00", "end": "16:00", "note": "",
        }}
        payload = {
            "message": {
                "text": "not free 2-4 Friday",
                "from": {"username": "Helly"},
                "chat": {"id": "8990699115"},
            }
        }
        client = TestClient(__import__("app.main").main.app)
        client.post("/webhook/telegram", json=payload)

    # Step 2: Confirm
    payload_confirm = {
        "message": {
            "text": "yes",
            "from": {"username": "Helly"},
            "chat": {"id": "8990699115"},
        }
    }
    client.post("/webhook/telegram", json=payload_confirm)

    # Step 3: Verify booking rejects Helly for that slot
    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None
        config = dealer.config or {}
        helly = next(r for r in config["sales_team"] if r["name"] == "Helly")
        windows = helly.get("unavailable_windows", [])
        assert len(windows) == 1, "Availability window should exist"
        assert windows[0]["date"] == "2026-07-17"
        assert windows[0]["start"] == "14:00"

        # Activate multiple reps, find_available_rep_for_slot should skip Helly
        for rep in config["sales_team"]:
            if rep["name"] in ("Helly", "Vishva", "Mike", "Dana", "Sarah"):
                rep["active"] = True
        dealer.config = _json.loads(_json.dumps(config))
        flag_modified(dealer, "config")
        session.commit()

        from app.engine.router import find_available_rep_for_slot
        slot = datetime(2026, 7, 17, 14, 0, tzinfo=timezone.utc)
        result = find_available_rep_for_slot(session, dealer, config["sales_team"], slot)
        assert result is not None
        assert result["name"] != "Helly", "Helly is blocked — smart booking should skip her"
    finally:
        session.close()


@patch("app.transports.telegram.TelegramTransport.send")
def test_no_show_via_telegram_reflected_on_dashboard(mock_send, _db):
    """No-show marked via Telegram is reflected on the dashboard appointments page."""
    import app.db as db
    from app.models import Dealer, Appointment, Lead, LeadEvent, LeadState, Channel
    from datetime import datetime, timezone, timedelta

    # Seed an appointment + nudge marker
    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None

        now = datetime.now(timezone.utc)
        lead = Lead(
            dealer_id=dealer.id, name="Dashboard Check",
            phone="+177****0005", state=LeadState.APPT_SET,
            source=Channel.WEBFORM, assigned_rep="Helly",
            consent=True,
        )
        session.add(lead)
        session.commit()
        appt = Appointment(
            lead_id=lead.id, dealer_id=dealer.id,
            scheduled_for=now - timedelta(hours=3),
            status="set",
        )
        session.add(appt)
        session.commit()
        session.add(LeadEvent(
            lead_id=lead.id, dealer_id=dealer.id,
            type="no_show_nudge",
            payload={"appointment_id": appt.id},
            synced=False,
        ))
        session.commit()
    finally:
        session.close()

    # Mark no-show via Telegram
    with patch("app.telegram_free_text.classify_message") as mock_classify:
        mock_classify.return_value = {"intent": "no_show_reply", "params": {"status": "no_show"}}
        payload = {
            "message": {
                "text": "no show",
                "from": {"username": "Helly"},
                "chat": {"id": "8990699115"},
            }
        }
        client = TestClient(__import__("app.main").main.app)
        resp = client.post("/webhook/telegram", json=payload)
        assert resp.status_code == 200

    # Verify on dashboard
    cookie = _make_manager_session()
    response = client.get("/dashboard/appointments?view=list", cookies={"session": cookie})
    assert response.status_code == 200
    assert "Dashboard Check" in response.text
    assert "no_show" in response.text or "No Show" in response.text
