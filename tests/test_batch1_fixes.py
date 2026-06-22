"""Batch-1 hardening fixes: opt-out (SMS+email), parser sanity, inventory upload,
round-robin reassignment timer. These cover the issues fixed after the audit.
"""
from __future__ import annotations

import asyncio
import io
import time
import types

import pytest
from unittest.mock import MagicMock

from app.config import settings
from app.models import (
    Channel, ConsentLog, Dealer, Lead, LeadEvent, LeadState, Vehicle,
)


# ── SMS opt-out (CASL: honor any reasonable intent, not just exact "STOP") ────

def test_sms_opt_out_matches_phrases():
    from app.main import _is_sms_opt_out
    kw = ["STOP", "STOPALL", "UNSUBSCRIBE", "ARRET"]
    assert _is_sms_opt_out("STOP", kw)
    assert _is_sms_opt_out("stop", kw)
    assert _is_sms_opt_out("please stop texting me", kw)
    assert _is_sms_opt_out("take me off your list", kw)
    assert _is_sms_opt_out("unsubscribe me", kw)
    # Normal messages must NOT trip it.
    assert not _is_sms_opt_out("can I stop by the dealership this afternoon to look at the civic?", kw)
    assert not _is_sms_opt_out("yes please book me for tuesday", kw)
    assert not _is_sms_opt_out("", kw)


# ── Email opt-out ─────────────────────────────────────────────────────────────

def test_email_opt_out_detection():
    from app.adapters.intake.email_ingest import _is_email_opt_out
    assert _is_email_opt_out("STOP")
    assert _is_email_opt_out("Please unsubscribe me from these emails")
    assert _is_email_opt_out("remove me from your list")
    assert not _is_email_opt_out("Yes, I'm interested — when can I come see the truck?")
    assert not _is_email_opt_out("")


# ── Generic parser must not treat greetings as the customer name ──────────────

def test_generic_parser_skips_greeting_as_name():
    from app.adapters.intake.email_parsers.generic import parse_generic
    lead = parse_generic("Hi there\nI'd like info on the 2022 Civic\nreach me at buyer@example.com")
    assert lead is not None
    assert lead.email == "buyer@example.com"
    assert lead.name != "Hi there"  # greeting must not become the name


# ── Email reply opt-out path actually opts the lead out ──────────────────────

def test_email_reply_stop_opts_out_lead(db_session):
    from app.adapters.intake.email_ingest import _handle_email_reply

    dealer = Dealer(slug="d1", name="D1", config={})
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    lead = Lead(dealer_id=dealer.id, source=Channel.EMAIL, name="Buyer",
                email="buyer@example.com", state=LeadState.ASSIGNED, assigned_rep="Helly")
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    fake_mail = MagicMock()
    handled = _handle_email_reply(
        db_session, lead, "buyer@example.com", "Please STOP emailing me",
        "Re: your car", fake_mail, "42",
    )
    assert handled is True
    db_session.refresh(lead)
    assert lead.state == LeadState.OPTED_OUT
    opt = db_session.query(ConsentLog).filter(
        ConsentLog.lead_id == lead.id, ConsentLog.action == "opted_out",
    ).first()
    assert opt is not None
    fake_mail.store.assert_called_once()  # email marked seen


# ── Round-robin reassignment resets the escalation timer ─────────────────────

def test_reassignment_emits_fresh_assigned_event(db_session, monkeypatch):
    monkeypatch.setattr(settings, "outbound_enabled", False)  # dry-run notify
    from app.engine.router import assign_lead

    dealer = Dealer(slug="d2", name="D2", config={}, round_robin_pointer=0)
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    team = [
        {"name": "A", "phone": "+16040000001", "active": True, "notify_backend": "telegram"},
        {"name": "B", "phone": "+16040000002", "active": True, "notify_backend": "telegram"},
    ]
    lead = Lead(dealer_id=dealer.id, source=Channel.SMS, phone="+16045551234",
                state=LeadState.AUTO_REPLIED)
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    # First assignment: AUTO_REPLIED -> ASSIGNED (rep A)
    assign_lead(db_session, lead, dealer, team)
    db_session.refresh(lead)
    first_rep = lead.assigned_rep

    # Reassignment (a pass): already ASSIGNED -> must still log a fresh event
    assign_lead(db_session, lead, dealer, team)
    db_session.refresh(lead)

    assigned_events = db_session.query(LeadEvent).filter(
        LeadEvent.lead_id == lead.id,
        LeadEvent.type == "state_change",
    ).all()
    to_assigned = [e for e in assigned_events if (e.payload or {}).get("to") == "ASSIGNED"]
    assert len(to_assigned) >= 2, "reassignment must emit a fresh ASSIGNED event to reset the timer"
    assert lead.assigned_rep != first_rep  # round-robin advanced to the next rep


# ── Inventory upload actually upserts vehicles (regression: Vehicle import) ───

def test_inventory_upload_creates_vehicles(db_session, monkeypatch):
    import app.dashboard as dash
    from app.dashboard import _get_serializer, upload_inventory

    dealer = Dealer(slug="upload-dealer", name="Upload Dealer", config={})
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    # Route uses the module session factory + cookie lookup — point both at our test session.
    monkeypatch.setattr(dash, "_get_session", lambda: db_session)

    token = _get_serializer().dumps(
        {"role": "manager", "rep_name": "Manager", "dealer_slug": "upload-dealer", "ts": time.time()}
    )
    request = types.SimpleNamespace(cookies={"session": token})

    # Capitalized headers — the normal export casing that used to be rejected.
    csv_bytes = (
        b"Stock_No,Year,Make,Model,Trim,Body,Price,Mileage\n"
        b"A100,2022,Honda,Civic,Sport,Sedan,18900,48000\n"
        b"BADROW,notayear,Toyota,Corolla,,Sedan,15000,30000\n"   # bad year -> row error
    )
    upload = MagicMock()
    upload.filename = "inventory.csv"

    async def _read():
        return csv_bytes
    upload.read = _read

    resp = asyncio.run(upload_inventory(request, upload, {"role": "manager", "dealer_slug": "upload-dealer"}))
    assert resp.status_code == 200
    body = resp.body.decode()
    assert "1 vehicles uploaded" in body          # the good row upserted
    assert "error" in body.lower()                # the bad row reported, not silently dropped

    veh = db_session.query(Vehicle).filter(
        Vehicle.dealer_id == dealer.id, Vehicle.stock_no == "A100",
    ).first()
    assert veh is not None
    assert veh.make == "Honda" and veh.model == "Civic" and veh.price == 18900
