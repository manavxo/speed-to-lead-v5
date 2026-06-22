"""T2: Prove the AI engine holds a grounded conversation against live OpenRouter.

Drive handle_turn() with 3 scripted turns, using an SQLite in-memory DB
and the real DeepSeek V4 Flash via OpenRouter.

Run: python test_t2_ai_engine.py
"""
from __future__ import annotations

import os
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("OUTBOUND_ENABLED", "false")

import textwrap
from app.db import init_db, get_session_factory
from app.models import Channel, Dealer, Lead, LeadState, Vehicle
from sqlalchemy import select, func

PREMIER_CONFIG = {
    "dealer": {
        "name": "Premier Auto Group",
        "timezone": "America/Vancouver",
        "hours": {
            "mon": "09:00-19:00", "tue": "09:00-19:00", "wed": "09:00-19:00",
            "thu": "09:00-19:00", "fri": "09:00-19:00", "sat": "10:00-17:00",
            "sun": "closed",
        },
        "location_address": "4567 Kingsway, Burnaby, BC V5H 2B1",
        "main_phone": "+17787623122",
    },
    "ai": {
        "persona": "friendly, knowledgeable, no-pressure sales rep at Premier Auto Group. Keep responses concise (2-3 sentences).",
        "goal": "book_appointment",
        "guardrails": {"no_price_negotiation": True, "no_financing_promises": True},
    },
}


def _exec(session, stmt):
    return session.execute(stmt).scalars()


def run_3_turn_conversation():
    init_db()
    session = get_session_factory()()

    # Create dealer
    dealer = Dealer(slug="premier-auto", name="Premier Auto Group", config=PREMIER_CONFIG)
    session.add(dealer)
    session.commit()
    session.refresh(dealer)

    # Seed 5 vehicles
    vehicles = [
        Vehicle(dealer_id=dealer.id, stock_no="V001", year=2023, make="Hyundai",
                model="Tucson", trim="Preferred", price=29900, mileage=18500,
                body="SUV", status="available",
                raw={"engine": "2.5L I4", "transmission": "Automatic",
                     "drivetrain": "AWD", "exterior_color": "Phantom Black"}),
        Vehicle(dealer_id=dealer.id, stock_no="V002", year=2023, make="Mazda",
                model="CX-5", trim="GX", price=31200, mileage=14500,
                body="SUV", status="available",
                raw={"engine": "2.5L I4", "transmission": "Automatic",
                     "drivetrain": "AWD", "exterior_color": "Soul Red Crystal"}),
        Vehicle(dealer_id=dealer.id, stock_no="V003", year=2022, make="Honda",
                model="Civic", trim="Sport", price=25800, mileage=22000,
                body="Sedan", status="available",
                raw={"engine": "2.0L I4", "transmission": "Automatic",
                     "drivetrain": "FWD", "exterior_color": "Aegean Blue"}),
        Vehicle(dealer_id=dealer.id, stock_no="V004", year=2024, make="Kia",
                model="Sportage", trim="EX", price=34900, mileage=8500,
                body="SUV", status="available",
                raw={"engine": "2.5L I4", "transmission": "Automatic",
                     "drivetrain": "AWD", "exterior_color": "Glacier White"}),
        Vehicle(dealer_id=dealer.id, stock_no="V005", year=2023, make="Toyota",
                model="RAV4", trim="LE", price=32000, mileage=19500,
                body="SUV", status="available",
                raw={"engine": "2.5L I4", "transmission": "Automatic",
                     "drivetrain": "AWD", "exterior_color": "Magnetic Gray"}),
    ]
    session.add_all(vehicles)
    session.commit()

    vcount = session.execute(select(func.count()).where(Vehicle.dealer_id == dealer.id)).scalar()
    print(f"Seeded {vcount} vehicles")

    # Create lead
    lead = Lead(
        dealer_id=dealer.id,
        source=Channel.SMS,
        name="Manav",
        phone="+16045550123",
        state=LeadState.ENGAGED,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)

    from app.engine.conversation import handle_turn

    turns = [
        ("Hi, I am looking for a used SUV under $35k. What do you have?",
         "SUV inquiry — AI MUST call check_inventory and reference real cars"),

        ("Tell me about the Hyundai Tucson. How much is it?",
         "Specific vehicle — AI MUST reference check_inventory results, not invent"),

        ("Sounds great, I'd like to come see it. Can I come tomorrow afternoon?",
         "Booking intent — AI should suggest a time or book"),
    ]

    print("=" * 65)
    print("T2 - 3-TURN LIVE AI CONVERSATION (DeepSeek V4 Flash)")
    print("=" * 65)
    print(f"Dealer: {dealer.name}")
    print(f"Inventory: {vcount} vehicles seeded")
    print()

    for i, (message, desc) in enumerate(turns, 1):
        print(f"--- TURN {i} ({desc}) ---")
        print(f"Customer: {message}")

        result = handle_turn(
            session, lead, message,
            dealer_config=dealer.config or {},
        )
        text = result.get("text", "")
        mode = result.get("mode", "?")
        tools = result.get("tools_used", [])

        print(f"Mode: {mode}")
        if tools:
            print(f"Tools called: {', '.join(tools)}")
        print(f"AI ({len(text)} chars):")
        print(textwrap.fill(text, width=70))
        print()

    # Verify inventory grounding
    print("--- GROUNDING VERIFICATION ---")
    from tools.check_inventory import search
    suvs = search(session, dealer.id, body="SUV", max_price=35000, limit=10)
    print(f"Real inventory (SUV under $35k): {len(suvs)} vehicles")
    for v in suvs:
        print(f"  #{v.stock_no}: {v.year} {v.make} {v.model} {v.trim} — ${v.price:,} ({v.mileage:,} km)")
    
    # Check if AI text references any real stock numbers
    for v in suvs:
        if v.stock_no in text:
            print(f"  ✓ AI referenced real vehicle #{v.stock_no}")

    session.close()
    print("\nT2 complete.")


if __name__ == "__main__":
    run_3_turn_conversation()
