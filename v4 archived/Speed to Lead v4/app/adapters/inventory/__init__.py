"""AXIS 1 — inventory ingestion ladder (best -> universal floor).

    feed             CSV/TSV/XML (Google Vehicle Ads / FB Catalog specs)   [preferred]
    dms              known-platform feed/API + prebuilt field mapping
    structured_data  schema.org JSON-LD / internal JSON API
    website_scrape   LLM-assisted HTML extraction (web-scrape skill)
    manual_upload    CSV upload / dashboard entry                          [floor]

discovery.py auto-detects the best rung at onboarding; mapping.py normalizes fields.
"""

from app.adapters.inventory.base import InventorySource, VehicleRecord

__all__ = ["InventorySource", "VehicleRecord"]
