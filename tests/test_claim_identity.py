"""3.2: handle_claim rep identity verification tests.

Currently, any rep can claim any ASSIGNED lead regardless of who it's
assigned to. This test proves the fix: handle_claim must verify the
claiming rep matches lead.assigned_rep.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.models import Channel, Dealer, Lead, LeadState


@pytest.fixture
def claim_engine():
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
def claim_session(claim_engine):
    Session = sessionmaker(bind=claim_engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def claim_dealer(claim_session):
    dealer = Dealer(
        slug="claim-test",
        name="Claim Test Auto",
        sms_number="+17781234567",
        config={},
    )
    claim_session.add(dealer)
    claim_session.commit()
    claim_session.refresh(dealer)
    return dealer


def _create_lead(session, dealer, *, state=LeadState.ASSIGNED, assigned_rep="Mike", phone="+16045550001"):
    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.SMS,
        name="Test Customer",
        phone=phone,
        state=state,
        assigned_rep=assigned_rep,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return lead


def test_claim_by_assigned_rep_succeeds(claim_session, claim_dealer):
    """The assigned rep can claim their own lead."""
    from app.engine.router import handle_claim

    lead = _create_lead(claim_session, claim_dealer, assigned_rep="Mike")
    result = handle_claim(claim_session, lead, "Mike")

    claim_session.expire_all()
    lead = claim_session.get(Lead, lead.id)
    assert lead.state == LeadState.CLAIMED


def test_claim_by_wrong_rep_raises(claim_session, claim_dealer):
    """A rep that is NOT the assigned rep should NOT be able to claim."""
    from app.engine.router import handle_claim

    lead = _create_lead(claim_session, claim_dealer, assigned_rep="Mike")

    with pytest.raises(ValueError, match="assigned to"):
        handle_claim(claim_session, lead, "Dana")

    # Lead should still be ASSIGNED to Mike
    claim_session.expire_all()
    lead = claim_session.get(Lead, lead.id)
    assert lead.state == LeadState.ASSIGNED
    assert lead.assigned_rep == "Mike"


def test_claim_unassigned_lead_succeeds(claim_session, claim_dealer):
    """If no rep is assigned (assigned_rep is None), any rep can claim."""
    from app.engine.router import handle_claim

    lead = _create_lead(claim_session, claim_dealer, assigned_rep=None)
    result = handle_claim(claim_session, lead, "Dana")

    claim_session.expire_all()
    lead = claim_session.get(Lead, lead.id)
    assert lead.state == LeadState.CLAIMED
