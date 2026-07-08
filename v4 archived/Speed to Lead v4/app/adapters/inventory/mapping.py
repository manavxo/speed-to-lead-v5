"""Field-mapping layer — normalize each source's columns to the canonical VehicleRecord.

Two paths:
  1) Known maps for popular platforms + the Google Vehicle Ads / Facebook Catalog specs (instant).
  2) LLM-assisted mapping for unknown column sets at onboarding; the result is persisted so it
     runs once per dealer, not per sync.
"""

from __future__ import annotations

import csv
from io import StringIO

from app.adapters.inventory.base import VehicleRecord

# canonical field -> set of known source column aliases (extend as we meet platforms).
KNOWN_MAPS: dict[str, dict[str, list[str]]] = {
    "google_vehicle_ads": {
        "vin": ["vin"],
        "stock_no": ["stock", "stock_number", "stock_no"],
        "year": ["year"],
        "make": ["make"],
        "model": ["model"],
        "trim": ["trim"],
        "body": ["body_style", "body"],
        "mileage": ["mileage"],
        "price": ["price"],
        "status": ["state_of_vehicle", "status"],
        "url": ["link", "vehicle_url"],
        "photos": ["image_link", "additional_image_link", "image_url"],
    },
    # "facebook_catalog": {...}, "dealerpull": {...}, ...
}

# Flatten known column aliases -> canonical field for quick lookup.
_COL_TO_FIELD: dict[str, str] = {}
for _spec in KNOWN_MAPS.values():
    for _field, _aliases in _spec.items():
        for _alias in _aliases:
            _COL_TO_FIELD[_alias.lower()] = _field


_STATUS_MAP = {
    "used": "available",
    "new": "available",
    "available": "available",
    "sold": "sold",
    "removed": "removed",
}


def _coerce_int(val: str | None) -> int | None:
    if val is None or val.strip() == "":
        return None
    return int(float(val.replace(",", "").strip()))


def _coerce_float(val: str | None) -> float | None:
    if val is None or val.strip() == "":
        return None
    return float(val.replace(",", "").strip())


def _build_photos(val: str | None) -> list[str]:
    if not val:
        return []
    return [u.strip() for u in val.split("|") if u.strip()]


def map_row(row: dict, mapping: dict[str, str] | str = "auto") -> VehicleRecord:
    """Map a single raw source row to a VehicleRecord using an explicit/known/auto mapping.

    If mapping is 'auto', uses the KNOWN_MAPS column alias lookup. For unknown columns,
    the LLM-assisted mapper should be called once at onboarding and the result cached.
    """
    if mapping == "auto":
        # Auto-discover by matching column names against known aliases.
        resolved: dict[str, str] = {}
        for col_name in row:
            canonical = _COL_TO_FIELD.get(col_name.lower())
            if canonical:
                resolved[canonical] = col_name
    else:
        # Explicit mapping: canonical_field -> source_column
        resolved = mapping

    def _get(field: str) -> str | None:
        col = resolved.get(field)
        if col is None:
            return None
        val = row.get(col)
        if val is None or (isinstance(val, str) and val.strip() == ""):
            return None
        return str(val).strip()

    photos_raw = _get("photos")
    photos = _build_photos(photos_raw) if photos_raw else []

    status_raw = _get("status")
    status = _STATUS_MAP.get(status_raw.lower() if status_raw else "", "available")

    return VehicleRecord(
        vin=_get("vin"),
        stock_no=_get("stock_no"),
        year=_coerce_int(_get("year")),
        make=_get("make"),
        model=_get("model"),
        trim=_get("trim"),
        body=_get("body"),
        mileage=_coerce_int(_get("mileage")),
        price=_coerce_float(_get("price")),
        status=status,
        url=_get("url"),
        photos=photos,
        raw=dict(row),
    )


def map_csv(text: str, mapping: dict[str, str] | str = "auto") -> list[VehicleRecord]:
    """Parse a CSV string and return a list of VehicleRecords."""
    reader = csv.DictReader(StringIO(text))
    return [map_row(row, mapping) for row in reader]


def infer_mapping_with_llm(sample_rows: list[dict]) -> dict[str, str]:
    """Ask Claude to map unknown columns -> canonical fields. Cache + return the mapping."""
    raise NotImplementedError