"""1.3: pass_count persistence regression tests.

pass_count is currently set via getattr(lead, "pass_count", 0) + 1 in
app/engine/router.py. This test proves it persists across session refreshes.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.models import Channel, Dealer, Lead, LeadState


@pytest.fixture
def pc_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def pc_session(pc_engine):
    Session = sessionmaker(bind=pc_engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def pc_dealer(pc_session):
    dealer = Dealer(
        slug="pass-count-test",
        name="Pass Count Test Auto",
        sms_number="+17781234567",
        config={
            "dealer": {"name": "Pass Count Test Auto", "timezone": "America/Vancouver"},
            "routing": {"manager_phone": "+16045550001"},
            "sales_team": [
                {"name": "Mike", "phone": "+16045550001", "active": True},
                {"name": "Dana", "phone": "+16045550002", "active": True},
            ],
            "channels": {"sms_number": "+17781234567"},
        },
    )
    pc_session.add(dealer)
    pc_session.commit()
    pc_session.refresh(dealer)
    return dealer


@pytest.fixture
def pc_lead(pc_session, pc_dealer):
    lead = Lead(
        dealer_id=pc_dealer.id,
        source=Channel.SMS,
        name="Test Customer",
        phone="+16045559999",
        state=LeadState.ASSIGNED,
        assigned_rep="Mike",
    )
    pc_session.add(lead)
    pc_session.commit()
    pc_session.refresh(lead)
    return lead


def test_pass_count_defaults_to_zero(pc_session, pc_lead):
    """Newly created lead should have pass_count = 0."""
    assert pc_lead.pass_count == 0


def test_pass_count_increments_across_session_refresh(pc_engine, pc_session, pc_dealer, pc_lead, monkeypatch):
    """pass_count should persist after session close + reopen.
    
    This simulates what happens when handle_pass() is called, then
    the session is closed and a new one is opened (e.g., across requests).
    """
    from app.engine.router import handle_pass

    # Mock notify_rep to avoid real sends
    monkeypatch.setattr(
        "tools.notify_rep.notify_rep",
        lambda *a, **kw: type("R", (), {
            "success": True, "backend": "dry_run",
            "message_sid": None, "dry_run": True, "error": None,
        })(),
    )

    sales_team = pc_dealer.config["sales_team"]

    # Pass the lead once via handle_pass
    handle_pass(pc_session, pc_lead, pc_dealer, sales_team, rep_name="Mike", max_pass_count=5)
    pc_session.commit()

    lead_id = pc_lead.id

    # Close and reopen session
    pc_session.close()
    Session = sessionmaker(bind=pc_engine, expire_on_commit=False)
    new_session = Session()

    try:
        reloaded = new_session.get(Lead, lead_id)
        assert reloaded is not None, "Lead should still exist after session refresh"
        # pass_count should be 1 after the first pass
        assert reloaded.pass_count == 1, (
            f"Expected pass_count=1 after first pass, got {reloaded.pass_count}"
        )
    finally:
        new_session.close()


def test_pass_count_reaches_max_and_escalates(pc_session, pc_dealer, pc_lead, monkeypatch):
    """After max_pass_count passes, pass_count should be persisted at that value."""
    from app.engine.router import handle_pass

    notify_calls = []
    monkeypatch.setattr(
        "tools.notify_rep.notify_rep",
        lambda *a, **kw: (
            notify_calls.append(dict(kw.get("payload", {}))),
            type("R", (), {
                "success": True, "backend": "dry_run",
                "message_sid": None, "dry_run": True, "error": None,
            })(),
        )[-1],
    )

    sales_team = pc_dealer.config["sales_team"]

    # Pass until escalation (max_pass_count=3, so 3 passes)
    handle_pass(pc_session, pc_lead, pc_dealer, sales_team, rep_name="Mike", max_pass_count=3)
    handle_pass(pc_session, pc_lead, pc_dealer, sales_team, rep_name="Mike", max_pass_count=3)
    handle_pass(pc_session, pc_lead, pc_dealer, sales_team, rep_name="Mike", max_pass_count=3)

    pc_session.expire_all()
    lead = pc_session.get(Lead, pc_lead.id)
    assert lead.pass_count >= 3, f"Expected pass_count >= 3, got {lead.pass_count}"
    assert lead.state == LeadState.ESCALATED, f"Expected ESCALATED after max passes, got {lead.state}"
