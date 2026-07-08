"""Org sink: fire a webhook (Zapier / Make / custom) with each LeadEvent."""

from __future__ import annotations

from app.adapters.organization import OrganizationSink
from app.models import LeadEvent


class WebhookSink(OrganizationSink):
    mode = "webhook"

    def push(self, event: LeadEvent) -> None:
        # TODO: POST event payload to self.target URL; treat non-2xx as failure (retry)
        raise NotImplementedError
