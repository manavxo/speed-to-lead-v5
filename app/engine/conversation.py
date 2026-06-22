"""AI conversation orchestration (the only place Claude/OpenRouter is called).

Flow: load the relevant workflow SOP (workflows/*.md) + the dealer's AI config + the pinned
vehicle context -> call OpenRouter with the tool definitions -> if the model requests a tool,
execute the deterministic tool and loop -> return the assistant turn.

Grounding rule: the model may only state facts returned by tools (e.g. check_inventory). It must
never invent a car/price. Tools are the only path to side effects.

Autonomy is hybrid by time-of-day (see is_business_hours): business hours -> draft for rep
approval; after hours -> send autonomously.

TODO: Docs say Claude but the code uses OpenRouter/Gemini.  Leave it; the provider swap is a
one-line config change when Anthropic creds are available.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

logger = logging.getLogger("speed-to-lead.conversation")

# ---------------------------------------------------------------------------
# Retry configuration for OpenRouter API calls
# ---------------------------------------------------------------------------
_MAX_RETRIES = 3
_RETRY_BACKOFF = (1, 2, 4)           # seconds between retries (exponential)
_TIMEOUT_SECONDS = 10                 # per-request timeout
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}

# ---------------------------------------------------------------------------
# Max conversation turns before escalating to human handoff
# ---------------------------------------------------------------------------
MAX_INBOUND_TURNS = 10


# ---------------------------------------------------------------------------
# OpenAI client singleton (P0-03)
# ---------------------------------------------------------------------------
_OPENAI_CLIENT = None


def _get_openai_client():
    """Lazy module-level singleton for the AI model client.

    Uses DeepSeek direct API when DEEPSEEK_API_KEY is configured (cheaper).
    Falls back to OpenRouter when only OPENROUTER_API_KEY is set.
    Instantiated on first use, then reused for the lifetime of the process.
    Replaces the per-request `OpenAI(...)` call that was leaking connections
    under load. Safe to call from any thread.
    """
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is None:
        from openai import OpenAI
        from app.config import settings as _settings

        if _settings.deepseek_api_key:
            base_url = _settings.deepseek_base_url
            api_key = _settings.deepseek_api_key
        else:
            base_url = _settings.openrouter_base_url
            api_key = _settings.openrouter_api_key

        _OPENAI_CLIENT = OpenAI(base_url=base_url, api_key=api_key)
    return _OPENAI_CLIENT


def _get_model_name() -> str:
    """Return the model name for the active AI provider.

    DeepSeek direct uses 'deepseek-v4-flash' (no OpenRouter prefix).
    OpenRouter uses the full path 'deepseek/deepseek-v4-flash'.
    """
    from app.config import settings as _settings
    if _settings.deepseek_api_key:
        return "deepseek-v4-flash"
    return _settings.openrouter_model


def is_business_hours(dealer_config: dict, now: datetime | None = None) -> bool:
    """True if `now` falls inside the dealer's open hours (in the dealer timezone).

    Parses dealer.hours[weekday] ("HH:MM-HH:MM"/"closed"), converts now to dealer tz.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    tz_name = dealer_config.get("dealer", {}).get("timezone", "America/Vancouver")
    hours = dealer_config.get("dealer", {}).get("hours", {})

    try:
        from zoneinfo import ZoneInfo
        local_now = now.astimezone(ZoneInfo(tz_name))
    except Exception:
        local_now = now

    # Map weekday number to day key
    day_keys = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    day_key = day_keys[local_now.weekday()]

    day_hours = hours.get(day_key, "closed")
    if day_hours == "closed" or not day_hours:
        return False

    try:
        open_str, close_str = day_hours.split("-")
        open_h, open_m = map(int, open_str.split(":"))
        close_h, close_m = map(int, close_str.split(":"))

        current_minutes = local_now.hour * 60 + local_now.minute
        open_minutes = open_h * 60 + open_m
        close_minutes = close_h * 60 + close_m

        return open_minutes <= current_minutes < close_minutes
    except (ValueError, AttributeError):
        return False


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "check_inventory",
            "description": "Search the dealer's vehicle inventory. Use this before quoting any car, price, or availability. NEVER invent vehicle information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword (make, model, etc.)"},
                    "max_price": {"type": "number", "description": "Maximum price filter"},
                    "body": {"type": "string", "description": "Body style filter (SUV, Sedan, etc.)"},
                    "make": {"type": "string", "description": "Filter by vehicle make (e.g. Hyundai, Honda, Toyota)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Check available appointment slots for the next 7 days. Returns ONLY valid slots during business hours that are not already booked. Use this BEFORE suggesting any appointment times. NEVER invent time slots.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {"type": "number", "description": "How many days to check (default 7)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book a test drive or visit appointment. Use this when a customer wants to see a vehicle, test drive, or visit the dealership. ONLY offer times returned by check_availability.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_time": {"type": "string", "description": "ISO 8601 datetime for the appointment (e.g. 2026-06-12T14:00:00). Must be a slot returned by check_availability."},
                    "notes": {"type": "string", "description": "What the appointment is for (e.g. 'Test drive of 2023 Honda Civic Sport', 'Look at SUVs under $30k')"},
                },
                "required": ["date_time"],
            },
        },
    },
]


