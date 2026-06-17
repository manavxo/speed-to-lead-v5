"""Tool: ingest a normalized lead and kick off the speed-to-lead flow.

Persist Lead (NEW) -> resolve vehicle_ref against the vehicles table -> send the instant SMS
auto-reply (AUTO_REPLIED) -> assign round-robin + WhatsApp claim ping (ASSIGNED) -> schedule
escalation. This is the <60s core loop.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.intake import NormalizedLead
from app.engine.lifecycle import transition
from app.models import Channel, ConsentLog, Direction, Lead, LeadState, Message
from tools.check_inventory import resolve_vehicle

logger = logging.getLogger("speed-to-lead.route_lead")


def _exec(session: Session, stmt):
    return session.execute(stmt).scalars()


def _auto_reply_text(dealer_config: dict, vehicle=None) -> str:
    """Generate an auto-reply message."""
    dealer_name = dealer_config.get("dealer", {}).get("name", "us")
    consent_text = dealer_config.get("compliance", {}).get(
        "consent_text",
        f"By submitting you agree to receive texts from {dealer_name}. Reply STOP to opt out."
    )

    if vehicle:
        return (
            f"Hi! Thanks for your interest in the {vehicle.year} {vehicle.make} {vehicle.model}. "
            f"One of our team members will reach out shortly. {consent_text}"
        )
    return (
        f"Hi! Thanks for reaching out to {dealer_name}. "
        f"One of our team members will be in touch shortly. {consent_text}"
    )


def ingest_lead(
    session: Session,
    dealer,
    lead_data: NormalizedLead,
    *,
    fake_twilio=None,
    now: datetime | None = None,
) -> Lead:
    """Persist + start the flow for a new lead.

    Steps:
    1. Deduplicate (check for existing lead with same phone + dealer in rolling 24h window)
    2. Persist Lead (NEW)
    3. Resolve vehicle_ref
    4. Log consent if provided
    5. Transition to AUTO_REPLIED + send auto-reply SMS (via send_sms, gated by OUTBOUND_ENABLED)
    6. Assign round-robin + WhatsApp claim ping (via assign_lead)

    Returns the persisted Lead.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    dealer_config = dealer.config or {}

    # 1. Dedupe: check for existing lead with same phone + dealer in rolling 24h window
    if lead_data.phone:
        from datetime import timedelta
        cutoff = now - timedelta(hours=24)
        existing = _exec(session,
            select(Lead).where(
                Lead.dealer_id == dealer.id,
                Lead.phone == lead_data.phone,
                Lead.created_at >= cutoff,
            )
        ).first()
        if existing:
            logger.info("Deduped lead for phone=%s dealer=%s -> existing lead#%s",
                        lead_data.phone, dealer.slug, existing.id)
            return existing

    # 2. Persist Lead (NEW)
    vehicle_id = None
    vehicle = None
    if lead_data.vehicle_ref:
        vehicle = resolve_vehicle(session, dealer.id, lead_data.vehicle_ref)
        if vehicle:
            vehicle_id = vehicle.id

    lead = Lead(
        dealer_id=dealer.id,
        source=lead_data.source,
        name=lead_data.name,
        phone=lead_data.phone,
        email=lead_data.email,
        vehicle_ref=lead_data.vehicle_ref,
        vehicle_id=vehicle_id,
        state=LeadState.NEW,
        consent=lead_data.consent,
        created_at=now,
        updated_at=now,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)

    logger.info("Lead#%s created for dealer=%s source=%s phone=%s",
                lead.id, dealer.slug, lead_data.source, lead_data.phone)

    # 3. Log consent if provided (webform express consent)
    if lead_data.consent and lead_data.phone:
        consent_log = ConsentLog(
            dealer_id=dealer.id,
            lead_id=lead.id,
            phone=lead_data.phone,
            action="granted",
            text=lead_data.raw.get("consent_text", "Webform consent checkbox"),
        )
        session.add(consent_log)
        session.commit()
    elif lead_data.source == Channel.SMS and lead_data.phone:
        # SMS inbound = implied consent under CASL
        from tools.send_sms import _log_consent
        _log_consent(session, lead, source="sms_inbound")

    # 4. Transition NEW -> AUTO_REPLIED
    auto_text = _auto_reply_text(dealer_config, vehicle)
    transition(session, lead, LeadState.AUTO_REPLIED, reason="auto_reply",
               meta={"reply_text": auto_text})

    # 5. Send the auto-reply (gated by OUTBOUND_ENABLED inside send_sms/send_whatsapp)
    # Prefer WhatsApp if whatsapp_sender is configured, otherwise fall back to SMS
    channels = dealer_config.get("channels", {})
    whatsapp_sender = channels.get("whatsapp_sender", "")
    sms_number = channels.get("sms_number", "")

    # WhatsApp template SID for customer auto-replies
    WHATSAPP_AUTO_REPLY_TEMPLATE = "HX4ec87aebc636f28e34c42d57e3112320"

    if lead_data.phone and (whatsapp_sender or sms_number):
        if whatsapp_sender:
            # Send via WhatsApp as free-form message (sandbox allows this;
            # production will need an approved template for business-initiated)
            from tools.send_sms import send_whatsapp
            sid = send_whatsapp(
                to=lead_data.phone,
                body=auto_text,
                from_number=whatsapp_sender,
                lead=lead,
                session=session,
                role="CUSTOMER",
                fake_twilio=fake_twilio,
            )
            channel = "whatsapp"
        else:
            # Fall back to SMS
            from tools.send_sms import send_sms
            sid = send_sms(
                session,
                to=lead_data.phone,
                body=auto_text,
                from_number=sms_number,
                dealer_slug=dealer.slug,
                dealer_config=dealer_config,
                lead=lead,
                fake_twilio=fake_twilio,
                now=now,
            )
            channel = "sms"

        if sid:
            logger.info("Auto-reply %s sent for lead#%s sid=%s", channel, lead.id, sid)
        else:
            logger.info("Auto-reply %s suppressed for lead#%s (opt-out or quiet hours)", channel, lead.id)

    # ALWAYS record the auto-reply message to the conversation thread.
    # Use the caller's session — no global factory. The previous "fresh_session"
    # hack broke tests because each `sqlite:///:memory:` is a different in-memory
    # DB, so the factory pointed at a DB with no tables. expire_all() handles
    # any stale entity state from the transition + send_sms above.
    try:
        session.expire_all()
        existing_msg = session.execute(
            select(Message).where(Message.lead_id == lead.id, Message.direction == Direction.OUTBOUND)
        ).scalars().first()
        if not existing_msg:
            msg = Message(
                lead_id=lead.id,
                direction=Direction.OUTBOUND,
                channel=Channel.SMS,
                body=auto_text,
                ai_generated=True,
            )
            session.add(msg)
            session.commit()
            logger.info("Auto-reply message recorded for lead#%s", lead.id)
        else:
            logger.info("Auto-reply message already exists for lead#%s (sid=%s)", lead.id, existing_msg.provider_sid)
    except Exception:
        logger.exception("Failed to record auto-reply message for lead#%s", lead.id)
        session.rollback()

    # 6. Assign round-robin + SMS claim ping
    sales_team = dealer_config.get("sales_team", [])
    sms_number = dealer_config.get("channels", {}).get("sms_number")
    if sales_team:
        from app.engine.router import assign_lead
        assign_lead(
            session, lead, dealer, sales_team,
            fake_twilio=fake_twilio,
            sms_number=sms_number,
        )

    return lead