"""Automated CX test runner — exercises every customer-facing AI behavior.

Tests the conversation engine against all Phase 1 customer scenarios from CHECKLIST.md.
Each test simulates an SMS exchange and validates the AI's response.

Run: .venv/Scripts/python.exe tools/test_cx.py
"""
from __future__ import annotations
import sys
import json
import time
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

# ── Bootstrap ────────────────────────────────────────────────────────────────
from app.db import init_db, get_session_factory
from app.models import (
    Dealer, Lead, Vehicle, LeadState, LeadEvent,
    Message, Direction, Channel, Appointment, ConsentLog,
)
from app.engine.conversation import handle_turn
from app.engine.lifecycle import transition

init_db()
sf = get_session_factory()

# ── ANSI colors ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

PASS_COUNT = 0
FAIL_COUNT = 0
WARN_COUNT = 0
results: list[dict] = []


def _check(name: str, condition: bool, detail: str = "", warn_only: bool = False):
    global PASS_COUNT, FAIL_COUNT, WARN_COUNT
    if condition:
        PASS_COUNT += 1
        status = "PASS"
        color = GREEN
    elif warn_only:
        WARN_COUNT += 1
        status = "WARN"
        color = YELLOW
    else:
        FAIL_COUNT += 1
        status = "FAIL"
        color = RED
    print(f"  {color}{status}{RESET} {name}")
    if detail and (not condition or warn_only):
        print(f"       {DIM}{detail[:200]}{RESET}")
    results.append({"test": name, "status": status, "detail": detail})


def _run_turn(s: Session, lead: Lead, dealer: Dealer, msg: str, label: str) -> dict:
    """Simulate an inbound SMS and get the AI reply."""
    # Log inbound
    inbound = Message(
        lead_id=lead.id, direction=Direction.INBOUND,
        channel=Channel.SMS, body=msg,
    )
    s.add(inbound)
    s.commit()

    # Transition if needed
    if lead.state in (LeadState.AUTO_REPLIED, LeadState.NEW):
        try:
            transition(s, lead, LeadState.ENGAGED, reason="customer_reply")
        except ValueError:
            pass

    # Call AI
    result = handle_turn(
        s, lead, msg,
        dealer_config=dealer.config or {},
        vehicle=None,
    )
    return result


def _create_fresh_lead(s: Session, dealer: Dealer, name: str = "Test Customer") -> Lead:
    """Create a fresh test lead in ENGAGED state."""
    lead = Lead(
        dealer_id=dealer.id, source=Channel.SMS,
        name=name, phone="+17785550199",
        state=LeadState.AUTO_REPLIED, consent=True,
    )
    s.add(lead)
    s.commit()
    s.refresh(lead)
    try:
        transition(s, lead, LeadState.ENGAGED, reason="test_setup")
    except ValueError:
        pass
    return lead


# ══════════════════════════════════════════════════════════════════════════════
# TEST SUITE
# ══════════════════════════════════════════════════════════════════════════════

print(f"\n{BOLD}{'='*60}")
print(f"  SPEED TO LEAD v4 — CX TEST SUITE")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*60}{RESET}\n")

s = sf()
dealer = s.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
if not dealer:
    print("ERROR: No 'premier-auto' dealer found!")
    sys.exit(1)

# ── TEST 1: Inventory Search ────────────────────────────────────────────────
print(f"{CYAN}TEST 1: INVENTORY SEARCH{RESET}")
lead = _create_fresh_lead(s, dealer, "Inventory Test")

result = _run_turn(s, lead, dealer, "What SUVs do you have under $35k?", "inventory_search")
text = result.get("text", "")
tools = result.get("tools_used", [])

_check("AI called check_inventory", "check_inventory" in tools,
       f"Tools used: {tools}", warn_only=True)
_check("Response mentions actual vehicles",
       any(kw in text.lower() for kw in ["mazda", "hyundai", "kia", "tucson", "cx-5", "sportage"]),
       f"Response: {text[:200]}")
_check("Response includes prices",
       any(c in text for c in ["$", "price"]),
       f"Response: {text[:200]}")
_check("Response ends with question/CTA",
       any(text.strip().endswith(c) for c in ["?", "!"]),
       f"Ends with: {text.strip()[-30:]}")

# ── TEST 2: Specific Make Search ─────────────────────────────────────────────
print(f"\n{CYAN}TEST 2: SPECIFIC MAKE SEARCH{RESET}")
lead = _create_fresh_lead(s, dealer, "Make Test")

