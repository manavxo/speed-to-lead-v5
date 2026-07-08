"""Onboarding discovery probe — auto-detect the best inventory rung for a dealer URL.

Walks the ladder best -> floor, asking each adapter's `detect(url)` for a confidence score, and
recommends the highest. Used by tools/provision_dealer.py when `inventory.source: auto`.
"""

from __future__ import annotations

from app.adapters.inventory.base import InventorySource
from app.adapters.inventory.feed import FeedSource


class _ManualFloor(InventorySource):
    """Stub representing the manual upload floor — no file needed, always available."""
    kind = "manual"

    def fetch(self):
        raise NotImplementedError("Manual upload not yet implemented")

    @classmethod
    def detect(cls, url: str) -> float:
        return 0.1


ManualUploadSource = _ManualFloor  # alias for compatibility

# Order matters: best first, universal floor last.
# Stub adapters (DmsSource, StructuredDataSource, WebsiteScrapeSource) removed in v4;
# they can be re-added as concrete implementations later.
LADDER: list[type[InventorySource]] = [
    FeedSource,
    _ManualFloor,
]


def discover(url: str) -> dict:
    """Return {'kind': <best rung>, 'confidence': float, 'scores': {...}} for `url`.

    TODO: call each adapter's detect(url); pick the highest; return scores for the onboarding preview.
    """
    scores = {a.kind: a.detect(url) for a in LADDER}
    best = max(scores, key=scores.get) if scores else _ManualFloor.kind
    return {"kind": best, "confidence": scores.get(best, 0.0), "scores": scores}
