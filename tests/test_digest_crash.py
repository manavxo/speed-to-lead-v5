"""1.1: Daily digest crash regression test.

send_daily_digest() in app/scheduler.py references an undefined `dealer`
variable at line ~422 (dealer.id). This test proves the bug exists,
then the fix ensures a proper Dealer lookup by slug.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.models import Dealer


@pytest.fixture
def digest_engine():
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
def digest_session(digest_engine):
    Session = sessionmaker(bind=digest_engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def seeded_dealer(digest_session):
    """Seed a minimal dealer with manager phone for digest."""
    dealer = Dealer(
        slug="premier-auto-group",
        name="Premier Auto Group",
        sms_number="+17781234567",
        config={
            "dealer": {"name": "Premier Auto Group", "timezone": "America/Vancouver"},
            "routing": {
                "manager_phone": "+16045550001",
                "digest_enabled": True,
                "digest_time": "08:00",
            },
            "channels": {"sms_number": "+17781234567"},
        },
    )
    digest_session.add(dealer)
    digest_session.commit()
    digest_session.refresh(dealer)
    return dealer


def test_send_daily_digest_does_not_crash(digest_session, seeded_dealer):
    """send_daily_digest must not crash with NameError on dealer.id.

    The function receives dealer_slug but was referencing dealer.id without
    loading the Dealer from the database. After fix, it loads the dealer
    and runs without error.
    """
    from app.scheduler import send_daily_digest

    config = seeded_dealer.config

    # send_sms is a no-op in test via DRYRUN
    with patch("tools.send_sms.send_sms") as mock_send:
        send_daily_digest(digest_session, seeded_dealer.slug, config)

    # Should have reached send_sms (or skipped due to no leads)
    # Either way — no NameError crash
    assert True


def test_send_daily_digest_skips_when_no_manager_phone(digest_session, seeded_dealer):
    """If no manager_phone, digest should return early, not crash."""
    from app.scheduler import send_daily_digest

    config = seeded_dealer.config.copy()
    config["routing"] = config.get("routing", {}).copy()
    config["routing"].pop("manager_phone", None)

    # Should return early, not crash
    send_daily_digest(digest_session, seeded_dealer.slug, config)
    # If we get here, no crash — test passes
    assert True
