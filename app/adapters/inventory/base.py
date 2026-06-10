"""AXIS 1 base: the InventorySource interface + the canonical VehicleRecord.

Every inventory adapter (feed, dms, structured_data, website_scrape, manual_upload) implements
`InventorySource.fetch()` and returns `VehicleRecord`s. `tools/sync_inventory.py` maps those into
the `Vehicle` DB table. The engine/AI never see an adapter's raw format.
"""

from __future__ import annotations

import abc
from typing import Optional

from pydantic import BaseModel


class VehicleRecord(BaseModel):
    """Canonical vehicle shape produced by every Axis-1 adapter (pre-persistence)."""
    stock_no: Optional[str] = None
    vin: Optional[str] = None
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    trim: Optional[str] = None
    body: Optional[str] = None
    mileage: Optional[int] = None
    price: Optional[float] = None
    status: str = "available"
    url: Optional[str] = None
    photos: list[str] = []
    raw: dict = {}


class InventorySource(abc.ABC):
    """Implement one of these per inventory platform / method.

    Contract:
      - `fetch()` returns the dealer's *current* full inventory as VehicleRecords.
      - It must be safe to call repeatedly (sync runs on a timer).
      - On a recoverable error, raise; the caller serves last-known-good and flags staleness.
    """

    #: short id used in dealer config `inventory.source` / discovery results
    kind: str = "base"

    def __init__(self, dealer_slug: str, url: Optional[str] = None, field_map: object = "auto", **opts):
        self.dealer_slug = dealer_slug
        self.url = url
        self.field_map = field_map
        self.opts = opts

    @abc.abstractmethod
    def fetch(self) -> list[VehicleRecord]:  # pragma: no cover - interface
        """Return the dealer's current inventory."""
        raise NotImplementedError

    @classmethod
    def detect(cls, url: str) -> float:  # pragma: no cover - interface
        """Return a 0..1 confidence that this adapter can handle `url` (used by discovery.py)."""
        return 0.0
