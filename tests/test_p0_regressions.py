"""Regression tests for the follow-up sender (P0-12).

Bug history: v4's code review (docs/11-CODE-REVIEW.md) flagged the
follow-up sender as a no-op. The actual v4 code had the fix in place
(`_handle_followup` calls `handle_turn` and `send_sms`), but the v5 build
must keep the fix. These tests pin the behavior so a future refactor
can't silently regress it to a no-op.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models import Channel, Dealer, Direction, Lead, LeadState, Message


# Minimal dealer config that the followup sender needs
DEMO_CONFIG = {
    "dealer": {
        "name": "Demo Auto Sales",
        "timezone": "America/Vancouver",
        "hours": {"mon": "09:00-18:00", "tue": "09:00-18:00", "wed": "09:00-18:00",
                  "thu": "09:00-18:00", "fri": "09:00-18:00", "sat": "10:00-17:00",
                  "sun": "closed"},
    },
    "compliance": {
        "consent_text": "Reply STOP to opt out.",
        "region": "CA-BC",
    },
    "ai": {"persona": "Test"},
}


def test_p0_12_followup_sender_actually_sends_a_message(db_session, monkeypatch):
    """The followup handler must call send_sms and persist a Message row.

    A no-op followup (the v4 bug) would just log and return without
    sending anything. We patch the network and DB to verify the side effects.
    """
    from app.scheduler import _handle_followup
    from app.db import get_session_factory

    # Set up dealer + lead in a fresh, non-terminal state
    dealer = Dealer(slug="p0-12-dealer", name="P0-12 Dealer", config=DEMO_CONFIG)
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    lead = Lead(
        dealer_id=dealer.id,
        name="P0-12 Customer",
        phone="+160****5678",
        source=Channel.SMS,
        state=LeadState.ENGAGED,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    # Patch the conversation engine so it returns canned text
    from app.engine import conversation as conv
    monkeypatch.setattr(
        conv, "handle_turn",
        lambda *a, **kw: {"text": "Just checking in!", "tools_used": []},
    )

    # Patch the SMS chokepoint to capture the call
    sent = {}
    def fake_send_sms(*args, **kwargs):
        sent["to"] = kwargs.get("to_phone") or args[1] if len(args) > 1 else None
        sent["body"] = kwargs.get("body") or args[2] if len(args) > 2 else None
        sent["lead_id"] = kwargs.get("lead_id")
        return "FAKE_SID"
    monkeypatch.setattr(
        "tools.send_sms.send_sms", fake_send_sms, raising=False,
    )
    # Also patch where scheduler imports it from
    import app.scheduler as sched
    monkeypatch.setattr(sched, "send_sms", fake_send_sms, raising=False)

    # Capture Message rows that get added
    initial_count = len(db_session.query(Message).all())

    # Fire the followup
    _handle_followup(lead.id, dealer.slug, minutes=30)

    # Assert: send_sms was called
    assert sent.get("to") is not None, (
        "P0-12 REGRESSION: _handle_followup did not call send_sms. "
        "The followup is a no-op — this is the v4 bug we fixed."
    )
    assert "checking in" in sent.get("body", "").lower(), (
        f"P0-12: send_sms was called but with wrong body. Got: {sent.get('body')!r}"
    )

    # Assert: a Message row was persisted
    final_count = len(db_session.query(Message).all())
    assert final_count == initial_count + 1, (
        f"P0-12 REGRESSION: expected 1 new Message row, got {final_count - initial_count}. "
        f"The followup sent the SMS but did not persist it."
    )

    # Assert: the persisted message is OUTBOUND direction
    new_msg = db_session.query(Message).order_by(Message.id.desc()).first()
    assert new_msg.direction == Direction.OUTBOUND
    assert new_msg.lead_id == lead.id


def test_p0_12_followup_skips_terminal_leads(db_session, monkeypatch):
    """A followup for a SOLD/LOST/OPTED_OUT lead must NOT send."""
    from app.scheduler import _handle_followup

    dealer = Dealer(slug="p0-12-terminal", name="Terminal Dealer", config=DEMO_CONFIG)
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    # SOLD lead
    sold = Lead(
        dealer_id=dealer.id,
        name="Sold Customer",
        phone="+160****9999",
        source=Channel.SMS,
        state=LeadState.SOLD,
    )
    db_session.add(sold)
    db_session.commit()
    db_session.refresh(sold)

    # Patch send_sms to detect any call
    called = {"count": 0}
    def fake_send_sms(*args, **kwargs):
        called["count"] += 1
        return "FAKE"
    import app.scheduler as sched
    monkeypatch.setattr(sched, "send_sms", fake_send_sms, raising=False)

    # Fire the followup
    _handle_followup(sold.id, dealer.slug, minutes=30)

    assert called["count"] == 0, (
        "P0-12: followup was sent to a SOLD lead. Terminal leads must be skipped."
    )
