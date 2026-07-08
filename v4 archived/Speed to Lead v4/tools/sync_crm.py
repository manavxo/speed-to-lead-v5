"""Tool: flush the LeadEvent stream to the dealer organization sink (Axis 2).

Reads unsynced LeadEvents, pushes each through the configured OrganizationSink with retry, and
marks them synced. We own the canonical record, so a sink failure never loses data - it just retries.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import httpx
from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.models import Dealer, LeadEvent

logger = logging.getLogger("speed-to-lead.sync_crm")


class OrganizationSink(ABC):
    """Base class for all organization sinks."""

    @abstractmethod
    def push(self, event: dict) -> bool:
        """Push a single event. Return True on success, False on failure."""


class NativeSink(OrganizationSink):
    """No-op sink - we ARE the system of record. Marks events as synced."""

    def push(self, event: dict) -> bool:
        return True


class WebhookSink(OrganizationSink):
    """POST LeadEvent payload to an external webhook URL (Zapier/Make/custom)."""

    def __init__(self, webhook_url: str, auth_header: str | None = None):
        self.webhook_url = webhook_url
        self.auth_header = auth_header

    def push(self, event: dict) -> bool:
        headers = {"Content-Type": "application/json"}
        if self.auth_header:
            headers["Authorization"] = self.auth_header

        try:
            resp = httpx.post(
                self.webhook_url,
                json=event,
                headers=headers,
                timeout=10,
            )
            return resp.status_code < 300
        except Exception:
            logger.exception("Webhook sink failed")
            return False


class EmailDigestSink(OrganizationSink):
    """Queue events for batch email digest (placeholder)."""

    def __init__(self, recipient: str):
        self.recipient = recipient

    def push(self, event: dict) -> bool:
        logger.info("Email digest event for %s: %s", self.recipient, event.get("event_type"))
        return True


def build_sink(dealer: Dealer) -> OrganizationSink:
    """Instantiate the right OrganizationSink from config."""
    config = dealer.config or {}
    lead_org = config.get("lead_org", {})
    mode = lead_org.get("mode", "native")
    target = lead_org.get("target", "")
    credentials_ref = lead_org.get("credentials_ref", "")

    if mode == "native":
        return NativeSink()
    elif mode == "webhook":
        auth = None
        if credentials_ref:
            import os
            auth = os.environ.get(credentials_ref)
        return WebhookSink(target, auth_header=auth)
    elif mode == "email_digest":
        return EmailDigestSink(target or "admin@example.com")
    elif mode == "crm_sync":
        auth = None
        if credentials_ref:
            import os
            auth = os.environ.get(credentials_ref)
        return WebhookSink(target, auth_header=auth)
    elif mode == "sheet":
        return WebhookSink(target) if target else NativeSink()
    else:
        return NativeSink()


def flush_events(session: Session, dealer: Dealer, *, batch: int = 100) -> dict:
    """Push pending LeadEvents to the sink. Returns pushed/failed counts."""
    sink = build_sink(dealer)

    stmt = (
        select(LeadEvent)
        .where(LeadEvent.dealer_id == dealer.id, LeadEvent.synced == false())
        .order_by(LeadEvent.created_at.asc())
        .limit(batch)
    )
    events = session.execute(stmt).scalars().all()

    pushed = 0
    failed = 0


    for event in events:
        payload = {
            "event_id": event.id,
            "lead_id": event.lead_id,
            "dealer_slug": dealer.slug,
            "event_type": event.type,
            "payload": event.payload or {},
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }

        try:
            success = sink.push(payload)
            if success:
                event.synced = True
                pushed += 1
            else:
                failed += 1
        except Exception:
            logger.exception("Failed to sync event %s", event.id)
            failed += 1

    session.commit()
    return {"pushed": pushed, "failed": failed, "total": len(events)}

