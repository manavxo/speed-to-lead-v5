"""Tool (AI-callable): search the synced vehicles table.

This is the AI's ONLY window into inventory — the grounding boundary. The model may only quote
cars/prices this returns; it must never invent one. Used to resolve a lead's vehicle_ref and to
answer vague asks ("any SUVs under $15k?") or suggest alternatives when a car is sold.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Vehicle


def _exec(session: Session, stmt):
    """Execute a select statement and return scalars."""
    return session.execute(stmt).scalars()


def resolve_vehicle(session: Session, dealer_id: int, vehicle_ref: str) -> Vehicle | None:
    """Resolve a stock#/VIN/URL/Y-M-M reference to a single Vehicle, or None.

    Tries: exact stock_no match, exact VIN match, URL match. Returns None if no match.
    """
    if not vehicle_ref:
        return None

    ref = vehicle_ref.strip()

    # Try stock_no first
    result = _exec(session,
        select(Vehicle).where(
            Vehicle.dealer_id == dealer_id,
            Vehicle.stock_no == ref,
        )
    ).first()
    if result:
        return result

    # Try VIN
    result = _exec(session,
        select(Vehicle).where(
            Vehicle.dealer_id == dealer_id,
            Vehicle.vin == ref,
        )
    ).first()
    if result:
        return result

    # Try URL
    result = _exec(session,
        select(Vehicle).where(
            Vehicle.dealer_id == dealer_id,
            Vehicle.url == ref,
        )
    ).first()
    if result:
        return result

    # Try partial match on URL (e.g. the ref contains the stock# in the URL path)
    result = _exec(session,
        select(Vehicle).where(
            Vehicle.dealer_id == dealer_id,
            Vehicle.url.ilike(f"%{ref}%"),
        )
    ).first()
    if result:
        return result

    return None


def search(
    session: Session,
    dealer_id: int,
    *,
    query: str | None = None,
    max_price: float | None = None,
    body: str | None = None,
    make: str | None = None,
    limit: int = 5,
) -> list[Vehicle]:
    """Return matching available vehicles.

    Supports keyword search across make/model/trim, price filter, body style filter.
    Only returns vehicles with status='available'.
    """
    stmt = select(Vehicle).where(
        Vehicle.dealer_id == dealer_id,
        Vehicle.status == "available",
    )

    if max_price is not None:
        stmt = stmt.where(Vehicle.price <= max_price)

    if body:
        stmt = stmt.where(Vehicle.body.ilike(f"%{body}%"))

    if make:
        stmt = stmt.where(Vehicle.make.ilike(f"%{make}%"))

    if query:
        # Match PER WORD, not the whole string. The model often passes a natural
        # phrase like "2023 Toyota RAV4 XLE", but make/model/trim/year live in
        # separate columns — so a single "%2023 Toyota RAV4 XLE%" LIKE matches
        # nothing. Split into tokens and require each token to hit some field
        # (year matched numerically). This makes "Toyota RAV4 XLE", "RAV4 XLE",
        # and "2023 RAV4" all resolve to the right car.
        import re as _re
        tokens = [t for t in _re.split(r"\s+", query.strip()) if t]
        for tok in tokens:
            pat = f"%{tok}%"
            conds = [
                Vehicle.make.ilike(pat),
                Vehicle.model.ilike(pat),
                Vehicle.trim.ilike(pat),
                Vehicle.body.ilike(pat),
            ]
            if tok.isdigit():
                conds.append(Vehicle.year == int(tok))
            stmt = stmt.where(or_(*conds))

    stmt = stmt.limit(limit)
    return list(_exec(session, stmt).all())