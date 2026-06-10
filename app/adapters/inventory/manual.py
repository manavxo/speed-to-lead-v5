"""Inventory rung 1 (preferred): standardized syndication/advertising feed.

CSV/TSV/XML in the Google Vehicle Ads or Facebook Automotive Catalog spec — what most Canadian
independent-dealer DMS platforms already emit for AutoTrader.ca/Kijiji/CarGurus/Google/FB.
"""

from __future__ import annotations

from pathlib import Path

from app.adapters.inventory.base import InventorySource, VehicleRecord
from app.adapters.inventory.mapping import map_csv


class FeedSource(InventorySource):
    kind = "feed"

    def fetch(self) -> list[VehicleRecord]:
        """Download (or read local) feed and return mapped VehicleRecords.

        Supports CSV files (local path or URL). XML/TSV support to be added.
        """
        if not self.url:
            raise ValueError("FeedSource requires a URL")

        # Support local file paths for development/testing
        local = Path(self.url)
        if local.exists():
            text = local.read_text(encoding="utf-8")
        else:
            # TODO: download from remote URL using httpx
            raise NotImplementedError(f"Remote feed download not yet implemented: {self.url}")

        mapping = self.field_map if self.field_map != "auto" else "auto"
        return map_csv(text, mapping)

    @classmethod
    def detect(cls, url: str) -> float:
        """Return confidence that this URL serves a feed.

        TODO: HEAD/GET; look for tabular/XML content-type or a known feed path.
        For now, return 0.0 (let manual be the floor until real detection is implemented).
        """
        if not url:
            return 0.0
        lower = url.lower()
        # Known feed path patterns
        feed_hints = ["feed", "csv", "inventory.csv", "vehicles.csv", "export"]
        if any(h in lower for h in feed_hints):
            return 0.8
        return 0.1