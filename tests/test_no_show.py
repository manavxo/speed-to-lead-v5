"""Phase 4: No-show handling — dashboard buttons, scheduler nudge, Telegram replies.

Tests:
- Dashboard button calls the right function, appointment state updates
- Scheduler sweep with frozen clock > 2h past → exactly one nudge sent
- Appointment less than 2h past → no nudge
- Rep's reply to nudge calls mark_showed/mark_no_show
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
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


def _seed_appointment_and_lead(session, dealer_id: int, rep_name: str, hours_ago: int = 3):
    """Create a lead and appointment in the past (for nudge testing)."""
    from app.models import Lead, Appointment, LeadState, Channel

    now = datetime.now(timezone.utc)
    lead = Lead(
        dealer_id=dealer_id, name="NoShow Test", phone="+177****0001",
        state=LeadState.APPT_SET, source=Channel.WEBFORM,
        assigned_rep=rep_name, consent=True,
        created_at=now - timedelta(hours=hours_ago + 2),
        updated_at=now - timedelta(hours=hours_ago + 2),
    )
    session.add(lead)
    session.commit()
    appt = Appointment(
        lead_id=lead.id, dealer_id=dealer_id,
        scheduled_for=now - timedelta(hours=hours_ago),
        status="set",
    )
    session.add(appt)
    session.commit()
    return lead, appt


# ── Dashboard button tests ───────────────────────────────────────────────────

@patch("app.transports.telegram.TelegramTransport.send")
def test_dashboard_mark_showed(mock_send, _db):
    """Dashboard mark-showed button updates appointment and lead state."""
    import app.db as db
    from app.models import Dealer, Appointment, Lead, LeadState

    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None
        lead, appt = _seed_appointment_and_lead(session, dealer.id, "Helly")
    finally:
        session.close()

    cookie = _make_manager_session()
    client = TestClient(__import__("app.main").main.app)
    response = client.post(
        f"/dashboard/leads/{lead.id}/mark-showed",
        data={"appointment_id": appt.id},
        cookies={"session": cookie},
    )
    assert response.status_code == 200

    # Verify state updated
    session2 = db.get_session_factory()()
    try:
        updated_appt = session2.get(Appointment, appt.id)
        assert updated_appt.status == "showed"
        updated_lead = session2.get(Lead, lead.id)
        assert updated_lead.state == LeadState.SHOWED
    finally:
        session2.close()


@patch("app.transports.telegram.TelegramTransport.send")
def test_dashboard_mark_no_show(mock_send, _db):
    """Dashboard mark-no-show button updates appointment status."""
    import app.db as db
    from app.models import Dealer, Appointment, Lead

    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None
        lead, appt = _seed_appointment_and_lead(session, dealer.id, "Helly")
    finally:
        session.close()

    cookie = _make_manager_session()
    client = TestClient(__import__("app.main").main.app)
    response = client.post(
        f"/dashboard/leads/{lead.id}/mark-no-show",
        data={"appointment_id": appt.id},
        cookies={"session": cookie},
    )
    assert response.status_code == 200

    session2 = db.get_session_factory()()
    try:
        updated_appt = session2.get(Appointment, appt.id)
        assert updated_appt.status == "no_show"
    finally:
        session2.close()


# ── Scheduler nudge tests ────────────────────────────────────────────────────

@patch("app.transports.telegram.TelegramTransport.send")
def test_nudge_sends_for_overdue_appointment(mock_send, _db):
    """Appointment > 2h past → nudge sent via Telegram."""
    import app.db as db
    from app.models import Dealer
    from app.scheduler import _run_no_show_nudge_session

    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None
        lead, appt = _seed_appointment_and_lead(session, dealer.id, "Helly", hours_ago=3)
    finally:
        session.close()

    _run_no_show_nudge_session(session)
    session.close()

    # Should have sent one Telegram message
    mock_send.assert_called_once()
    call_args = mock_send.call_args
    assert "NoShow Test" in call_args[1]["body"]
    assert "show" in call_args[1]["body"].lower()


@patch("app.transports.telegram.TelegramTransport.send")
def test_nudge_only_once(mock_send, _db):
    """Running the nudge sweep twice doesn't double-nudge."""
    import app.db as db
    from app.models import Dealer
    from app.scheduler import _run_no_show_nudge_session

    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None
        lead, appt = _seed_appointment_and_lead(session, dealer.id, "Helly", hours_ago=3)
    finally:
        session.close()

    # Run twice
    _run_no_show_nudge_session(session)
    _run_no_show_nudge_session(session)
    session.close()

    # Should have sent exactly one nudge
    assert mock_send.call_count == 1


@patch("app.transports.telegram.TelegramTransport.send")
def test_nudge_not_sent_for_recent_appointment(mock_send, _db):
    """Appointment less than 2h past → no nudge."""
    import app.db as db
    from app.models import Dealer
    from app.scheduler import _run_no_show_nudge_session

    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None
        lead, appt = _seed_appointment_and_lead(session, dealer.id, "Helly", hours_ago=1)
    finally:
        session.close()

    _run_no_show_nudge_session(session)
    session.close()

    mock_send.assert_not_called()


# ── Telegram reply to nudge ──────────────────────────────────────────────────

@patch("app.transports.telegram.TelegramTransport.send")
def test_telegram_showed_reply_to_nudge(mock_send, _db):
    """Rep replies 'showed' to nudge → appointment marked showed."""
    import app.db as db
    from app.models import Dealer, Appointment, LeadEvent

    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None
        lead, appt = _seed_appointment_and_lead(session, dealer.id, "Helly", hours_ago=3)

        # Add a nudge marker so the no-show reply handler finds it
        session.add(LeadEvent(
            lead_id=lead.id, dealer_id=dealer.id, type="no_show_nudge",
            payload={"appointment_id": appt.id},
            synced=False,
        ))
        session.commit()
    finally:
        session.close()

    # Simulate Telegram reply
    with patch("app.telegram_free_text.classify_message") as mock_classify:
        mock_classify.return_value = {"intent": "no_show_reply", "params": {"status": "showed"}}
        payload = {
            "message": {
                "text": "he showed",
                "from": {"username": "Helly"},
                "chat": {"id": "8990699115"},
            }
        }
        client = TestClient(__import__("app.main").main.app)
        response = client.post("/webhook/telegram", json=payload)
        assert response.status_code == 200

    # Verify appointment was marked showed
    session2 = db.get_session_factory()()
    try:
        updated_appt = session2.get(Appointment, appt.id)
        assert updated_appt.status == "showed"
    finally:
        session2.close()


@patch("app.transports.telegram.TelegramTransport.send")
def test_telegram_no_show_reply_to_nudge(mock_send, _db):
    """Rep replies 'no show' to nudge → appointment marked no_show."""
    import app.db as db
    from app.models import Dealer, Appointment, LeadEvent

    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None
        lead, appt = _seed_appointment_and_lead(session, dealer.id, "Helly", hours_ago=3)

        session.add(LeadEvent(
            lead_id=lead.id, dealer_id=dealer.id, type="no_show_nudge",
            payload={"appointment_id": appt.id},
            synced=False,
        ))
        session.commit()
    finally:
        session.close()

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
        response = client.post("/webhook/telegram", json=payload)
        assert response.status_code == 200

    session2 = db.get_session_factory()()
    try:
        updated_appt = session2.get(Appointment, appt.id)
        assert updated_appt.status == "no_show"
    finally:
        session2.close()