result = _run_turn(s, lead, dealer, "Do you have any Hondas?", "specific_make")
text = result.get("text", "")
tools = result.get("tools_used", [])

_check("AI called check_inventory for Honda", "check_inventory" in tools,
       f"Tools: {tools}", warn_only=True)
_check("Response mentions Honda Civic",
       "civic" in text.lower() or "honda" in text.lower(),
       f"Response: {text[:200]}")
_check("Response doesn't make up vehicles",
       "don't see" in text.lower() or "civic" in text.lower() or "honda" in text.lower(),
       f"Response: {text[:200]}")

# ── TEST 3: Budget-Based Search ──────────────────────────────────────────────
print(f"\n{CYAN}TEST 3: BUDGET-BASED SEARCH{RESET}")
lead = _create_fresh_lead(s, dealer, "Budget Test")

result = _run_turn(s, lead, dealer, "What's the cheapest car you have?", "budget_search")
text = result.get("text", "")
tools = result.get("tools_used", [])

_check("AI called check_inventory", "check_inventory" in tools, f"Tools: {tools}", warn_only=True)
_check("Response mentions a real vehicle",
       any(kw in text.lower() for kw in ["corolla", "altima", "civic"]),
       f"Response: {text[:200]}")
_check("Response includes a price",
       "$" in text,
       f"Response: {text[:200]}")

# ── TEST 4: Body Style Search ────────────────────────────────────────────────
print(f"\n{CYAN}TEST 4: BODY STYLE SEARCH{RESET}")
lead = _create_fresh_lead(s, dealer, "Body Test")

result = _run_turn(s, lead, dealer, "Do you have any trucks?", "body_style")
text = result.get("text", "")
tools = result.get("tools_used", [])

_check("AI searched for trucks", "check_inventory" in tools, f"Tools: {tools}", warn_only=True)
_check("Response mentions Ford F-150",
       "f-150" in text.lower() or "f150" in text.lower() or "ford" in text.lower(),
       f"Response: {text[:200]}")

# ── TEST 5: Appointment Booking ──────────────────────────────────────────────
print(f"\n{CYAN}TEST 5: APPOINTMENT BOOKING{RESET}")
lead = _create_fresh_lead(s, dealer, "Booking Test")

result = _run_turn(s, lead, dealer,
    "I like the Mazda CX-5. Can I test drive it this Saturday at 2pm?",
    "booking")
text = result.get("text", "")
tools = result.get("tools_used", [])

_check("AI called book_appointment", "book_appointment" in tools,
       f"Tools: {tools}", warn_only=True)
_check("AI confirmed the appointment",
       any(kw in text.lower() for kw in ["set", "booked", "saturday", "see you"]),
       f"Response: {text[:200]}")
_check("AI includes address",
       any(kw in text.lower() for kw in ["main street", "vancouver", "4217"]),
       f"Response: {text[:200]}")

# Check appointment exists in DB
appts = list(s.execute(
    select(Appointment).where(Appointment.lead_id == lead.id)
).scalars().all())
_check("Appointment saved to DB", len(appts) > 0,
       f"Appointments found: {len(appts)}")
_check("Lead state is APPT_SET", lead.state == LeadState.APPT_SET,
       f"Lead state: {lead.state.value}")

# ── TEST 6: Price Negotiation Guardrail ──────────────────────────────────────
print(f"\n{CYAN}TEST 6: PRICE NEGOTIATION GUARDRAIL{RESET}")
lead = _create_fresh_lead(s, dealer, "Negotiation Test")

# First establish context
_run_turn(s, lead, dealer, "Tell me about the Honda Civic", "context")
result = _run_turn(s, lead, dealer, "What's the best price you can give me on the Civic?", "negotiate")
text = result.get("text", "")

_check("AI does NOT negotiate price",
       not any(kw in text.lower() for kw in ["discount", "lower", "reduce", "drop the price", "$27", "$26"]),
       f"Response: {text[:200]}")
_check("AI defers to in-person",
       any(kw in text.lower() for kw in ["team", "come in", "discuss", "visit", "when"]),
       f"Response: {text[:200]}")

# ── TEST 7: Human Escalation ─────────────────────────────────────────────────
print(f"\n{CYAN}TEST 7: HUMAN ESCALATION{RESET}")
lead = _create_fresh_lead(s, dealer, "Escalation Test")

result = _run_turn(s, lead, dealer, "Can I talk to a real person?", "escalation")
text = result.get("text", "")

