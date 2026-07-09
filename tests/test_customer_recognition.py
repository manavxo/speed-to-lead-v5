"""Phase 1: Cross-channel / long-window customer recognition tests.

Tests:
- Same phone texts twice within 24h → single Lead (regression guard)
- Same phone, prior SOLD lead from 3 months ago → new Lead created, prior history recorded as LeadEvent
- Same phone, different channels within 24h → recognized as same lead
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

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


def _create_lead(session, dealer, name: str, phone: str, state, vehicle: str = "",
                  hours_ago: int = 0):
    """Helper to create a lead."""
    from app.models import Lead, LeadState, Channel
    now = datetime.now(timezone.utc)
    lead = Lead(
        dealer_id=dealer.id, name=name, phone=phone,
        state=state, source=Channel.WEBFORM, vehicle_ref=vehicle or None,
        consent=True,
        created_at=now - timedelta(hours=hours_ago),
        updated_at=now - timedelta(hours=hours_ago),
    )
    session.add(lead)
    session.commit()
    return lead


def test_dedup_same_phone_within_24h(_db):
    """Same phone texts twice within 24h → single Lead returned."""
    import app.db as db
    from app.models import Dealer, Lead, LeadState
    from app.adapters.intake import NormalizedLead
    from tools.route_lead import ingest_lead
    from app.models import Channel

    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None

        # First lead
        lead1 = ingest_lead(session, dealer, NormalizedLead(
            source=Channel.WEBFORM, name="Dedup Alice", phone="+17705550001",
            vehicle_ref="Civic", consent=True,
        ))
        first_id = lead1.id

        # Second lead with same phone within 24h
        lead2 = ingest_lead(session, dealer, NormalizedLead(
            source=Channel.SMS, name="Dedup Alice", phone="+17705550001",
            vehicle_ref="Civic", consent=True,
        ))
        # Should return the SAME lead (deduped)
        assert lead2.id == first_id, f"Dedup failed: {lead2.id} != {first_id}"
    finally:
        session.close()


def test_returning_customer_creates_new_lead(_db):
    """Prior SOLD lead from 3 months ago → new Lead created with returning_customer event."""
    import app.db as db
    from app.models import Dealer, Lead, LeadState, LeadEvent, Channel
    from app.adapters.intake import NormalizedLead
    from tools.route_lead import ingest_lead

    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None

        # Create an old SOLD lead (3 months ago)
        old_lead = _create_lead(
            session, dealer, "Returning Bob", "+17705550002",
            LeadState.SOLD, vehicle="CR-V", hours_ago=2160,  # 90 days
        )

        # New lead with same phone
        new_lead = ingest_lead(session, dealer, NormalizedLead(
            source=Channel.WEBFORM, name="Bob Again", phone="+17705550002",
            vehicle_ref="Civic", consent=True,
        ))

        # Should be a NEW lead, not the old one
        assert new_lead.id != old_lead.id, "Should create a new lead, not reuse the old sold one"
        assert new_lead.name == "Bob Again"

        # Should have a returning_customer event
        rc_event = session.execute(
            select(LeadEvent).where(
                LeadEvent.lead_id == new_lead.id,
                LeadEvent.type == "returning_customer",
            )
        ).scalars().first()
        assert rc_event is not None, "Should have returning_customer LeadEvent"
        payload = rc_event.payload or {}
        assert payload.get("prior_lead_id") == old_lead.id
        assert payload.get("prior_vehicle") == "CR-V"
        assert payload.get("prior_state") == "SOLD"
    finally:
        session.close()


def test_returning_customer_lost_lead(_db):
    """Prior LOST lead from 3 months ago → new Lead created with prior history."""
    import app.db as db
    from app.models import Dealer, Lead, LeadState, LeadEvent, Channel
    from app.adapters.intake import NormalizedLead
    from tools.route_lead import ingest_lead

    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None

        old_lead = _create_lead(
            session, dealer, "Lost Carol", "+17705550003",
            LeadState.LOST, vehicle="Tucson", hours_ago=2160,
        )

        new_lead = ingest_lead(session, dealer, NormalizedLead(
            source=Channel.WEBFORM, name="Carol Returns", phone="+17705550003",
            vehicle_ref="Santa Fe", consent=True,
        ))

        assert new_lead.id != old_lead.id
        rc_event = session.execute(
            select(LeadEvent).where(
                LeadEvent.lead_id == new_lead.id,
                LeadEvent.type == "returning_customer",
            )
        ).scalars().first()
        assert rc_event is not None
        assert rc_event.payload.get("prior_lead_id") == old_lead.id
    finally:
        session.close()


def test_cross_channel_dedup_within_24h(_db):
    """Same phone, webform + SMS within 24h → same lead."""
    import app.db as db
    from app.models import Dealer, Lead, Channel
    from app.adapters.intake import NormalizedLead
    from tools.route_lead import ingest_lead

    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None

        lead1 = ingest_lead(session, dealer, NormalizedLead(
            source=Channel.WEBFORM, name="Cross Dana", phone="+17705550004",
            vehicle_ref="RAV4", consent=True,
        ))

        # Same phone via different channel
        lead2 = ingest_lead(session, dealer, NormalizedLead(
            source=Channel.SMS, name="Cross Dana", phone="+17705550004",
            vehicle_ref="RAV4", consent=True,
        ))

        assert lead2.id == lead1.id, "Cross-channel dedup should return same lead"
    finally:
        session.close()


def test_find_prior_leads_by_phone(_db):
    """find_prior_leads_by_phone returns old terminal-state leads."""
    import app.db as db
    from app.models import Dealer, LeadState, Lead
    from tools.route_lead import find_prior_leads_by_phone

    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None

        # Create an old SOLD lead
        _create_lead(session, dealer, "History Eve", "+17705550005",
                     LeadState.SOLD, vehicle="Civic", hours_ago=2160)

        # Find prior leads
        priors = find_prior_leads_by_phone(session, dealer, "+17705550005")
        assert len(priors) == 1
        assert priors[0].name == "History Eve"
    finally:
        session.close()
