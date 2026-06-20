"""Tool: ingest a normalized lead and kick off the speed-to-lead flow.

Persist Lead (NEW) -> resolve vehicle_ref -> send instant auto-reply (AUTO_REPLIED) ->
AI sends proactive personalized follow-up (ENGAGED) -> AI handles full conversation ->
books appointment (APPT_SET) -> assign round-robin + notify rep.

The sales rep is NOT pinged until the AI has qualified the lead and booked an appointment.
This is the <60s core loop.
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


def _build_ai_followup_context(lead_data: NormalizedLead, vehicle=None, dealer_config: dict = None) -> str:
    """Build context for the AI's proactive follow-up message.

    Uses form data (name, vehicle interest, message) to generate a personalized
    opening that engages the customer immediately.
    """
    parts = []
    dealer_name = (dealer_config or {}).get("dealer", {}).get("name", "us")

    if lead_data.name:
        parts.append(f"Customer name: {lead_data.name}")
    if lead_data.vehicle_ref:
        parts.append(f"Vehicle interest: {lead_data.vehicle_ref}")
    if vehicle:
        parts.append(f"Matched inventory: {vehicle.year} {vehicle.make} {vehicle.model} ({vehicle.trim}) — ${vehicle.price:,.0f}" if vehicle.price else f"Matched inventory: {vehicle.year} {vehicle.make} {vehicle.model}")
    if lead_data.message:
        parts.append(f"Customer message: {lead_data.message}")

    context = ". ".join(parts) if parts else "New lead from webform"
    return context


def _send_to_customer(
    session: Session,
    lead: Lead,
    body: str,
    *,
    whatsapp_sender: str = "",
    sms_number: str = "",
    dealer_slug: str = "",
    dealer_config: dict = None,
    fake_twilio=None,
    now=None,
) -> str | None:
    """Send a message to the customer via WhatsApp or SMS. Returns SID or None."""
    if not lead.phone:
        logger.warning("_send_to_customer: no phone for lead#%s", lead.id)
        return None

    logger.info(
        "_send_to_customer: lead#%s to=%s whatsapp_sender=%r sms_number=%r",
        lead.id, lead.phone, whatsapp_sender, sms_number,
    )

    sid = None
    if whatsapp_sender:
        from tools.send_sms import send_whatsapp
        logger.info("_send_to_customer: calling send_whatsapp for lead#%s", lead.id)
        sid = send_whatsapp(
            to=lead.phone,
            body=body,
            from_number=whatsapp_sender,
            lead=lead,
            session=session,
            role="CUSTOMER",
            fake_twilio=fake_twilio,
        )
        logger.info("_send_to_customer: send_whatsapp returned %r for lead#%s", sid, lead.id)
    elif sms_number:
        from tools.send_sms import send_sms
        sid = send_sms(
            session,
            to=lead.phone,
            body=body,
            from_number=sms_number,
            dealer_slug=dealer_slug,
            dealer_config=dealer_config or {},
            lead=lead,
            fake_twilio=fake_twilio,
            now=now,
        )
    return sid


def _record_outbound_message(session: Session, lead: Lead, body: str, channel: Channel) -> None:
    """Record an outbound message in the conversation thread."""
    try:
        session.expire_all()
        msg = Message(
            lead_id=lead.id,
            direction=Direction.OUTBOUND,
            channel=channel,
            body=body,
            ai_generated=True,
        )
        session.add(msg)
        session.commit()
    except Exception:
        logger.exception("Failed to record outbound message for lead#%s", lead.id)
        session.rollback()


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
    existing = None
    was_dryrun = False
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
            # Check if the existing lead's auto-reply was actually sent (not DRYRUN)
            last_outbound = session.execute(
                select(Message).where(
                    Message.lead_id == existing.id,
                    Message.direction == Direction.OUTBOUND,
                ).order_by(Message.created_at.desc())
            ).scalars().first()

            was_dryrun = (
                last_outbound is not None
                and last_outbound.provider_sid is not None
                and last_outbound.provider_sid.startswith("DRYRUN_")
            )

            if was_dryrun:
                logger.info("Lead#%s was DRYRUN — deleting stale messages and re-sending", existing.id)
                from sqlalchemy import delete as sa_delete
                session.execute(
                    sa_delete(Message).where(
                        Message.lead_id == existing.id,
                        Message.provider_sid.like("DRYRUN_%"),
                    )
                )
                session.execute(
                    sa_delete(ConsentLog).where(
                        ConsentLog.lead_id == existing.id,
                    )
                )
                existing.state = LeadState.NEW
                existing.updated_at = now
                session.commit()
                # Fall through — don't return early
            else:
                logger.info("Deduped lead for phone=%s dealer=%s -> existing lead#%s",
                            lead_data.phone, dealer.slug, existing.id)
                return existing

    # 2. Persist Lead (NEW) or reuse existing DRYRUN lead
    vehicle = None
    if existing and was_dryrun:
        lead = existing
        lead.name = lead_data.name or lead.name
        lead.email = lead_data.email or lead.email
        lead.vehicle_ref = lead_data.vehicle_ref or lead.vehicle_ref
        if lead_data.vehicle_ref:
            vehicle = resolve_vehicle(session, dealer.id, lead_data.vehicle_ref)
            if vehicle:
                lead.vehicle_id = vehicle.id
        session.commit()
        session.refresh(lead)
        logger.info("Reusing DRYRUN lead#%s for phone=%s", lead.id, lead_data.phone)
    else:
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
    dealer_name = dealer_config.get("dealer", {}).get("name", "us")
    consent_text = dealer_config.get("compliance", {}).get(
        "consent_text",
        f"By submitting you agree to receive texts from {dealer_name}. Reply STOP to opt out."
    )
    auto_text = f"Thanks for reaching out to {dealer_name}! {consent_text}"
    transition(session, lead, LeadState.AUTO_REPLIED, reason="auto_reply",
               meta={"reply_text": auto_text})

    # 5. Send the auto-reply (gated by OUTBOUND_ENABLED inside send_sms/send_whatsapp)
    channels = dealer_config.get("channels", {})
    whatsapp_sender = channels.get("whatsapp_sender") or getattr(dealer, "whatsapp_sender", "") or ""
    sms_number = channels.get("sms_number") or getattr(dealer, "sms_number", "") or ""

    _send_to_customer(
        session, lead, auto_text,
        whatsapp_sender=whatsapp_sender, sms_number=sms_number,
        dealer_slug=dealer.slug, dealer_config=dealer_config,
        fake_twilio=fake_twilio, now=now,
    )

    # Record auto-reply in message thread
    _record_outbound_message(session, lead, auto_text, Channel.WHATSAPP if whatsapp_sender else Channel.SMS)

    # 6. AI proactive follow-up — engage the customer immediately with personalized context
    ai_context = _build_ai_followup_context(lead_data, vehicle, dealer_config)
    ai_followup_success = False
    try:
        from app.engine.conversation import handle_turn
        result = handle_turn(
            session, lead, ai_context,
            dealer_config=dealer_config,
            vehicle=vehicle,
            is_proactive=True,
        )
        ai_followup_text = result.get("text", "")
        if ai_followup_text:
            # Send the AI's personalized follow-up
            _send_to_customer(
                session, lead, ai_followup_text,
                whatsapp_sender=whatsapp_sender, sms_number=sms_number,
                dealer_slug=dealer.slug, dealer_config=dealer_config,
                fake_twilio=fake_twilio, now=now,
            )
            _record_outbound_message(session, lead, ai_followup_text, Channel.WHATSAPP if whatsapp_sender else Channel.SMS)
            logger.info("AI proactive follow-up sent for lead#%s", lead.id)
        ai_followup_success = True
    except Exception:
        logger.exception("AI proactive follow-up failed for lead#%s — deleting lead to avoid partial state", lead.id)
        # Delete the lead and all related data to avoid a half-baked AUTO_REPLIED lead
        from sqlalchemy import delete as sa_delete
        session.execute(sa_delete(Message).where(Message.lead_id == lead.id))
        session.execute(sa_delete(ConsentLog).where(ConsentLog.lead_id == lead.id))
        session.execute(sa_delete(Lead).where(Lead.id == lead.id))
        session.commit()
        raise

    # 7. Transition to ENGAGED — AI is now handling the conversation
    # Rep will be assigned only when an appointment is booked (APPT_SET)
    try:
        transition(session, lead, LeadState.ENGAGED, reason="ai_engaged",
                   meta={"ai_context": ai_context[:200]})
    except ValueError:
        logger.info("Lead#%s already past ENGAGED — skipping transition", lead.id)

    return lead