"""3.3: Transaction safety tests for ingest_lead().

If the AI follow-up fails after the lead is committed, the lead should
be rolled back entirely — not left in AUTO_REPLIED with no follow-up.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.adapters.intake import NormalizedLead
from app.models import Channel, Dealer, Lead


@pytest.fixture
def tx_engine():
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
def tx_session(tx_engine):
    Session = sessionmaker(bind=tx_engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def tx_dealer(tx_session):
    dealer = Dealer(
        slug="tx-test",
        name="Transaction Test Auto",
        sms_number="+17781234567",
        config={
            "dealer": {"name": "Transaction Test Auto", "timezone": "America/Vancouver"},
            "channels": {"sms_number": "+17781234567"},
            "compliance": {
                "consent_text": "By submitting you agree. Reply STOP to opt out.",
            },
        },
    )
    tx_session.add(dealer)
    tx_session.commit()
    tx_session.refresh(dealer)
    return dealer


def test_ingest_lead_rolls_back_on_ai_followup_failure(tx_session, tx_dealer):
    """If AI follow-up raises, the lead should NOT exist in the database."""
    from tools.route_lead import ingest_lead

    lead_data = NormalizedLead(
        source=Channel.WEBFORM,
        name="Jane Doe",
        phone="+16045559999",
        email="jane@example.com",
        vehicle_ref=None,
        consent=True,
        raw={},
    )

    now = datetime(2026, 6, 20, 14, 0, tzinfo=timezone.utc)

    # Mock handle_turn to simulate AI failure
    with patch("app.engine.conversation.handle_turn") as mock_handle_turn:
        mock_handle_turn.side_effect = RuntimeError("AI API timeout simulated")

        with pytest.raises(RuntimeError, match="AI API timeout simulated"):
            ingest_lead(tx_session, tx_dealer, lead_data, now=now)

    # Verify NO lead was created (rollback happened)
    leads = tx_session.execute(select(Lead)).scalars().all()
    assert len(leads) == 0, (
        f"Expected 0 leads after rollback, found {len(leads)}. "
        f"Lead was committed despite AI failure."
    )