def _execute_tool_call(
    tool_name: str,
    arguments_json: str,
    *,
    session: Session | None = None,
    lead=None,
    dealer_id: int | None = None,
    dealer_config: dict | None = None,
) -> dict:
    """Execute a tool call requested by the AI model.

    All side effects go through deterministic code - the model only reasons.
    Dispatches to real tools (check_inventory.search, book_appointment.book_appointment).
    """
    try:
        args = json.loads(arguments_json) if arguments_json else {}
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse tool args for %s: %s", tool_name, arguments_json)
        args = {}

    if tool_name == "check_inventory":
        if session and dealer_id is not None:
            from tools.check_inventory import search
            vehicles = search(
                session, dealer_id,
                query=args.get("query"),
                max_price=args.get("max_price"),
                body=args.get("body"),
                make=args.get("make"),
                limit=5,
            )
            if not vehicles:
                return {"vehicles": [], "message": "No matching vehicles found."}
            results = []
            for v in vehicles:
                price_str = f"${v.price:,.0f}" if v.price else "TBD"
                specs = v.raw or {}
                result_entry = {
                    "stock_no": v.stock_no,
                    "year": v.year,
                    "make": v.make,
                    "model": v.model,
                    "trim": v.trim,
                    "price": price_str,
                    "mileage": f"{v.mileage:,} km" if v.mileage else "TBD",
                    "body": v.body,
                    "status": v.status,
                }
                result_entry["specs"] = {
                    "engine": specs.get("engine"),
                    "transmission": specs.get("transmission"),
                    "drivetrain": specs.get("drivetrain"),
                    "horsepower": specs.get("horsepower"),
                    "fuel_economy": specs.get("fuel_economy"),
                    "exterior_color": specs.get("exterior_color") or specs.get("color"),
                    "interior": specs.get("interior"),
                    "range": specs.get("range"),
                    "features": specs.get("features", [])[:5],
                }
                results.append(result_entry)
            return {"vehicles": results, "count": len(results)}
        return {"vehicles": [], "message": "No matching vehicles found."}

    elif tool_name == "check_availability":
        if session and dealer_id is not None:
            from tools.check_availability import check_availability as check_avail
            slots = check_avail(
                session, dealer_id,
                days_ahead=args.get("days_ahead", 7),
                dealer_config=dealer_config,
            )
            if not slots:
                return {"slots": [], "message": "No available slots in the next 7 days."}
            return {"slots": slots, "count": len(slots)}
        return {"slots": [], "message": "Cannot check availability right now."}

    elif tool_name == "book_appointment":
        if session and lead is not None:
            from datetime import datetime as dt
            from tools.book_appointment import book_appointment
            try:
                dt_str = args.get("date_time", "")
                if dt_str:
                    scheduled_for = dt.fromisoformat(dt_str)
                else:
                    # No date provided — default to next business day at 10am
                    from datetime import timedelta
                    now = dt.now(timezone.utc)
                    scheduled_for = now + timedelta(days=1)
                    scheduled_for = scheduled_for.replace(hour=18, minute=0, second=0, microsecond=0)
                    # If that's a Sunday, move to Monday
                    if scheduled_for.weekday() == 6:
                        scheduled_for += timedelta(days=1)

                logger.info("Booking appointment: lead=%s, scheduled_for=%s, notes=%s",
                           lead.id, scheduled_for.isoformat(), args.get("notes"))

                appt = book_appointment(
                    session, lead, scheduled_for,
                    notes=args.get("notes"),
                    dealer_config=dealer_config,
                )
                return {
                    "status": "booked",
                    "appointment_id": appt.id,
                    "scheduled_for": scheduled_for.isoformat(),
                    "message": "Appointment booked successfully!",
                }
            except ValueError as e:
                logger.warning("book_appointment rejected: %s", e)
                return {"status": "error", "message": str(e)}
            except Exception:
                logger.exception("book_appointment failed")
                return {"status": "error", "message": "Could not book appointment. Please try again."}
        return {"status": "pending", "message": "Appointment request noted."}

    else:
        return {"error": f"Unknown tool: {tool_name}"}


WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / "workflows"


def load_workflow(name: str) -> str:
    """Read a markdown SOP from workflows/ to inject into the system prompt."""
    path = WORKFLOWS_DIR / name
    if not path.exists():
        return f"(workflow '{name}' not found)"
    return path.read_text(encoding="utf-8")


