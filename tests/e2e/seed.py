"""Seed the e2e test database with leads, appointments, and messages."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from datetime import datetime, timezone, timedelta
from app.db import get_session_factory
from app.models import Lead, LeadState, Appointment, Message, Direction, Channel, Dealer
from sqlalchemy import select

DEALER_SLUG = "premier-auto"

LEADS = [
    {"name": "Alice Test", "phone": "+17781110001", "assigned_rep": "Helly",  "state": LeadState.NEW,       "vehicle_ref": "2024 Toyota Camry"},
    {"name": "Bob Test",   "phone": "+17781110002", "assigned_rep": "Helly",  "state": LeadState.ENGAGED,   "vehicle_ref": "2023 Honda Accord"},
    {"name": "Carol Test", "phone": "+17781110003", "assigned_rep": "Vishva", "state": LeadState.APPT_SET,  "vehicle_ref": "2024 Ford Explorer"},
    {"name": "Dave Test",  "phone": "+17781110004", "assigned_rep": "Vishva", "state": LeadState.SOLD,      "vehicle_ref": "2023 Tesla Model 3"},
    {"name": "Eve Test",   "phone": "+17781110005", "assigned_rep": None,     "state": LeadState.NEW,       "vehicle_ref": "2024 BMW X5"},
    {"name": "Frank Test", "phone": "+17781110006", "assigned_rep": None,     "state": LeadState.AUTO_REPLIED, "vehicle_ref": "2023 Mercedes C300"},
]


def seed():
    session = get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == DEALER_SLUG)).scalars().first()
        if not dealer:
            print("Dealer not found. Run the app first to auto-provision.")
            return

        now = datetime.now(timezone.utc)

        for ld in LEADS:
            lead = Lead(
                dealer_id=dealer.id,
                name=ld["name"],
                phone=ld["phone"],
                assigned_rep=ld["assigned_rep"],
                state=ld["state"],
                vehicle_ref=ld["vehicle_ref"],
                source=Channel.WEBFORM,
                consent=True,
                created_at=now - timedelta(hours=len(LEADS) - LEADS.index(ld)),
                updated_at=now - timedelta(hours=len(LEADS) - LEADS.index(ld)),
            )
            session.add(lead)
            session.flush()

            if ld["state"] == LeadState.APPT_SET:
                appt = Appointment(
                    lead_id=lead.id,
                    scheduled_for=now + timedelta(days=2),
                    status="set",
                )
                session.add(appt)

        session.commit()
        print(f"Seeded {len(LEADS)} leads.")
    finally:
        session.close()


if __name__ == "__main__":
    seed()
