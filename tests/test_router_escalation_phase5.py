"""Phase 5: Round-robin + escalation coverage extensions.

Gaps filled:
1. Pass→pass→escalate sequence (not just the notify call)
2. Round-robin fairness with mid-rotation deactivation
3. Stuck-lead sweep tz regression guard
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.models import Channel, Dealer, Lead, LeadEvent, LeadState, Message


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def r5_engine():
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
def r5_session(r5_engine):
    TestSession = sessionmaker(bind=r5_engine, expire_on_commit=False)
    s = TestSession()
    yield s
    s.close()


@pytest.fixture
def dealer(r5_session):
    d = Dealer(
        slug="phase5-dealer",
        name="Phase 5 Test Dealer",
        timezone="America/Vancouver",
        sms_number="+177****9999",
        config={
            "dealer": {"slug": "phase5-dealer", "name": "Phase 5 Test Dealer",
                       "timezone": "America/Vancouver",
                       "hours": {"mon-fri": "09:00-19:00"}},
            "channels": {"sms_number": "+177****9999"},
            "sales_team": [
                {"name": "Alice", "phone": "+160****0001", "active": True},
                {"name": "Bob",   "phone": "+160****0002", "active": True},
                {"name": "Carol", "phone": "+160****0003", "active": True},
            ],
            "routing": {
                "strategy": "round_robin",
                "claim_timeout_min": 2,
                "escalation": ["reassign", "notify_manager"],
                "manager_phone": "+160****0000",
            },
            "lead_org": {"mode": "native"},
            "inventory": {"source": "manual", "refresh_min": 180},
        },
    )
    r5_session.add(d)
    r5_session.commit()
    r5_session.refresh(d)
    return d


# ---------------------------------------------------------------------------
# Test 1: Pass→pass→escalate sequence
# ---------------------------------------------------------------------------

def test_pass_pass_escalate_sequence(r5_session, dealer):
    """After configurable number of passes, lead escalates to manager."""
    from app.engine.router import next_rep, assign_lead, handle_pass

    sales_team = dealer.config["sales_team"]
    max_passes = 3

    lead = Lead(
        dealer_id=dealer.id, source=Channel.SMS, name="Pass Test",
        phone="+160****0101", state=LeadState.ASSIGNED,
    )
    r5_session.add(lead)
    r5_session.commit()
    r5_session.refresh(lead)

    # First pass: reassigns
    result1 = handle_pass(r5_session, lead, dealer, sales_team, "Alice",
                          max_pass_count=max_passes)
    assert result1 is not None, "First pass should return next rep"
    assert lead.pass_count == 1
    assert lead.state == LeadState.ASSIGNED

    # Second pass: reassigns
    result2 = handle_pass(r5_session, lead, dealer, sales_team,
                          lead.assigned_rep, max_pass_count=max_passes)
    assert result2 is not None, "Second pass should return next rep"
    assert lead.pass_count == 2

    # Third pass: should escalate (reaches max_pass_count)
    result3 = handle_pass(r5_session, lead, dealer, sales_team,
                          lead.assigned_rep, max_pass_count=max_passes)
    assert result3 is None, "Third pass should escalate (no rep returned)"
    assert lead.pass_count == 3
    # Should be in ESCALATED state
    assert lead.state == LeadState.ESCALATED, (
        f"Lead should be ESCALATED after {max_passes} passes, got {lead.state.value}"
    )

    # Verify an escalation event was logged
    events = r5_session.execute(
        select(LeadEvent).where(
            LeadEvent.lead_id == lead.id,
            LeadEvent.type == "state_change",
        )
    ).scalars().all()
    escalated_events = [e for e in events
                        if e.payload and e.payload.get("to") == "ESCALATED"]
    assert len(escalated_events) >= 1


# ---------------------------------------------------------------------------
# Test 2: Round-robin fairness with mid-rotation deactivation
# ---------------------------------------------------------------------------

def test_round_robin_fairness_mid_rotation_deactivation(r5_session, dealer):
    """Deactivating a rep mid-rotation doesn't skip or double-assign."""
    from app.engine.router import next_rep

    sales_team = list(dealer.config["sales_team"])  # 3 active reps
    # Initial assignments — distribute across all 3
    picks1 = [next_rep(dealer, sales_team)["name"] for _ in range(6)]
    assert picks1 == ["Alice", "Bob", "Carol", "Alice", "Bob", "Carol"], (
        f"Expected even rotation, got {picks1}"
    )

    # Carol goes inactive mid-rotation
    sales_team[2]["active"] = False  # Carol deactivated

    # Next assignments should only be Alice and Bob, evenly
    picks2 = [next_rep(dealer, sales_team)["name"] for _ in range(4)]
    assert "Carol" not in picks2, f"Deactivated rep should not appear: {picks2}"
    # With pointer at 6 (was Carol's turn), 6 % 2 = 0 => Alice, then 1 => Bob, etc.
    assert picks2 == ["Alice", "Bob", "Alice", "Bob"], (
        f"Expected even rotation among 2 active reps, got {picks2}"
    )

    # No duplicate consecutive same-rep assignment
    for i in range(1, len(picks2)):
        assert picks2[i] != picks2[i-1], (
            f"Same rep assigned consecutively: {picks2[i]} at {i-1} and {i}"
        )