def build_system_prompt(dealer_config: dict, vehicle_context: str | None = None) -> str:
    """Assemble the system prompt from the dealer config + workflow SOPs + vehicle context."""
    ai_config = dealer_config.get("ai", {})
    persona = ai_config.get("persona", "friendly, concise, no-pressure local sales rep")
    goal = ai_config.get("goal", "book_appointment")
    guardrails = ai_config.get("guardrails", {})
    business_facts = ai_config.get("business_facts", "")
    engagement_mode = ai_config.get("engagement_mode", "full_auto")

    dealer = dealer_config.get("dealer", {})
    dealer_name = dealer.get("name", "the dealership")
    dealer_phone = dealer.get("main_phone", "")
    dealer_address = dealer.get("location_address", "")
    dealer_hours = dealer.get("hours", {})

    # Format hours as human-readable text
    hours_text = ""
    if dealer_hours:
        day_names = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday",
                     "thu": "Thursday", "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}
        hours_lines = []
        for day_key in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]:
            val = dealer_hours.get(day_key, "closed")
            day_name = day_names.get(day_key, day_key)
            if val == "closed" or not val:
                hours_lines.append(f"  {day_name}: Closed")
            else:
                hours_lines.append(f"  {day_name}: {val}")
        hours_text = "\n".join(hours_lines)

    # Inject current date/time so the LLM can resolve relative dates
    tz_name = dealer.get("timezone", "America/Vancouver")
    try:
        from zoneinfo import ZoneInfo
        now_local = datetime.now(timezone.utc).astimezone(ZoneInfo(tz_name))
    except Exception:
        now_local = datetime.now(timezone.utc)
    today_line = (
        f"CURRENT DATE AND TIME: {now_local.strftime('%A, %B %d, %Y at %I:%M %p %Z')} "
        f"(timezone: {tz_name})"
    )

    prompt_parts = [
        today_line,
        "",
        f"You are a {persona} at {dealer_name}.",
        f"When greeting a new customer, introduce yourself as being from {dealer_name}.",
        f"Your primary goal is to {goal} — get the customer to commit to a specific time to visit.",
        "",
        "When a customer says a relative date like 'Monday' or 'next Saturday', use the current",
        "date above to calculate the exact ISO 8601 datetime. Always use the NEAREST future date",
        "that matches. For example, if today is Sunday June 7 and they say 'Monday', use Monday",
        "June 8 (tomorrow), not Monday June 15.",
        "",
        "═══ CRITICAL RULES ═══",
        "",
        "1. ALWAYS use the check_inventory tool before quoting ANY vehicle, price, or availability.",
        "   NEVER invent, guess, or hallucinate vehicle information. If you haven't called the tool, you don't know the answer.",
        "",
        "2. When a customer asks about vehicles (by type, budget, make, or feature), ALWAYS call check_inventory with relevant filters:",
        "   - 'What SUVs do you have?' → call check_inventory with body='SUV'",
        "   - 'Anything under $20k?' → call check_inventory with max_price=20000",
        "   - 'Do you have Hondas?' → call check_inventory with make='Honda'",
        "   - 'Tell me about the BMW' → call check_inventory with make='BMW'",
        "   - 'What about the Hyundai Tucson?' → call check_inventory with make='Hyundai', query='Tucson'",
        "   - 'Cheapest SUV?' → call check_inventory with body='SUV' (then pick the lowest price from results)",
        "   - 'What colors does it come in?' → call check_inventory with query='<make model>' (specs are in the results)",
        "   - 'What engine does it have?' → call check_inventory with query='<make model>' (specs are in the results)",
        "",
        "3. When check_inventory returns results, the 'specs' object contains detailed vehicle information.",
        "   Use it to answer questions about: engine, transmission, drivetrain, horsepower, fuel economy,",
        "   exterior color, interior, range, and features. Always share 2-3 relevant specs when discussing a vehicle.",
        "",
        "5. When check_inventory returns NO results, say: 'I don't see any matching vehicles in our current inventory, ",
        "   but our stock changes frequently. Let me check with our team — what's the best number to reach you at?'",
        "",
        "═══ SALES INTELLIGENCE ═══",
        "",
        "You are a seasoned sales professional, not just an order taker. Your job is to HELP the customer find the right vehicle, even if it's not what they originally asked for.",
        "",
        "CROSS-SELL & UPSELL:",
        "- If a customer asks for a sedan, suggest test-driving an SUV too — 'A lot of our customers who come in for a sedan end up loving the higher seating position of an SUV. Want to compare both when you come in?'",
        "- If a customer mentions a budget, show vehicles slightly above AND below — 'I found something perfect at $28k, and there's also a loaded version at $33k that might be worth the stretch.'",
        "- If a customer is focused on one make, mention comparable alternatives — 'The Civic is great, but the Corolla has a similar feel with better fuel economy. Want to see both?'",
        "",
        "REDIRECTING WHEN NOT IN STOCK:",
        "- If check_inventory returns nothing matching, DON'T just say 'we don't have it'",
        "- Suggest the closest alternatives from what IS in stock",
        "- Ask qualifying questions to narrow down what they REALLY need",
        "- 'I don't see a [exact request] right now, but I have [similar option] that checks most of your boxes. What specifically drew you to [original request]?'",
        "",
        "READING CUSTOMER INTENT:",
        "- 'Just looking' → They're interested but not committed. Show 1-2 exciting options to hook them.",
        "- 'What's the cheapest?' → Price-sensitive. Focus on value, not features. Show the best deal.",
        "- 'I want [specific car]' → High intent. Get them in FAST. Book immediately.",
        "- Comparing vehicles → They're close to buying. Help them decide, don't overwhelm.",
        "- Asking about trade-in → They're serious. Push for appointment.",
        "- Vague questions → Ask 2-3 qualifying questions before showing inventory.",
        "",
        "SALES CONVERSATION TECHNIQUES:",
        "- Use the 'feel, felt, found' method: 'I understand how you feel. A lot of our customers felt the same way, but they found that...'",
        "- Create urgency naturally: 'This one's been getting a lot of interest' or 'We only have 2 in this color'",
        "- Use social proof: 'This is our most popular model' or 'We've had 3 families come in for this one this week'",
        "- Always have a next step: never end a message without a question or call to action",
        "",
        "5. Never list more than 3-5 vehicles at once. Curate the best matches and ask a follow-up question.",
        "",
        "6. Always end your message with a question or clear next step to keep the conversation moving.",
        "",
        "═══ BOOKING APPOINTMENTS (YOUR #1 JOB) ═══",
        "",
        "You have two tools: check_availability and book_appointment. USE BOTH.",
        "",
        "YOU MUST call check_availability BEFORE offering any time slots.",
        "If check_availability returns 0 slots, say: 'We don't have any availability",
        "right now — let me connect you with our team to find a time that works.'",
        "",
        "ONLY offer slots that check_availability returned. NEVER invent a time.",
        "If a customer asks for a specific time NOT in the returned slots, politely",
        "offer the closest available alternative.",
        "",
        "When to book (don't wait for the perfect moment — any of these is enough):",
        "  - Customer says they want to see a vehicle in person",
        "  - Customer asks 'when can I come in?' or 'can I test drive it?'",
        "  - Customer shows strong interest (asks detailed questions, compares vehicles, mentions budget)",
        "  - Customer says 'sure', 'okay', 'sounds good', 'let's do it', or similar agreement",
        "  - You've shown 2-3 vehicles and the customer likes one",
        "  - Customer gives you ANY specific date/time (e.g., 'Monday at 6pm', 'next Saturday')",
        "",
        "How to book:",
        "  1. FIRST call check_availability() to get available slots.",
        "  2. Suggest 1-2 slots from the returned list.",
        "  3. When the customer picks a slot, call book_appointment with that ISO 8601 datetime.",
        "  4. After booking, confirm: 'You're all set! We'll see you [day] at [time] at [address].",
        "     Bring your driver's license. Looking forward to it!'",
        "",
        "NEVER book without calling check_availability first.",
        "NEVER invent time slots that check_availability didn't return.",
        "The system enforces: no bookings outside business hours and no double-bookings.",
        "Only the slots from check_availability are valid.",
        "",
        "═══ HANDLING OBJECTIONS (BE INDEPENDENT) ═══",
        "",
        "You are a capable sales assistant. Handle these yourself before escalating:",
        "",
        "  - Price questions: 'Great question — the team can discuss pricing when you come in. When works for a visit?'",
        "  - Trade-in: 'We do accept trade-ins! The team will give you a fair appraisal when you come in. What are you driving now?'",
        "  - Financing: 'Our finance team works with multiple lenders to find the best option. They'll walk you through everything in person.'",
        "  - Vehicle condition: 'All our vehicles go through a thorough inspection. Come see it in person — you'll love it.'",
        "  - Availability: Call check_inventory first. If in stock, say: 'Yes, it's available! Want to come see it this week?'",
        "  - Comparison questions: Call check_inventory for both vehicles and help them compare.",
        "",
        "ONLY escalate to a human when:",
        "  - Customer explicitly asks: 'Can I talk to a real person?' / 'Let me speak to a manager'",
        "  - You've tried 3+ times to book and they keep deflecting",
        "  - The question is about legal, warranty claims, or existing service issues",
        "",
        "When escalating, ALWAYS provide the dealership phone number so they can call directly.",
        "Say: 'Of course! You can reach us at [phone number], or I can have someone call you. What's best?'",
        "",
        "═══ CONNECTING TO A SALESPERSON ═══",
        "",
        "When a customer asks to speak to someone, or when you need to hand off:",
        "  - Give them the phone number: 'You can call us directly at [phone number]'",
        "  - Offer a callback: 'I can have someone from our team give you a call. What's the best number to reach you?'",
        "  - If they're frustrated, acknowledge it: 'I understand — let me get you connected with our team right away.'",
        "  - NEVER say 'I'll have someone reach out' without giving them a direct way to contact you.",
        "",
        "IDENTITY & CONTACT INFO:",
        f"  Dealership: {dealer_name}",
    ]
    if dealer_address:
        prompt_parts.append(f"  Address: {dealer_address}")
    if dealer_phone:
        prompt_parts.append(f"  Phone: {dealer_phone}")
        prompt_parts.append(f"  Phone (for connecting customers): {dealer_phone}")
    if hours_text:
        prompt_parts.append(f"  Business Hours (for reference when suggesting times — NOT a booking restriction):\n{hours_text}")
    prompt_parts.append("")

    # Guardrails
    prompt_parts.append("GUARDRAILS:")
    if guardrails.get("no_price_negotiation"):
        prompt_parts.append(
            "- Do NOT negotiate on price. If a customer asks for a discount, say: "
            "'That's a great question — the team can discuss pricing and any current promotions "
            "when you come in. When would you like to take a look?'"
        )
    if guardrails.get("no_financing_promises"):
        prompt_parts.append(
            "- Do NOT make specific financing promises, quote interest rates, or guarantee approval. "
            "Say: 'Our finance team works with multiple lenders to find the best option for your situation. "
            "They'll walk you through everything when you come in.'"
        )
    prompt_parts.extend([
        "- Do NOT provide legal advice. For legal questions, say: 'I'd need to connect you with our management team for that.'",
        "- Do NOT make guarantees about vehicle condition, reliability, or future performance.",
        "- Do NOT argue with frustrated customers. De-escalate and offer to connect them with a team member.",
        "- Stay on topic (vehicles, test drives, appointments, dealership). If asked about unrelated topics, politely redirect.",
    ])

    prompt_parts.append("")

    # Engagement mode instructions
    if engagement_mode == "qualify_only":
        prompt_parts.extend([
            "═══ ENGAGEMENT MODE: QUALIFY ONLY ═══",
            "",
            "Your role is LIMITED to initial greeting and qualification.",
            f"After greeting the customer and asking 2-3 qualifying questions about what they're looking for,",
            f"say: 'Let me connect you with one of our sales specialists at {dealer_name} who can help you further.'",
            "Then transition the conversation to a human rep. Do NOT attempt to book appointments or show inventory.",
            "",
        ])
    elif engagement_mode == "greeting_only":
        prompt_parts.extend([
            "═══ ENGAGEMENT MODE: GREETING ONLY ═══",
            "",
            f"Your ONLY job is to send this ONE greeting: 'Hi! Thanks for reaching out to {dealer_name}. A member of our team will be with you shortly!'",
            "Do NOT ask questions, show inventory, or attempt to book. Just send the greeting and let the human team take over.",
            "",
        ])

    # Vehicle context for a pinned vehicle (from web form inquiry)
    if vehicle_context:
        prompt_parts.append(
            f"THE CUSTOMER INQUIRED ABOUT THIS SPECIFIC VEHICLE:\n{vehicle_context}\n"
            f"Start by confirming interest in this vehicle, then work toward booking a visit.\n"
        )

    prompt_parts.extend([
        "",
        "═══ BUSINESS FACTS (you may ONLY state these verbatim) ═══",
        "",
        "The dealership has provided these specific facts. You may repeat them",
        "verbatim when relevant. For ANYTHING not listed below, you MUST defer:",
        "'Let me check with the team on that and get back to you.'",
        "",
        f"{business_facts or '(no specific business facts provided — defer ALL factual questions)'}",
        "",
        "CONVERSATION STYLE:",
        "- Messages can be up to 1400 characters. A compliance footer (dealer name + opt-out instruction) will be automatically appended to your message, so leave room for it.",
        "- Format longer responses neatly: use line breaks between topics, bullet points (•) for vehicle lists,",
        "  and keep paragraphs short. Example:",
        "    Here are our SUVs under $35k:",
        "    ",
        "    • 2023 Hyundai Tucson Preferred — $29,900 (18,000 km)",
        "      Great fuel economy, loaded with tech features",
        "    ",
        "    • 2023 Mazda CX-5 GX — $31,200 (14,500 km)",
        "      Premium interior, smooth ride",
        "    ",
        "    Which one catches your eye? I can set up a test drive for you this week!",
        "- Be warm and natural, like talking to a friend who works at a dealership.",
        "- Use the customer's name occasionally if you know it.",
        "- If the customer is vague or 'just browsing', use check_inventory to suggest 1-3 relevant vehicles.",
        "- If the customer says 'I'll think about it' or 'not now', be polite and mention you'll follow up.",
        "- For trade-in questions: acknowledge they accept trade-ins, but details are handled in-person.",
        "",
        "MESSAGE DELIVERABILITY RULES:",
        "- Keep messages under 300 characters when possible for best delivery",
        "- NEVER use ALL CAPS for emphasis — use natural language",
        "- Avoid excessive punctuation (!!!, ???)",
        "- NEVER include URLs in messages — the customer already has your contact info",
        "- Include your dealership name in your FIRST message to establish identity",
        "- Avoid spam trigger words: 'free', 'winner', 'congrats', 'act now', 'limited time'",
        "- Keep messages conversational and natural — you're a real person at a dealership",
        "",
        "CONVERSATION ARC (don't rush — let it flow naturally):",
        "1. Confirm what they're looking for",
        "2. Show relevant inventory (via check_inventory tool)",
        "3. Light qualification: timeline, trade-in?, financing?",
        "4. Offer 2 concrete appointment times (not 'when works for you?')",
        "5. Book the appointment and confirm with date/time/address",
    ])

    # Load relevant workflow
    workflow = load_workflow("qualify_and_book.md")
    prompt_parts.append(f"\nREFERENCE WORKFLOW:\n{workflow}")

    return "\n\n".join(prompt_parts)


