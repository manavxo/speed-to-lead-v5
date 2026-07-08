"""SLA escalation — fires when a lead isn't claimed within routing.claim_timeout_min.

Escalation ladder (from dealer config `routing.escalation`): reassign to the next rep, then
notify the manager. The lead already got the instant AI auto-reply, so it is never left waiting.
"""
from __future__ import annotations

import logging
from sqlalchemy.orm import Session

from app.engine.lifecycle import transition
from app.models import Dealer, Lead, LeadState

logger = logging.getLogger("speed-to-lead.escalation")


def on_claim_timeout(
    session: Session,
    lead_id: int,
    dealer: Dealer,
    sales_team: list[dict],
    *,
    fake_twilio=None,
    sms_number: str | None = None,
) -> Lead | None:
    """If still unclaimed, advance the escalation ladder.

    Steps:
    1. Reload the lead
    2. If still ASSIGNED, transition to ESCALATED
    3. Run the next escalation action from config (reassign via router.assign_lead,
       then notify_manager via send_sms)

    Returns the updated lead, or None if lead not found.
    """
    lead = session.get(Lead, lead_id)
    if lead is None:
        return None

    # Only escalate if still ASSIGNED
    if lead.state != LeadState.ASSIGNED:
        return lead

    # Transition to ESCALATED
    transition(session, lead, LeadState.ESCALATED, reason="claim_timeout")

    logger.info("Lead#%s escalated — running actions", lead_id)

    # Run escalation actions from config
    dealer_config = dealer.config or {}
    escalation_actions = dealer_config.get("routing", {}).get(
        "escalation", ["reassign", "notify_manager"]
    )

    for action in escalation_actions:
        if action == "reassign":
            from app.engine.router import assign_lead
            assign_lead(
                session, lead, dealer, sales_team,
                fake_twilio=fake_twilio,
                sms_number=sms_number,
            )
        elif action == "notify_manager":
            manager_phone = dealer_config.get("routing", {}).get("manager_phone")
            if manager_phone:
                manager_msg = (
                    f"Lead {lead.name or 'Customer'} ({lead.phone or 'unknown'}) "
                    f"unclaimed after timeout. Please review."
                )
                from tools.send_sms import send_sms
                send_sms(
                    session=session,
                    to=manager_phone,
                    body=manager_msg,
                    from_number=sms_number or "",
                    lead=lead,
                    role="MANAGER",
                    fake_twilio=fake_twilio,
                    force_send=True,
                )

    return lead
