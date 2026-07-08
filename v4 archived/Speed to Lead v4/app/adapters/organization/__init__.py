"""AXIS 2 — organization sinks: mirror the canonical LeadEvent stream to the dealer's
system of record (CRM, spreadsheet, webhook, or our own dashboard).

The engine ALWAYS owns the canonical Lead + LeadEvent records. A sink just mirrors them
outward, so a sink failure never loses a lead. `tools/sync_crm.py` calls `push()` per event
with retry. `native` is a no-op beyond our own DB (our dashboard is the system of record).
"""

from __future__ import annotations

import abc

from app.models import LeadEvent


class OrganizationSink(abc.ABC):
    """Implement one per system-of-record target (native, crm_sync, sheet, webhook, email_digest)."""

    mode: str = "base"

    def __init__(self, dealer_slug: str, target: str = "", credentials_ref: str = "", **opts):
        self.dealer_slug = dealer_slug
        self.target = target
        self.credentials_ref = credentials_ref
        self.opts = opts

    @abc.abstractmethod
    def push(self, event: LeadEvent) -> None:  # pragma: no cover - interface
        """Mirror a single LeadEvent to the external system. Raise on failure to trigger retry."""
        raise NotImplementedError


__all__ = ["OrganizationSink"]
