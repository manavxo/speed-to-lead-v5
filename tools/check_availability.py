"""Tool: check appointment slot availability (deterministic, grounded).

Returns ONLY valid booking slots based on:
- Dealer business hours (from dealer config)
- Existing appointments per rep (no double-booking)

The AI may ONLY offer slots this tool returns. If empty, the AI must
say no slots are available and escalate to a human.

This is the same grounding contract as check_inventory: the tool is the
sole source of truth. The model MUST NOT invent slots.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select, func

from app.models import Appointment

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger("speed-to-lead.check_availability")


def _is_day_closed(hours: dict, day_key: str) -> bool:
    val = hours.get(day_key, "closed")
    return val == "closed" or not val


def _parse_hours_range(hours: dict, day_key: str) -> tuple[int, int] | None:
    """Return (open_minutes, close_minutes) or None if closed."""
    if _is_day_closed(hours, day_key):
        return None
    val = hours[day_key]
    try:
        open_str, close_str = val.split("-")
        open_h, open_m = map(int, open_str.split(":"))
        close_h, close_m = map(int, close_str.split(":"))
        return (open_h * 60 + open_m, close_h * 60 + close_m)
    except (ValueError, AttributeError):
        return None


def _round_to_nearest_slot(dt: datetime, interval_min: int = 30) -> datetime:
    """Round a datetime up to the nearest 30-minute slot."""
    minutes = dt.hour * 60 + dt.minute
    rounded = ((minutes + interval_min - 1) // interval_min) * interval_min
    return dt.replace(hour=rounded // 60, minute=rounded % 60, second=0, microsecond=0)


_DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def check_availability(
    session: Session,
    dealer_id: int,
    *,
    days_ahead: int = 7,
    dealer_config: dict | None = None,
    interval_min: int = 60,
    now: datetime | None = None,
) -> list[dict]:
    """Return available appointment slots for the next N days.

    Each slot is a dict: {date, time, iso, rep_name (or None)}.
    Slots are filtered to business hours minus existing appointments.
    Returns at most 20 slots (ordered chronologically).

    Args:
        session: DB session for querying existing appointments.
        dealer_id: The dealer to check.
        days_ahead: How many days to look ahead (default 7).
        dealer_config: Dealer config dict (for business hours).
        interval_min: Slot interval in minutes (default 60).
        now: Optional fixed timestamp for testing.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if dealer_config is None:
        dealer_config = {}

    hours = dealer_config.get("dealer", {}).get("hours", {})
    tz_name = dealer_config.get("dealer", {}).get("timezone", "America/Vancouver")

    try:
        from zoneinfo import ZoneInfo
        dealer_tz = ZoneInfo(tz_name)
    except Exception:
        dealer_tz = timezone.utc

    local_now = now.astimezone(dealer_tz)

    # Fetch existing appointments for the next N days
    end_date = local_now + timedelta(days=days_ahead + 1)
    existing = session.execute(
        select(Appointment).where(
            Appointment.dealer_id == dealer_id,
            Appointment.scheduled_for >= local_now.replace(hour=0, minute=0, second=0, microsecond=0),
            Appointment.scheduled_for < end_date,
            Appointment.status.in_(["set", "confirmed"]),
        )
    ).scalars().all()

    # Build set of occupied slots as (iso_datetime) strings
    occupied = set()
    for appt in existing:
        if appt.scheduled_for:
            slot_dt = appt.scheduled_for.astimezone(dealer_tz) if appt.scheduled_for.tzinfo else appt.scheduled_for.replace(tzinfo=timezone.utc).astimezone(dealer_tz)
            occupied.add(slot_dt.strftime("%Y-%m-%dT%H:%M"))

    # Generate available slots
    slots: list[dict] = []
    for day_offset in range(days_ahead):
        check_date = local_now.date() + timedelta(days=day_offset)
        day_key = _DAY_KEYS[check_date.weekday()]

        day_range = _parse_hours_range(hours, day_key)
        if day_range is None:
            continue  # closed day

        open_min, close_min = day_range

        # Start from open time (or next available on today)
        start_min = open_min
        if day_offset == 0:
            current_min = local_now.hour * 60 + local_now.minute
            start_min = max(open_min, _round_to_nearest_slot(local_now, interval_min).hour * 60 + _round_to_nearest_slot(local_now, interval_min).minute)

        for slot_min in range(start_min, close_min, interval_min):
            slot_h = slot_min // 60
            slot_m = slot_min % 60
            slot_dt = datetime(
                check_date.year, check_date.month, check_date.day,
                slot_h, slot_m, 0, tzinfo=dealer_tz,
            )

            iso_key = slot_dt.strftime("%Y-%m-%dT%H:%M")
            if iso_key not in occupied:
                slots.append({
                    "date": check_date.strftime("%A, %B %d"),
                    "time": f"{slot_h:02d}:{slot_m:02d}",
                    "iso": slot_dt.isoformat(),
                })

            if len(slots) >= 20:
                break

        if len(slots) >= 20:
            break

    logger.info(
        "check_availability: dealer=%d days=%d slots=%d occupied=%d",
        dealer_id, days_ahead, len(slots), len(occupied),
    )
    return slots