def handle_turn(
    session: Session,
    lead,
    inbound_text: str,
    *,
    dealer_config: dict,
    vehicle=None,
    fake_llm=None,
    now: datetime | None = None,
    is_proactive: bool = False,
) -> dict:
    """Produce the next assistant turn for `lead`.

    Returns a dict describing the action: {"mode": "send"|"draft", "text": ..., "tools_used": [...]}.

    When is_proactive=True, this is the AI's first outreach after a webform submission.
    The AI should use the form context (name, vehicle interest, message) to craft a
    personalized engagement message — not wait for the customer to message first.

    In business hours: mode="draft" (rep approves before sending).
    After hours: mode="send" (autonomous).

    After MAX_INBOUND_TURNS inbound messages without resolution (lead still ENGAGED),
    sends a handoff message, transitions the lead to ASSIGNED, and logs a
    'max_turns_reached' LeadEvent.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Engagement mode checks
    # ------------------------------------------------------------------
    ai_config = dealer_config.get("ai", {})
    engagement_mode = ai_config.get("engagement_mode", "full_auto")
    dealer_name = dealer_config.get("dealer", {}).get("name", "the dealership")

    if engagement_mode == "greeting_only" and session is not None and lead is not None:
        from sqlalchemy import func, select
        from app.models import Direction, LeadEvent, LeadState, Message

        inbound_count = session.execute(
            select(func.count()).where(
                Message.lead_id == lead.id,
                Message.direction == Direction.INBOUND,
            )
        ).scalar() or 0

        # Only send greeting on first inbound message
        if inbound_count <= 1:
            greeting = f"Hi! Thanks for reaching out to {dealer_name}. A member of our team will be with you shortly!"

            from app.engine.lifecycle import transition
            transition(
                session, lead, LeadState.ASSIGNED,
                reason="greeting_only_mode",
                meta={"inbound_count": inbound_count},
            )

            return {
                "mode": "send",
                "text": greeting,
                "is_business_hours": is_business_hours(dealer_config, now),
                "tools_used": [],
                "engagement_mode": "greeting_only",
            }

    if engagement_mode == "qualify_only" and session is not None and lead is not None:
        from sqlalchemy import func, select
        from app.models import Direction, LeadEvent, LeadState, Message

        inbound_count = session.execute(
            select(func.count()).where(
                Message.lead_id == lead.id,
                Message.direction == Direction.INBOUND,
            )
        ).scalar() or 0

        # After 3+ turns of qualification, hand off to human
        if inbound_count >= 3 and lead.state == LeadState.ENGAGED:
            handoff = (
                f"Let me connect you with one of our sales specialists at {dealer_name} who can help you further. "
                f"A team member will reach out to you shortly!"
            )
            from app.engine.lifecycle import transition
            transition(
                session, lead, LeadState.ASSIGNED,
                reason="qualify_only_handoff",
                meta={"inbound_count": inbound_count},
            )
            return {
                "mode": "send",
                "text": handoff,
                "is_business_hours": is_business_hours(dealer_config, now),
                "tools_used": [],
                "engagement_mode": "qualify_only",
            }

    # ------------------------------------------------------------------
    # Proactive AI follow-up: engage customer immediately after webform
    # ------------------------------------------------------------------
    if is_proactive:
        # For proactive messages, we want the AI to craft a personalized
        # opening based on form data. Skip max-turns guard — this is turn 0.
        is_biz = is_business_hours(dealer_config, now)

        vehicle_context = None
        if vehicle:
            price_str = f"${vehicle.price:,.0f}" if vehicle.price else "TBD"
            vehicle_context = (
                f"{vehicle.year} {vehicle.make} {vehicle.model} {vehicle.trim or ''} — {price_str}"
            )

        system_prompt = build_system_prompt(dealer_config, vehicle_context)

        # Add proactive instruction to system prompt
        proactive_instruction = (
            "\n\n[PROACTIVE OUTREACH]: The customer just submitted a webform. "
            "You are initiating the conversation — they have NOT messaged you yet. "
            "Introduce yourself, reference their specific interest (vehicle, budget, etc.), "
            "and ask an engaging question to start the qualification conversation. "
            "Be warm, personal, and specific to their inquiry. "
            "Keep it under 3 sentences. Do NOT ask them to 'let you know' — ask a specific question."
        )

        tools_used: list[str] = []
        assistant_text = _call_openrouter(
            system_prompt + proactive_instruction, inbound_text, vehicle_context,
            session=session, lead=lead,
            dealer_id=lead.dealer_id if lead else None,
            dealer_config=dealer_config,
            tools_used=tools_used,
        )

        return {
            "mode": "send",
            "text": assistant_text,
            "is_business_hours": is_biz,
            "tools_used": tools_used,
            "proactive": True,
        }

    # ------------------------------------------------------------------
    # Max-turns guard: count inbound messages for this lead
    # ------------------------------------------------------------------
    if session is not None and lead is not None:
        from sqlalchemy import func, select
        from app.models import Direction, LeadEvent, LeadState, Message

        inbound_count = session.execute(
            select(func.count()).where(
                Message.lead_id == lead.id,
                Message.direction == Direction.INBOUND,
            )
        ).scalar() or 0

        if inbound_count >= MAX_INBOUND_TURNS and lead.state == LeadState.ENGAGED:
            logger.warning(
                "Lead %s hit max inbound turns (%d); handing off to human rep",
                lead.id, inbound_count,
            )
            # Send handoff message with dealer name
            dealer_name = dealer_config.get("dealer", {}).get("name", "our team")
            handoff_text = (
                f"Thanks for chatting with us! I've passed your information to {dealer_name}. "
                f"A sales rep will follow up with you shortly to help with whatever you need."
            )
            # Transition to ASSIGNED for human follow-up
            from app.engine.lifecycle import transition
            transition(
                session, lead, LeadState.ASSIGNED,
                reason="max_turns_reached",
                meta={"inbound_count": inbound_count},
            )

            return {
                "mode": "send",
                "text": handoff_text,
                "is_business_hours": is_business_hours(dealer_config, now),
                "tools_used": [],
                "max_turns_reached": True,
            }

    # ------------------------------------------------------------------
    # Normal conversation flow
    # ------------------------------------------------------------------
    is_biz = is_business_hours(dealer_config, now)

    # Build vehicle context if available
    vehicle_context = None
    if vehicle:
        price_str = f"${vehicle.price:,.0f}" if vehicle.price else "TBD"
        mileage_str = f"{vehicle.mileage:,} km" if vehicle.mileage else "TBD"
        vehicle_context = (
            f"Stock #: {vehicle.stock_no} | "
            f"{vehicle.year} {vehicle.make} {vehicle.model} {vehicle.trim or ''} | "
            f"Price: {price_str} | "
            f"Mileage: {mileage_str}"
        )

    system_prompt = build_system_prompt(dealer_config, vehicle_context)

    tools_used: list[str] = []

    if fake_llm:
        response = fake_llm.respond(
            system=system_prompt,
            message=inbound_text,
            vehicle=vehicle_context,
        )
        assistant_text = response.get("text", "Thank you for your message!")
    else:
        assistant_text = _call_openrouter(
            system_prompt, inbound_text, vehicle_context,
            session=session, lead=lead,
            dealer_id=lead.dealer_id if lead else None,
            dealer_config=dealer_config,
            tools_used=tools_used,
        )

    return {
        'mode': 'draft' if is_biz else 'send',
        "text": assistant_text,
        "is_business_hours": is_biz,
        "tools_used": tools_used,
    }


def _call_openrouter_with_retry(client, **kwargs):
    """Call client.chat.completions.create() with retry + exponential backoff.

    Retries up to _MAX_RETRIES times on 5xx server errors and timeouts.
    Does NOT retry on 4xx errors (bad request, auth, rate limit) — those are permanent.
    Returns the response object on success.
    Raises the original exception after all retries are exhausted.
    """
    last_exc = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return client.chat.completions.create(timeout=_TIMEOUT_SECONDS, **kwargs)
        except Exception as exc:
            # Check if this is a retryable error (5xx or timeout)
            is_retryable = False
            status_code = getattr(exc, "status_code", None)
            if status_code is not None and status_code in _RETRYABLE_STATUS_CODES:
                is_retryable = True
            # Also retry on connection/timeout errors (no status_code)
            if status_code is None and isinstance(exc, (TimeoutError, ConnectionError, OSError)):
                is_retryable = True
            # Check for openai-specific status codes on the response
            if not is_retryable:
                resp = getattr(exc, "response", None)
                if resp is not None:
                    resp_status = getattr(resp, "status_code", None)
                    if resp_status is not None and resp_status in _RETRYABLE_STATUS_CODES:
                        is_retryable = True

            last_exc = exc
            if not is_retryable or attempt >= _MAX_RETRIES:
                break

            backoff = _RETRY_BACKOFF[attempt]
            logger.warning(
                "OpenRouter API error (attempt %d/%d, status=%s): %s — retrying in %ds",
                attempt + 1, _MAX_RETRIES + 1, status_code, exc, backoff,
            )
            time.sleep(backoff)

    raise last_exc


def _call_openrouter(
    system_prompt: str,
    user_message: str,
    vehicle_context: str | None = None,
    *,
    session: Session | None = None,
    lead=None,
    dealer_id: int | None = None,
    dealer_config: dict | None = None,
    tools_used: list | None = None,
) -> str:
    """Call OpenRouter API (OpenAI-compatible) for conversation generation.

    Uses retry with exponential backoff on 5xx server errors and timeouts.
    Falls back to a generic reply if the API call ultimately fails.
    Dispatches tool calls to real deterministic tools.
    """
    from app.config import settings

    if not settings.openrouter_api_key and not settings.deepseek_api_key:
        return "Thank you for your interest! One of our team members will be in touch shortly."

    try:
        # P0-03 APPLIED DURING MIGRATION: module-level lazy singleton — instantiates OpenAI client
        # once per process (not per request) to avoid connection/memory leak under load.
        client = _get_openai_client()

        messages = [{"role": "system", "content": system_prompt}]

        # Load recent conversation history from the Message table for context
        if lead is not None and session is not None:
            from sqlalchemy import select
            from app.models import Message, Direction

            recent_msgs = session.execute(
                select(Message)
                .where(Message.lead_id == lead.id)
                .order_by(Message.created_at.desc())
                .limit(20)
            ).scalars().all()

            # Reverse so oldest-first (chronological order)
            recent_msgs.reverse()

            # If we have more than 10 messages, summarize the older ones
            # to keep context under token limits
            if len(recent_msgs) > 10:
                older = recent_msgs[:-10]
                recent = recent_msgs[-10:]
                # Build a condensed summary of older messages
                summary_lines = []
                for msg in older:
                    prefix = "Customer" if msg.direction == Direction.INBOUND else "AI"
                    body = msg.body[:200]
                    summary_lines.append(f"{prefix}: {body}")
                summary = " [Earlier conversation] " + " | ".join(summary_lines)
                messages.append({"role": "system", "content": summary})
                recent_msgs = recent

            for msg in recent_msgs:
                role = "assistant" if msg.direction == Direction.OUTBOUND else "user"
                messages.append({"role": role, "content": msg.body})

        messages.append({"role": "user", "content": user_message})

        response = _call_openrouter_with_retry(
            client,
            model=_get_model_name(),
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            max_tokens=1024,
            temperature=0.7,
        )

        choice = response.choices[0]
        if choice.message.tool_calls:
            # Model requested tool calls — execute them with real tools
            tool_results = []
            for tc in choice.message.tool_calls:
                result = _execute_tool_call(
                    tc.function.name, tc.function.arguments,
                    session=session, lead=lead, dealer_id=dealer_id,
                    dealer_config=dealer_config,
                )
                if tools_used is not None:
                    tools_used.append(tc.function.name)
                tool_results.append({
                    "tool_call_id": tc.id,
                    "role": "tool",
                    "content": json.dumps(result),
                })

            # Send tool results back for final response
            messages.append(choice.message.model_dump())
            messages.extend(tool_results)

            final_response = _call_openrouter_with_retry(
                client,
                model=_get_model_name(),
                messages=messages,
                max_tokens=1024,
                temperature=0.7,
            )
            return final_response.choices[0].message.content or "Thank you!"

        return choice.message.content or "Thank you for your message!"

    except Exception:
        logger.exception("OpenRouter call failed after retries")
        return "I'm having trouble connecting right now. Please try again in a few minutes."