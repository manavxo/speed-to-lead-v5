"""Regression tests for the 2026-07-09 security review:

1. Telegram /start deep link requires the rep's PIN — a dealer_slug + rep_name
   alone (both visible in shared dashboard URLs / the sales-team dropdown)
   must not be enough to hijack a rep's lead-notification channel.
2. POST /dashboard/team (add team member) is manager-only.
3. POST /dashboard/leads/{id}/mark-showed and mark-no-show enforce the same
   rep-ownership check (_check_lead_access) as mark-sold/mark-lost.
4. POST /dashboard/team/{rep_name}/unavailable(/remove) is manager-only.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.fixture
def client(tmp_path):
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


def _make_rep_session(rep_name: str) -> str:
    from app.dashboard import _get_serializer
    return _get_serializer().dumps({
        "role": "rep", "rep_name": rep_name, "dealer_slug": "premier-auto", "ts": 0,
    })


# ── 1. Telegram /start PIN requirement ──────────────────────────────────────

@patch("app.transports.telegram.TelegramTransport.send")
def test_telegram_start_without_pin_does_not_bind(mock_send, client):
    """dealer_slug__rep_name with no PIN must not bind the chat_id (old format)."""
    payload = {"message": {"text": "/start premier-auto__Helly", "chat": {"id": "999999"}}}
    r = client.post("/webhook/telegram", json=payload)
    assert r.status_code == 200

    import app.db as db
    from app.models import Dealer
    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        helly = next(rep for rep in dealer.config["sales_team"] if rep["name"] == "Helly")
        assert helly["telegram_chat_id"] != "999999"
    finally:
        session.close()


@patch("app.transports.telegram.TelegramTransport.send")
def test_telegram_start_with_wrong_pin_does_not_bind(mock_send, client):
    """An attacker guessing the wrong PIN must not hijack the rep's chat_id."""
    payload = {"message": {"text": "/start premier-auto__Helly__0000", "chat": {"id": "999999"}}}
    r = client.post("/webhook/telegram", json=payload)
    assert r.status_code == 200

    import app.db as db
    from app.models import Dealer
    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        helly = next(rep for rep in dealer.config["sales_team"] if rep["name"] == "Helly")
        assert helly["telegram_chat_id"] != "999999"
    finally:
        session.close()


@patch("app.transports.telegram.TelegramTransport.send")
def test_telegram_start_with_correct_pin_binds(mock_send, client):
    """The rep's own PIN (from premier-auto.yaml: Helly=7721) legitimately binds chat_id."""
    payload = {"message": {"text": "/start premier-auto__Helly__7721", "chat": {"id": "555555"}}}
    r = client.post("/webhook/telegram", json=payload)
    assert r.status_code == 200

    import app.db as db
    from app.models import Dealer
    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        helly = next(rep for rep in dealer.config["sales_team"] if rep["name"] == "Helly")
        assert helly["telegram_chat_id"] == "555555"
    finally:
        session.close()


# ── 2. add_team_member is manager-only ──────────────────────────────────────

def test_rep_cannot_add_team_member(client):
    cookie = _make_rep_session("Helly")
    r = client.post(
        "/dashboard/team",
        data={"name": "Backdoor", "phone": "+16045550199"},
        cookies={"session": cookie},
    )
    assert r.status_code == 403

    import app.db as db
    from app.models import Dealer
    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        names = [rep["name"] for rep in dealer.config["sales_team"]]
        assert "Backdoor" not in names
    finally:
        session.close()


def test_manager_can_add_team_member(client):
    cookie = _make_manager_session()
    r = client.post(
        "/dashboard/team",
        data={"name": "NewRep", "phone": "+16045550199"},
        cookies={"session": cookie},
    )
    assert r.status_code == 200

    import app.db as db
    from app.models import Dealer
    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        names = [rep["name"] for rep in dealer.config["sales_team"]]
        assert "NewRep" in names
    finally:
        session.close()


# ── 3. mark-showed / mark-no-show enforce rep ownership ─────────────────────

def _seed_appointment_and_lead(session, dealer_id: int, rep_name: str):
    from app.models import Lead, Appointment, LeadState, Channel

    now = datetime.now(timezone.utc)
    lead = Lead(
        dealer_id=dealer_id, name="Ownership Test", phone="+177****0002",
        state=LeadState.APPT_SET, source=Channel.WEBFORM,
        assigned_rep=rep_name, consent=True,
        created_at=now - timedelta(hours=5), updated_at=now - timedelta(hours=5),
    )
    session.add(lead)
    session.commit()
    appt = Appointment(lead_id=lead.id, dealer_id=dealer_id, scheduled_for=now - timedelta(hours=3), status="set")
    session.add(appt)
    session.commit()
    return lead, appt


@patch("app.transports.telegram.TelegramTransport.send")
def test_other_rep_cannot_mark_showed(mock_send, client):
    """A rep not assigned to the lead cannot mark another rep's appointment showed."""
    import app.db as db
    from app.models import Dealer

    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        lead, appt = _seed_appointment_and_lead(session, dealer.id, "Helly")
    finally:
        session.close()

    cookie = _make_rep_session("SomeoneElse")
    r = client.post(
        f"/dashboard/leads/{lead.id}/mark-showed",
        data={"appointment_id": appt.id},
        cookies={"session": cookie},
    )
    assert r.status_code == 403


@patch("app.transports.telegram.TelegramTransport.send")
def test_other_rep_cannot_mark_no_show(mock_send, client):
    import app.db as db
    from app.models import Dealer

    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        lead, appt = _seed_appointment_and_lead(session, dealer.id, "Helly")
    finally:
        session.close()

    cookie = _make_rep_session("SomeoneElse")
    r = client.post(
        f"/dashboard/leads/{lead.id}/mark-no-show",
        data={"appointment_id": appt.id},
        cookies={"session": cookie},
    )
    assert r.status_code == 403


@patch("app.transports.telegram.TelegramTransport.send")
def test_assigned_rep_can_mark_showed(mock_send, client):
    """The rep actually assigned to the lead still can."""
    import app.db as db
    from app.models import Dealer

    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        lead, appt = _seed_appointment_and_lead(session, dealer.id, "Helly")
    finally:
        session.close()

    cookie = _make_rep_session("Helly")
    r = client.post(
        f"/dashboard/leads/{lead.id}/mark-showed",
        data={"appointment_id": appt.id},
        cookies={"session": cookie},
    )
    assert r.status_code == 200
