"""Phase 1: Rep availability — unavailability windows.

Tests:
- Adding a window via the dashboard endpoint persists it in dealer.config.
- A malformed window (bad date, end before start) is rejected.
- SalesRep validates unavailable_windows at YAML load time.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select


def _make_manager_session() -> str:
    from app.dashboard import _get_serializer
    return _get_serializer().dumps({
        "role": "manager",
        "rep_name": "",
        "dealer_slug": "premier-auto",
        "ts": 0,
    })


def _make_rep_session(rep_name: str = "Helly") -> str:
    from app.dashboard import _get_serializer
    return _get_serializer().dumps({
        "role": "rep",
        "rep_name": rep_name,
        "dealer_slug": "premier-auto",
        "ts": 0,
    })


@pytest.fixture
def client(tmp_path):
    """TestClient backed by a real temp-file SQLite DB with premier-auto provisioned."""
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


# ── Actual tests ─────────────────────────────────────────────────────────────

def test_availability_add_window_persists(client):
    """Adding a window via POST /team/Helly/unavailable persists it in dealer config."""
    import app.db as db
    from app.models import Dealer

    cookie = _make_manager_session()
    response = client.post(
        "/dashboard/team/Helly/unavailable",
        data={"date": "2026-07-15", "start": "14:00", "end": "16:00", "note": "dentist"},
        cookies={"session": cookie},
    )
    assert response.status_code == 200

    # Verify it persisted in dealer.config
    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None
        config = dealer.config or {}
        helly = next(r for r in config.get("sales_team", []) if r.get("name") == "Helly")
        windows = helly.get("unavailable_windows", [])
        assert len(windows) == 1
        assert windows[0]["date"] == "2026-07-15"
        assert windows[0]["start"] == "14:00"
        assert windows[0]["end"] == "16:00"
        assert windows[0]["note"] == "dentist"
    finally:
        session.close()


def test_availability_malformed_date_rejected(client):
    """Bad date format returns 400."""
    cookie = _make_manager_session()
    response = client.post(
        "/dashboard/team/Helly/unavailable",
        data={"date": "not-a-date", "start": "14:00", "end": "16:00"},
        cookies={"session": cookie},
    )
    assert response.status_code == 400
    assert "Invalid window" in response.text


def test_availability_malformed_time_rejected(client):
    """Bad time format returns 400."""
    cookie = _make_manager_session()
    response = client.post(
        "/dashboard/team/Helly/unavailable",
        data={"date": "2026-07-15", "start": "2pm", "end": "4pm"},
        cookies={"session": cookie},
    )
    assert response.status_code == 400
    assert "Invalid window" in response.text


def test_availability_end_before_start_rejected(client):
    """End time before start time returns 400."""
    cookie = _make_manager_session()
    response = client.post(
        "/dashboard/team/Helly/unavailable",
        data={"date": "2026-07-15", "start": "16:00", "end": "14:00"},
        cookies={"session": cookie},
    )
    assert response.status_code == 400
    assert "Invalid window" in response.text
    assert "after" in response.text.lower()


def test_availability_unknown_rep_returns_404(client):
    """Unknown rep name returns 404."""
    cookie = _make_manager_session()
    response = client.post(
        "/dashboard/team/NoOne/unavailable",
        data={"date": "2026-07-15", "start": "14:00", "end": "16:00"},
        cookies={"session": cookie},
    )
    assert response.status_code == 404


def test_availability_requires_auth(client):
    """Unauthenticated request returns 401/redirect."""
    response = client.post(
        "/dashboard/team/Helly/unavailable",
        data={"date": "2026-07-15", "start": "14:00", "end": "16:00"},
        follow_redirects=False,
    )
    assert response.status_code in (303, 401)


def test_availability_rep_cannot_add(client):
    """Rep role cannot add availability (manager-only) — including for their own name."""
    cookie = _make_rep_session("Helly")
    response = client.post(
        "/dashboard/team/Helly/unavailable",
        data={"date": "2026-07-15", "start": "14:00", "end": "16:00"},
        cookies={"session": cookie},
    )
    assert response.status_code == 403


def test_availability_rep_cannot_remove(client):
    """Rep role cannot remove another rep's (or their own) availability window."""
    cookie = _make_manager_session()
    client.post(
        "/dashboard/team/Helly/unavailable",
        data={"date": "2026-07-15", "start": "14:00", "end": "16:00"},
        cookies={"session": cookie},
    )

    rep_cookie = _make_rep_session("Helly")
    response = client.post(
        "/dashboard/team/Helly/unavailable/remove",
        data={"index": 0},
        cookies={"session": rep_cookie},
    )
    assert response.status_code == 403


def test_availability_remove_window(client):
    """Removing a window by index works."""
    import app.db as db
    from app.models import Dealer
    import json as _json

    # First add a window
    cookie = _make_manager_session()
    client.post(
        "/dashboard/team/Helly/unavailable",
        data={"date": "2026-07-15", "start": "14:00", "end": "16:00"},
        cookies={"session": cookie},
    )
    # Add a second one
    client.post(
        "/dashboard/team/Helly/unavailable",
        data={"date": "2026-07-16", "start": "09:00", "end": "12:00"},
        cookies={"session": cookie},
    )

    # Remove the first one (index 0)
    response = client.post(
        "/dashboard/team/Helly/unavailable/remove",
        data={"index": 0},
        cookies={"session": cookie},
    )
    assert response.status_code == 200

    # Verify only the second window remains
    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        helly = next(r for r in (dealer.config or {}).get("sales_team", []) if r.get("name") == "Helly")
        windows = helly.get("unavailable_windows", [])
        assert len(windows) == 1
        assert windows[0]["date"] == "2026-07-16"
    finally:
        session.close()


def test_availability_yaml_load_validates_windows():
    """SalesRep with unavailable_windows loads and validates correctly."""
    from app.config import SalesRep

    rep = SalesRep(
        name="TestRep",
        phone="+17705551234",
        unavailable_windows=[
            {"date": "2026-07-15", "start": "14:00", "end": "16:00", "note": "dentist"},
        ],
    )
    assert len(rep.unavailable_windows) == 1
    assert rep.unavailable_windows[0].date == "2026-07-15"
    assert rep.unavailable_windows[0].start == "14:00"
    assert rep.unavailable_windows[0].end == "16:00"


def test_availability_yaml_load_rejects_bad_date():
    """SalesRep with malformed date in unavailable_windows raises."""
    from app.config import SalesRep
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SalesRep(
            name="TestRep",
            phone="+17705551234",
            unavailable_windows=[
                {"date": "bad-date", "start": "14:00", "end": "16:00"},
            ],
        )