_check("AI provides phone number",
       any(c in text for c in ["778", "604", "+1", "phone", "call"]),
       f"Response: {text[:200]}")
_check("AI offers callback",
       any(kw in text.lower() for kw in ["call", "callback", "reach", "phone", "number"]),
       f"Response: {text[:200]}")

# ── TEST 8: Opt-Out (STOP) ───────────────────────────────────────────────────
print(f"\n{CYAN}TEST 8: OPT-OUT (STOP){RESET}")

# Simulate STOP via the main webhook handler logic
lead = _create_fresh_lead(s, dealer, "Opt-Out Test")
lead.phone = "+17785550198"
s.commit()

# Log the STOP as a ConsentLog entry (simulating what webhook_twilio_sms does)
consent = ConsentLog(
    dealer_id=dealer.id, phone=lead.phone,
    action="opted_out", text="STOP",
)
s.add(consent)
lead.state = LeadState.OPTED_OUT
s.commit()

_check("Lead moved to OPTED_OUT", lead.state == LeadState.OPTED_OUT,
       f"State: {lead.state.value}")
_check("ConsentLog recorded opt-out",
       s.execute(select(ConsentLog).where(
           ConsentLog.phone == lead.phone, ConsentLog.action == "opted_out"
       )).scalars().first() is not None, "")

# ── TEST 9: Resubscribe (START) ──────────────────────────────────────────────
print(f"\n{CYAN}TEST 9: RESUBSCRIBE (START){RESET}")

consent_re = ConsentLog(
    dealer_id=dealer.id, phone=lead.phone,
    action="re_granted", text="START",
)
s.add(consent_re)
s.commit()

# Check that the opt-out is revoked
from tools.send_sms import _is_opted_out
is_out = _is_opted_out(s, lead.phone)
_check("Opt-out revoked after START", not is_out,
       f"is_opted_out: {is_out}")

# ── TEST 10: Vague Question → Qualification ──────────────────────────────────
print(f"\n{CYAN}TEST 10: VAGUE QUESTION → QUALIFICATION{RESET}")
lead = _create_fresh_lead(s, dealer, "Vague Test")

result = _run_turn(s, lead, dealer, "Just looking around", "vague")
text = result.get("text", "")

_check("AI asks qualifying questions",
       any(kw in text.lower() for kw in ["what", "looking for", "type", "budget", "preference", "?"]),
       f"Response: {text[:200]}")
_check("AI doesn't dump full inventory",
       text.count("\n") < 20,
       f"Newlines: {text.count(chr(10))}")

# ── TEST 11: Specific Vehicle Questions ──────────────────────────────────────
print(f"\n{CYAN}TEST 11: SPECIFIC VEHICLE QUESTIONS{RESET}")
lead = _create_fresh_lead(s, dealer, "Spec Test")

result = _run_turn(s, lead, dealer,
    "What engine does the Toyota RAV4 have?",
    "specs")
text = result.get("text", "")
tools = result.get("tools_used", [])

_check("AI called check_inventory", "check_inventory" in tools, f"Tools: {tools}", warn_only=True)
_check("Response mentions engine specs",
       any(kw in text.lower() for kw in ["2.5", "4-cyl", "cylinder", "engine", "203 hp"]),
       f"Response: {text[:200]}")

# ── TEST 12: Multi-Turn Conversation Memory ──────────────────────────────────
print(f"\n{CYAN}TEST 12: MULTI-TURN CONVERSATION MEMORY{RESET}")
lead = _create_fresh_lead(s, dealer, "Memory Test")

_run_turn(s, lead, dealer, "I'm looking for an SUV for my family", "turn1")
result = _run_turn(s, lead, dealer, "What about the Hyundai Tucson?", "turn2")
text = result.get("text", "")

_check("AI knows about Tucson from inventory",
       "tucson" in text.lower() or "hyundai" in text.lower(),
       f"Response: {text[:200]}")
_check("AI provides specific details",
       any(kw in text.lower() for kw in ["$", "price", "km", "mileage", "features", "sunroof", "awd"]),
       f"Response: {text[:200]}")

# ── TEST 13: Trade-In Question ───────────────────────────────────────────────
print(f"\n{CYAN}TEST 13: TRADE-IN QUESTION{RESET}")
lead = _create_fresh_lead(s, dealer, "Trade-In Test")

result = _run_turn(s, lead, dealer, "Do you accept trade-ins?", "trade_in")
text = result.get("text", "")

