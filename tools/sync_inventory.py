"""Tool: sync a dealer's inventory from their configured source into the vehicles table.

Runs on an APScheduler timer (inventory.refresh_min). Upserts new vehicles, marks sold/removed.
On a fetch error, serves last-known-good and flags staleness. Idempotent per sync run.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.inventory.base import VehicleRecord
from app.models import Dealer, Vehicle


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _exec(session: Session, stmt):
    """Execute a select statement and return scalars. Works with plain SQLAlchemy sessions."""
    return session.execute(stmt).scalars()


def _upsert_vehicle(session: Session, dealer_id: int, record: VehicleRecord) -> Vehicle:
    """Insert or update a vehicle. Match by (dealer_id, stock_no) or (dealer_id, vin)."""
    existing = None

    if record.stock_no:
        existing = _exec(session,
            select(Vehicle).where(
                Vehicle.dealer_id == dealer_id,
                Vehicle.stock_no == record.stock_no,
            )
        ).first()

    if existing is None and record.vin:
        existing = _exec(session,
            select(Vehicle).where(
                Vehicle.dealer_id == dealer_id,
                Vehicle.vin == record.vin,
            )
        ).first()

    now = _utcnow()

    if existing is not None:
        # Update existing
        existing.vin = record.vin or existing.vin
        existing.stock_no = record.stock_no or existing.stock_no
        existing.year = record.year if record.year is not None else existing.year
        existing.make = record.make or existing.make
        existing.model = record.model or existing.model
        existing.trim = record.trim or existing.trim
        existing.body = record.body or existing.body
        existing.mileage = record.mileage if record.mileage is not None else existing.mileage
        existing.price = record.price if record.price is not None else existing.price
        existing.status = record.status
        existing.url = record.url or existing.url
        existing.photos = record.photos or existing.photos
        existing.raw = record.raw or existing.raw
        existing.synced_at = now
        return existing
    else:
        # Insert new
        vehicle = Vehicle(
            dealer_id=dealer_id,
            vin=record.vin,
            stock_no=record.stock_no,
            year=record.year,
            make=record.make,
            model=record.model,
            trim=record.trim,
            body=record.body,
            mileage=record.mileage,
            price=record.price,
            status=record.status,
            url=record.url,
            photos=record.photos,
            raw=record.raw,
            synced_at=now,
        )
        session.add(vehicle)
        return vehicle


def sync_inventory(
    session: Session,
    dealer: Dealer,
    records: list[VehicleRecord],
) -> dict:
    """Sync a dealer's inventory from VehicleRecords into the DB.

    Returns a summary dict: {upserted, marked_sold, total, stale}.
    Idempotent: running twice with the same data is a no-op.
    """
    now = _utcnow()
    dealer_id = dealer.id

    # Build a set of stock_nos/vins that are in the current feed
    feed_keys: set[str] = set()
    for r in records:
        if r.stock_no:
            feed_keys.add(f"stock:{r.stock_no}")
        if r.vin:
            feed_keys.add(f"vin:{r.vin}")

    # Upsert each record
    for record in records:
        _upsert_vehicle(session, dealer_id, record)

    # Mark vehicles as sold/removed if they're no longer in the feed
    all_vehicles = _exec(session,
        select(Vehicle).where(Vehicle.dealer_id == dealer_id)
    ).all()

    marked_sold = 0
    for v in all_vehicles:
        key_stock = f"stock:{v.stock_no}" if v.stock_no else None
        key_vin = f"vin:{v.vin}" if v.vin else None
        in_feed = (key_stock and key_stock in feed_keys) or (key_vin and key_vin in feed_keys)
        if not in_feed and v.status == "available":
            v.status = "sold"
            v.synced_at = now
            marked_sold += 1

    session.commit()

    return {
        "upserted": len(records),
        "marked_sold": marked_sold,
        "total": len(all_vehicles),
        "stale": False,
    }


def sync_inventory_from_source(session: Session, dealer: Dealer) -> dict:
    """Run a full sync from the dealer's configured inventory source.

    On failure, returns stale=True and the previously synced data remains.
    """
    from app.adapters.inventory.manual import FeedSource

    config = dealer.config or {}
    inv_config = config.get("inventory", {})
    source = inv_config.get("source", "manual")
    url = inv_config.get("url", "")
    field_map = inv_config.get("field_map", "auto")

    if source == "none" or source == "manual":
        return {"upserted": 0, "marked_sold": 0, "total": 0, "stale": False}

    try:
        if source == "feed":
            adapter = FeedSource(dealer_slug=dealer.slug, url=url, field_map=field_map)
        else:
            return {"upserted": 0, "marked_sold": 0, "total": 0, "stale": True,
                    "error": f"Source type '{source}' not yet implemented"}

        records = adapter.fetch()
        return sync_inventory(session, dealer, records)
    except Exception as exc:
        return {"upserted": 0, "marked_sold": 0, "total": 0, "stale": True,
                "error": str(exc)}