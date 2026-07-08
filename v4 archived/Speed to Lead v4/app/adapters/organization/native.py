"""Org sink: native — our own dashboard IS the system of record. Universal floor (default).

A no-op beyond our own DB: the LeadEvent already lives in Postgres and renders in the dashboard.
"""

from __future__ import annotations

from app.adapters.organization import OrganizationSink
from app.models import LeadEvent


class NativeSink(OrganizationSink):
    mode = "native"

    def push(self, event: LeadEvent) -> None:
        # Nothing to mirror — the dashboard reads LeadEvents directly. Mark synced.
        return None
