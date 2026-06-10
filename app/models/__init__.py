"""Canonical data model (SQLModel tables) — the single source of truth in Postgres.

These tables ARE the canonical schemas that sit in the middle of the three adapter axes:
every intake adapter produces a `Lead`, every inventory adapter produces a `Vehicle`, and
every organization sink consumes the `LeadEvent` stream. The engine and AI only ever see
these types — never an adapter's raw payload.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import JSON, Column
from sqlalchemy import event as sa_event
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LeadState(str, Enum):
    NEW = "NEW"
    AUTO_REPLIED = "AUTO_REPLIED"
    ASSIGNED = "ASSIGNED"
    CLAIMED = "CLAIMED"
    ENGAGED = "ENGAGED"
    APPT_SET = "APPT_SET"
    SHOWED = "SHOWED"
    SOLD = "SOLD"
    LOST = "LOST"
    ESCALATED = "ESCALATED"
    OPTED_OUT = "OPTED_OUT"


class Channel(str, Enum):
    SMS = "sms"
    WHATSAPP = "whatsapp"
    MESSENGER = "messenger"
    EMAIL = "email"
    WEBFORM = "webform"
    PHONE = "phone"


class Direction(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class Dealer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True)
    name: str
    timezone: str = "America/Vancouver"
    # Indexed tenant-resolution columns (populated by provision_dealer.py from config)
    sms_number: Optional[str] = Field(default=None, index=True)
    whatsapp_sender: Optional[str] = Field(default=None, index=True)
    web_form_token: Optional[str] = Field(default=None, index=True, unique=True)
    # Full validated DealerConfig is persisted so the engine can resolve behavior per tenant.
    config: dict = Field(default_factory=dict, sa_column=Column(JSON))
    round_robin_pointer: int = 0
    created_at: datetime = Field(default_factory=_utcnow)


class Vehicle(SQLModel, table=True):
    """Canonical Vehicle — what every Axis-1 inventory adapter normalizes to."""
    id: Optional[int] = Field(default=None, primary_key=True)
    dealer_id: int = Field(index=True, foreign_key="dealer.id")
    stock_no: Optional[str] = Field(default=None, index=True)
    vin: Optional[str] = Field(default=None, index=True)
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    trim: Optional[str] = None
    body: Optional[str] = None
    mileage: Optional[int] = None
    price: Optional[float] = None
    status: str = "available"          # available | sold | removed
    url: Optional[str] = None
    photos: list = Field(default_factory=list, sa_column=Column(JSON))
    raw: dict = Field(default_factory=dict, sa_column=Column(JSON))   # original source payload
    synced_at: datetime = Field(default_factory=_utcnow)


class Lead(SQLModel, table=True):
    """Canonical Lead — what every Axis-3 intake adapter normalizes to."""
    id: Optional[int] = Field(default=None, primary_key=True)
    dealer_id: int = Field(index=True, foreign_key="dealer.id")
    source: Channel
    name: Optional[str] = None
    phone: Optional[str] = Field(default=None, index=True)
    email: Optional[str] = None
    vehicle_ref: Optional[str] = None                       # stock#, VIN, URL, or Y/M/M from the lead
    vehicle_id: Optional[int] = Field(default=None, foreign_key="vehicle.id")
    state: LeadState = Field(default=LeadState.NEW, index=True)
    assigned_rep: Optional[str] = None
    pass_count: int = 0                                           # how many times reps have passed this lead
    consent: bool = False
    loss_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class LeadEvent(SQLModel, table=True):
    """Append-only stream of everything that happens to a lead.

    This is what Axis-2 organization sinks mirror to the dealer's system of record.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    lead_id: int = Field(index=True, foreign_key="lead.id")
    dealer_id: int = Field(index=True, foreign_key="dealer.id")
    type: str                                               # e.g. state_change, message, appointment
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    synced: bool = Field(default=False, index=True)         # flushed to the org sink yet?
    created_at: datetime = Field(default_factory=_utcnow)


class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    lead_id: int = Field(index=True, foreign_key="lead.id")
    direction: Direction
    channel: Channel
    body: str
    provider_sid: Optional[str] = Field(default=None, index=True, unique=True)  # Twilio SID (idempotency)
    delivery_status: Optional[str] = Field(default=None, index=True)  # queued/sent/delivered/failed/undelivered
    error_code: Optional[str] = None                       # Twilio error code (e.g. 21610, 30007)
    ai_generated: bool = False
    approved_by: Optional[str] = None                       # rep who approved (business-hours mode)
    # Role attribution (Phase 2 provisioning — locked in during v5 build per directive H.2.4).
    # recipient_role: "customer" | "rep" | "manager" | "system"
    # sender_role:   "customer" | "ai"      | "rep"    | "system"
    # Lets the lead detail page show who said what, and lets Phase 2 filter/sort by role.
    sender_role: Optional[str] = Field(default=None, index=True)
    recipient_role: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow)


class Appointment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    lead_id: int = Field(index=True, foreign_key="lead.id")
    dealer_id: int = Field(index=True, foreign_key="dealer.id")
    scheduled_for: datetime
    status: str = "set"                                     # set | confirmed | showed | no_show | cancelled
    created_at: datetime = Field(default_factory=_utcnow)


class ConsentLog(SQLModel, table=True):
    """CASL/PIPA-BC audit trail of consent + opt-out events."""
    id: Optional[int] = Field(default=None, primary_key=True)
    dealer_id: int = Field(index=True, foreign_key="dealer.id")
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id")
    phone: str = Field(index=True)
    action: str                                             # granted | opted_out
    text: Optional[str] = None                              # the consent/opt-out message text
    created_at: datetime = Field(default_factory=_utcnow)


@sa_event.listens_for(Lead, "before_update")
def _lead_before_update(mapper, connection, target):
    """Auto-update updated_at on every Lead update."""
    target.updated_at = datetime.now(timezone.utc)


__all__ = [
    "LeadState", "Channel", "Direction",
    "Dealer", "Vehicle", "Lead", "LeadEvent", "Message", "Appointment", "ConsentLog",
]
