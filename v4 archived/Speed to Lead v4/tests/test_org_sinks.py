"""Phase 12 - Org sink tests."""

from __future__ import annotations


from app.models import Channel, Dealer, Lead, LeadEvent, LeadState
from tools.sync_crm import NativeSink, WebhookSink, EmailDigestSink, build_sink, flush_events
from sqlalchemy.orm import sessionmaker


def _make_dealer(config):
    return Dealer(slug="test", name="Test", config=config)


def test_native_sink_always_succeeds():
    sink = NativeSink()
    assert sink.push({"event_type": "test"}) is True


def test_build_sink_native():
    dealer = _make_dealer({"lead_org": {"mode": "native"}})
    assert isinstance(build_sink(dealer), NativeSink)


def test_build_sink_webhook():
    dealer = _make_dealer({"lead_org": {"mode": "webhook", "target": "https://example.com/hook"}})
    assert isinstance(build_sink(dealer), WebhookSink)


def test_build_sink_email():
    dealer = _make_dealer({"lead_org": {"mode": "email_digest", "target": "test@test.com"}})
    assert isinstance(build_sink(dealer), EmailDigestSink)


def test_build_sink_default_is_native():
    dealer = _make_dealer({})
    assert isinstance(build_sink(dealer), NativeSink)


def test_flush_events_native_sink(db_engine):
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = TestSession()

    dealer = Dealer(slug="test", name="Test", config={"lead_org": {"mode": "native"}})
    session.add(dealer)
    session.commit()

    lead = Lead(dealer_id=dealer.id, source=Channel.WEBFORM, state=LeadState.AUTO_REPLIED)
    session.add(lead)
    session.commit()

    event = LeadEvent(lead_id=lead.id, dealer_id=dealer.id, type="lead_created", payload={})
    session.add(event)
    session.commit()

    result = flush_events(session, dealer)
    assert result["pushed"] == 1
    assert result["failed"] == 0
    assert event.synced is True
    session.close()


def test_flush_events_idempotent(db_engine):
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = TestSession()

    dealer = Dealer(slug="test", name="Test", config={"lead_org": {"mode": "native"}})
    session.add(dealer)
    session.commit()

    lead = Lead(dealer_id=dealer.id, source=Channel.WEBFORM, state=LeadState.AUTO_REPLIED)
    session.add(lead)
    session.commit()

    event = LeadEvent(lead_id=lead.id, dealer_id=dealer.id, type="lead_created", payload={})
    session.add(event)
    session.commit()

    flush_events(session, dealer)
    result2 = flush_events(session, dealer)
    assert result2["pushed"] == 0
    session.close()

