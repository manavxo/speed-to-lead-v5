"""After-hours morning-queue: leads that arrive at night are queued and sent
first thing when the dealer reopens — never texted overnight, never sent twice.
"""
from datetime import datetime, timezone

import pytest

from app.config import settings
from app.models import (
    Channel, Dealer, Direction, Lead, LeadEvent, LeadState, Message,
)
from tools.route_lead import is_after_hours, queue_morning_followup
from app.scheduler import _run_morning_followup_session

VANCOUVER_HOURS = {
    "mon": "09:00-19:00", "tue": "09:00-19:00", "wed": "09:00-19:00",
    "thu": "09:00-19:00", "fri": "09:00-19:00", "sat": "10:00-17:00", "sun": "closed",
}

# America/Vancouver is PDT (UTC-7) in June.
NIGHT_UTC = datetime(2026, 6, 5, 6, 0, tzinfo=timezone.utc)     # 23:00 Thu Vancouver (quiet, closed)
MORNING_UTC = datetime(2026, 6, 5, 17, 0, tzinfo=timezone.utc)  # 10:00 Fri Vancouver (open)


def _config():
    return {
        "dealer": {"name": "Test Dealer", "timezone": "America/Vancouver", "hours": VANCOUVER_HOURS},
        "channels": {"sms_number": "+17780000000"},
        "compliance": {"quiet_hours": "21:00-08:00"},
    }


@pytest.fixture
def dealer(db_session):
    d = Dealer(slug="test-dealer", name="Test Dealer", timezone="America/Vancouver",
               sms_number="+17780000000", config=_config())
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d


def _make_lead(db_session, dealer):
    lead = Lead(dealer_id=dealer.id, source=Channel.SMS, name="Night Caller",
                phone="+16040001111", state=LeadState.AUTO_REPLIED, consent=True)
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)
    return lead


def _outbound_count(db_session, lead_id):
    return db_session.query(Message).filter(
        Message.lead_id == lead_id, Message.direction == Direction.OUTBOUND,
    ).count()


def _event_count(db_session, lead_id, etype):
    return db_session.query(LeadEvent).filter(
        LeadEvent.lead_id == lead_id, LeadEvent.type == etype,
    ).count()


def test_is_after_hours_respects_global_flag(monkeypatch):
    cfg = _config()
    # When quiet hours are globally disabled, nothing is deferred.
    monkeypatch.setattr(settings, "quiet_hours_disabled", True)
    assert is_after_hours(cfg, now=NIGHT_UTC) is False
    # When enforced, night is after-hours, daytime is not.
    monkeypatch.setattr(settings, "quiet_hours_disabled", False)
    assert is_after_hours(cfg, now=NIGHT_UTC) is True
    assert is_after_hours(cfg, now=MORNING_UTC) is False


def test_queue_creates_marker_with_body(db_session, dealer):
    lead = _make_lead(db_session, dealer)
    queue_morning_followup(db_session, lead, "Hi! It's the AI from Test Dealer.")
    events = db_session.query(LeadEvent).filter(
        LeadEvent.lead_id == lead.id, LeadEvent.type == "morning_queue",
    ).all()
    assert len(events) == 1
    assert events[0].payload["body"] == "Hi! It's the AI from Test Dealer."
    # Nothing was actually sent at night.
    assert _outbound_count(db_session, lead.id) == 0


def test_morning_sweep_sends_once_and_is_idempotent(db_session, dealer, monkeypatch):
    monkeypatch.setattr(settings, "quiet_hours_disabled", False)
    lead = _make_lead(db_session, dealer)
    queue_morning_followup(db_session, lead, "Good morning from Test Dealer!")

    # Before opening: sweep at night does nothing.
    _run_morning_followup_session(db_session, now=NIGHT_UTC)
    assert _outbound_count(db_session, lead.id) == 0
    assert _event_count(db_session, lead.id, "morning_sent") == 0

    # After opening: the queued message goes out exactly once.
    _run_morning_followup_session(db_session, now=MORNING_UTC)
    assert _outbound_count(db_session, lead.id) == 1
    assert _event_count(db_session, lead.id, "morning_sent") == 1

    # Running again must NOT re-send (idempotent).
    _run_morning_followup_session(db_session, now=MORNING_UTC)
    assert _outbound_count(db_session, lead.id) == 1
    assert _event_count(db_session, lead.id, "morning_sent") == 1


def test_opted_out_lead_is_not_sent(db_session, dealer, monkeypatch):
    monkeypatch.setattr(settings, "quiet_hours_disabled", False)
    lead = _make_lead(db_session, dealer)
    queue_morning_followup(db_session, lead, "Hello!")
    lead.state = LeadState.OPTED_OUT
    db_session.commit()

    _run_morning_followup_session(db_session, now=MORNING_UTC)
    assert _outbound_count(db_session, lead.id) == 0
    assert _event_count(db_session, lead.id, "morning_sent") == 0
