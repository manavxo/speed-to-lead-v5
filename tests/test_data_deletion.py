"""Phase 2: Data deletion on request tests.

Tests:
- Deleting a lead removes Lead, Messages, Appointments, LeadEvents
- ConsentLog(action='deleted') remains afterward with the phone number
- Non-manager (rep) cannot trigger deletion (403)
- Deleting non-existent lead returns 404
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.fixture
def client(tmp_path):
    """TestClient backed by SQLite with premier-auto provisioned."""
    import app.db as db
    from app.main import _auto_provision_dealers, app

    db_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    db.init_db(db_url)
    db.get_session_factory(db_url)
    _auto_provision_dealers()
    try:
        yield TestClient(app)
    finally:
        db._engine = None
        db._SessionLocal = None


def _make_manager_session() -> str:
    from app.dashboard import _get_serializer
    return _get_serializer().dumps({
        "role": "manager", "rep_name": "", "dealer_slug": "premier-auto", "ts": 0,
    })


def _make_rep_session() -> str:
    from app.dashboard import _get_serializer
    return _get_serializer().dumps({
        "role": "rep", "rep_name": "Helly", "dealer_slug": "premier-auto", "ts": 0,
    })


def _seed_deletable_lead(client) -> int:
    """Create a lead with messages, appointment, and events. Returns lead_id."""
    import app.db as db
    from app.models import Lead, Message, Appointment, LeadEvent, LeadState, Channel, Direction

    session = db.get_session_factory()()
    try:
        from sqlalchemy import select as _sel
        from app.models import Dealer
        dealer = session.execute(_sel(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        now = datetime.now(timezone.utc)

        lead = Lead(
            dealer_id=dealer.id, name="Delete Me", phone="+17705559999",
            state=LeadState.APPT_SET, source=Channel.WEBFORM, consent=True,
        )
        session.add(lead)
        session.commit()

        msg = Message(lead_id=lead.id, direction=Direction.INBOUND, channel=Channel.SMS, body="test")
        session.add(msg)
        appt = Appointment(lead_id=lead.id, dealer_id=dealer.id,
                           scheduled_for=now + timedelta(days=1), status="set")
        session.add(appt)
        evt = LeadEvent(lead_id=lead.id, dealer_id=dealer.id, type="test", payload={}, synced=False)
        session.add(evt)
        session.commit()
        return lead.id
    finally:
        session.close()


# ── Tests ───────────────────────────────────────────────────────────────────

def test_delete_lead_removes_all_data(client):
    """Deleting a lead removes Lead, Messages, Appointments, LeadEvents."""
    import app.db as db
    from app.models import Lead, Message, Appointment, LeadEvent, ConsentLog

    lead_id = _seed_deletable_lead(client)

    cookie = _make_manager_session()
    resp = client.post(f"/dashboard/leads/{lead_id}/delete", cookies={"session": cookie})
    assert resp.status_code == 200, f"Delete failed: {resp.text[:200]}"

    session = db.get_session_factory()()
    try:
        assert session.get(Lead, lead_id) is None, "Lead should be deleted"
        # Check all related data is gone
        msgs = session.execute(select(Message).where(Message.lead_id == lead_id)).scalars().all()
        assert len(msgs) == 0, f"Messages remain: {len(msgs)}"
        appts = session.execute(select(Appointment).where(Appointment.lead_id == lead_id)).scalars().all()
        assert len(appts) == 0, f"Appointments remain: {len(appts)}"
        events = session.execute(select(LeadEvent).where(LeadEvent.lead_id == lead_id)).scalars().all()
        assert len(events) == 0, f"LeadEvents remain: {len(events)}"

        # ConsentLog should exist
        log = session.execute(
            select(ConsentLog).where(
                ConsentLog.phone == "+17705559999",
                ConsentLog.action == "deleted",
            )
        ).scalars().first()
        assert log is not None, "ConsentLog(action='deleted') should exist"
        assert log.lead_id is None, "ConsentLog.lead_id should be None after deletion"
        assert "#" in (log.text or ""), "Text should reference the deleted lead ID"
    finally:
        session.close()


def test_delete_lead_rep_forbidden(client):
    """Rep cannot trigger deletion (403)."""
    lead_id = _seed_deletable_lead(client)

    cookie = _make_rep_session()
    resp = client.post(f"/dashboard/leads/{lead_id}/delete", cookies={"session": cookie})
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"


def test_delete_nonexistent_lead_returns_404(client):
    """Deleting a lead that doesn't exist returns 404."""
    cookie = _make_manager_session()
    resp = client.post("/dashboard/leads/99999/delete", cookies={"session": cookie})
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