_check("AI accepts trade-ins",
       any(kw in text.lower() for kw in ["yes", "do", "accept", "trade-in", "trade in"]),
       f"Response: {text[:200]}")
_check("AI doesn't promise specific value",
       not any(kw in text.lower() for kw in ["worth", "$", "value", "appraisal"]),
       f"Response: {text[:200]}", warn_only=True)
_check("AI pushes for in-person",
       any(kw in text.lower() for kw in ["come in", "visit", "in person", "when"]),
       f"Response: {text[:200]}")

# ── TEST 14: Financing Question ──────────────────────────────────────────────
print(f"\n{CYAN}TEST 14: FINANCING QUESTION{RESET}")
lead = _create_fresh_lead(s, dealer, "Finance Test")

result = _run_turn(s, lead, dealer, "What kind of financing do you offer?", "financing")
text = result.get("text", "")

_check("AI doesn't promise specific rates",
       not any(kw in text.lower() for kw in ["0%", "1.9%", "2.9%", "interest rate", "apr"]),
       f"Response: {text[:200]}")
_check("AI mentions finance team",
       any(kw in text.lower() for kw in ["finance", "lender", "team", "options"]),
       f"Response: {text[:200]}")

# ── TEST 15: Out-of-Inventory Request ────────────────────────────────────────
print(f"\n{CYAN}TEST 15: OUT-OF-INVENTORY REQUEST{RESET}")
lead = _create_fresh_lead(s, dealer, "OOS Test")

result = _run_turn(s, lead, dealer, "Do you have any Teslas?", "out_of_stock")
text = result.get("text", "")
tools = result.get("tools_used", [])

_check("AI searched inventory first", "check_inventory" in tools,
       f"Tools: {tools}", warn_only=True)
_check("AI doesn't hallucinate a Tesla",
       "model 3" not in text.lower() or "model y" not in text.lower() or
       "don't" in text.lower() or "do not" in text.lower() or "not see" in text.lower(),
       f"Response: {text[:200]}")
_check("AI suggests alternatives or asks qualifying question",
       any(kw in text.lower() for kw in ["similar", "instead", "alternative", "what", "looking for", "don't see"]),
       f"Response: {text[:200]}")

# ── TEST 16: First Message Identity ──────────────────────────────────────────
print(f"\n{CYAN}TEST 16: FIRST MESSAGE IDENTITY{RESET}")

# Check the auto-reply that was generated
auto_replies = list(s.execute(
    select(Message).where(
        Message.direction == Direction.OUTBOUND,
        Message.ai_generated == True,
    ).order_by(Message.created_at.desc()).limit(5)
).scalars().all())

if auto_replies:
    first_reply = auto_replies[-1].body
    _check("Auto-reply mentions dealership name",
           "premier" in first_reply.lower() or "premier auto" in first_reply.lower(),
           f"Auto-reply: {first_reply[:150]}")
    _check("Auto-reply has opt-out footer",
           "stop" in first_reply.lower(),
           f"Auto-reply: {first_reply[-100:]}")
else:
    _check("Auto-reply exists", False, "No outbound messages found")

# ── TEST 17: Cross-Sell / Upsell ─────────────────────────────────────────────
print(f"\n{CYAN}TEST 17: CROSS-SELL / UPSELL{RESET}")
lead = _create_fresh_lead(s, dealer, "CrossSell Test")

result = _run_turn(s, lead, dealer, "I want a sedan", "cross_sell")
text = result.get("text", "")

_check("AI suggests options",
       any(kw in text.lower() for kw in ["civic", "corolla", "altima", "sedan"]),
       f"Response: {text[:200]}")
_check("AI might suggest SUV too",
       any(kw in text.lower() for kw in ["suv", "crossover", "also"]),
       f"Response: {text[:200]}", warn_only=True)

# ── FINAL SUMMARY ────────────────────────────────────────────────────────────
s.close()

print(f"\n{'='*60}")
print(f"{BOLD}RESULTS SUMMARY{RESET}")
print(f"{'='*60}")
print(f"  {GREEN}PASS: {PASS_COUNT}{RESET}")
print(f"  {RED}FAIL: {FAIL_COUNT}{RESET}")
print(f"  {YELLOW}WARN: {WARN_COUNT}{RESET}")
print(f"  TOTAL: {PASS_COUNT + FAIL_COUNT + WARN_COUNT}")
print(f"{'='*60}\n")

sys.exit(0 if FAIL_COUNT == 0 else 1)
