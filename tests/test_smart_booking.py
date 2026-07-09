"""Phase 3: Smart booking pairing — per-rep slot checks.

Tests:
- One rep blocked, one free → book with free rep
- Two customers, same time, two free reps → both booked, different reps
- All reps blocked → booking fails
- No windows → round-robin fairness preserved
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
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


def test_smart_booking_one_blocked_one_free(_db):
    """One rep blocked 2-4pm Friday, one free — Friday 2pm picks the free rep."""
    import app.db as db
    from app.models import Dealer
    from app.engine.router import find_available_rep_for_slot
    import json as _json
    from sqlalchemy.orm.attributes import flag_modified

    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None
        config = dealer.config or {}

        # Block Helly at 2-4pm on a future Friday, activate Mike
        for rep in config.get("sales_team", []):
            if rep["name"] == "Helly":
                rep["unavailable_windows"] = [
                    {"date": "2026-07-17", "start": "14:00", "end": "16:00", "note": "dentist"},
                ]
            if rep["name"] == "Mike":
                rep["active"] = True

        dealer.config = _json.loads(_json.dumps(config))
        flag_modified(dealer, "config")
        session.commit()

        friday_2pm = datetime(2026, 7, 17, 14, 0, tzinfo=timezone.utc)
        result = find_available_rep_for_slot(session, dealer, config["sales_team"], friday_2pm)
        assert result is not None, "Should find an available rep"
        assert result["name"] != "Helly", "Helly is blocked at this time"
        assert result["name"] in ("Mike", "Vishva", "Dana", "Sarah"), "Should pick an active free rep"
    finally:
        session.close()


def test_smart_booking_two_customers_same_time(_db):
    """Two customers request the same slot with free reps — each gets a different rep."""
    import app.db as db
    from app.models import Dealer, Lead, Appointment, LeadState, Channel
    from app.engine.router import find_available_rep_for_slot
    import json as _json
    from sqlalchemy.orm.attributes import flag_modified

    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None
        config = dealer.config or {}

        # Activate multiple reps, no blocks
        for rep in config.get("sales_team", []):
            rep["active"] = True
            rep["unavailable_windows"] = []

        dealer.config = _json.loads(_json.dumps(config))
        flag_modified(dealer, "config")
        session.commit()
        session.refresh(dealer)

        slot = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)

        # First request
        rep1 = find_available_rep_for_slot(session, dealer, config["sales_team"], slot)
        assert rep1 is not None

        # Occupy rep1 with an appointment at this slot
        lead1 = Lead(
            dealer_id=dealer.id, name="Customer A", phone="+177****0001",
            state=LeadState.NEW, source=Channel.WEBFORM, consent=True,
        )
        session.add(lead1)
        session.commit()
        appt1 = Appointment(lead_id=lead1.id, dealer_id=dealer.id, scheduled_for=slot, status="set")
        session.add(appt1)
        session.commit()
        lead1.assigned_rep = rep1["name"]
        session.commit()

        # Second request — same slot
        session.refresh(dealer)
        rep2 = find_available_rep_for_slot(session, dealer, config["sales_team"], slot)
        assert rep2 is not None, "Second customer should also find a rep"
        assert rep2["name"] != rep1["name"], "Second customer should get a different rep"
    finally:
        session.close()


def test_smart_booking_all_reps_blocked(_db):
    """All reps blocked → no rep available."""
    import app.db as db
    from app.models import Dealer
    from app.engine.router import find_available_rep_for_slot
    import json as _json
    from sqlalchemy.orm.attributes import flag_modified

    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None
        config = dealer.config or {}

        slot = datetime(2026, 7, 17, 14, 0, tzinfo=timezone.utc)
        for rep in config.get("sales_team", []):
            rep["active"] = True
            rep["unavailable_windows"] = [
                {"date": "2026-07-17", "start": "14:00", "end": "16:00", "note": "blocked"},
            ]

        dealer.config = _json.loads(_json.dumps(config))
        flag_modified(dealer, "config")
        session.commit()

        result = find_available_rep_for_slot(session, dealer, config["sales_team"], slot)
        assert result is None, "No rep should be available when all are blocked"
    finally:
        session.close()


def test_smart_booking_no_windows_round_robin(_db):
    """When no reps have unavailability windows, round-robin fairness is preserved."""
    import app.db as db
    from app.models import Dealer
    from app.engine.router import find_available_rep_for_slot
    import json as _json
    from sqlalchemy.orm.attributes import flag_modified

    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None
        config = dealer.config or {}

        for rep in config.get("sales_team", []):
            rep["active"] = True
            rep["unavailable_windows"] = []

        dealer.config = _json.loads(_json.dumps(config))
        flag_modified(dealer, "config")
        session.commit()

        slot = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)
        names = set()
        for _ in range(3):
            session.refresh(dealer)
            rep = find_available_rep_for_slot(session, dealer, config["sales_team"], slot)
            assert rep is not None
            names.add(rep["name"])

        assert len(names) >= 2, "Round-robin should assign at least 2 different reps in 3 calls"
    finally:
        session.close()
