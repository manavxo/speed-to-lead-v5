"""Regression (F7/F4): lead-facing SMS must persist recipient_role='customer'.

The CASL-footer dedup (main.py) counts customer-tagged outbound messages, and
the dashboard thread filter excludes non-customer messages. If send_sms logs
these as NULL (the original bug), the footer is appended to every message and
the thread filter only works by accident.
"""
from __future__ import annotations


def test_outbound_sms_tagged_recipient_role_customer(db_session, monkeypatch):
    from app.models import Dealer, Lead, LeadState, Channel, Message
    from tools.send_sms import send_sms

    monkeypatch.setattr("app.config.settings.outbound_enabled", False, raising=False)

    dealer = Dealer(slug="f7-dealer", name="F7 Dealer", config={})
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    lead = Lead(
        dealer_id=dealer.id, name="F7 Customer", phone="+17780001234",
        source=Channel.SMS, state=LeadState.ENGAGED, consent=True,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    for body in ("First message", "Second message"):
        send_sms(db_session, to=lead.phone, body=body, from_number="+17787623122",
                 dealer_config={}, lead=lead)

    customer_msgs = [m for m in db_session.query(Message).filter(
        Message.lead_id == lead.id).all() if m.recipient_role == "customer"]
    assert len(customer_msgs) == 2, (
        "outbound SMS not tagged recipient_role='customer' — F7 footer dedup "
        f"and F4 filter would break. Got: {[m.recipient_role for m in customer_msgs]}"
    )