# ---------------------------------------------------------------------------
# Test 3: Stuck-lead sweep tz regression guard
# ---------------------------------------------------------------------------

def test_stuck_lead_sweep_handles_naive_datetimes(r5_session, dealer):
    """Stuck-lead sweep handles naive DB datetimes (regression for d8522a5).

    The previous bug: comparing naive created_at/updated_at from SQLite
    against aware datetime.now(timezone.utc) crashed with TypeError.
    The fix added .tzinfo is None guards. This test verifies the sweep
    runs without crashing when DB has naive datetimes.
    """
    from app.scheduler import _run_stuck_lead_sweep_session

    # Create a lead with created_at notably in the past (should be flagged as stuck)
    old_time = datetime(2026, 1, 1, 0, 0, 0)  # Naive datetime — no tzinfo!
    lead = Lead(
        dealer_id=dealer.id, source=Channel.SMS, name="Stuck Lead",
        phone="+160****0202", state=LeadState.NEW,
        created_at=old_time,  # Naive — this was the crash source
    )
    r5_session.add(lead)
    r5_session.commit()

    # Create another lead stuck in ASSIGNED with naive updated_at
    lead2 = Lead(
        dealer_id=dealer.id, source=Channel.SMS, name="Stuck Assigned",
        phone="+160****0303", state=LeadState.ASSIGNED,
        assigned_rep="Alice",
        created_at=old_time,
        updated_at=old_time,  # Naive — this was also a crash source
    )
    r5_session.add(lead2)
    r5_session.commit()

    # This should NOT crash — must handle naive datetimes gracefully
    try:
        _run_stuck_lead_sweep_session(r5_session)
    except TypeError as e:
        pytest.fail(f"Stuck-lead sweep crashed with TypeError: {e}")

    # If we got here without crashing, the test passes
    assert True


def test_stuck_lead_sweep_handles_aware_datetimes(r5_session, dealer):
    """Stuck-lead sweep also works with aware datetimes (Postgres production path)."""
    from app.scheduler import _run_stuck_lead_sweep_session

    aware_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    lead = Lead(
        dealer_id=dealer.id, source=Channel.SMS, name="Aware Stuck",
        phone="+160****0404", state=LeadState.NEW,
        created_at=aware_time,
    )
    r5_session.add(lead)
    r5_session.commit()

    try:
        _run_stuck_lead_sweep_session(r5_session)
    except Exception as e:
        pytest.fail(f"Stuck-lead sweep crashed with aware datetime: {e}")

    assert True
