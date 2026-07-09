"""Free-text Telegram message router — classifies rep messages into intents.

Three intents:
1. availability → set/update unavailability windows
2. new_lead → create a lead via ingest_lead
3. no_show_reply → reply to a nudge (mark showed/no-show)
4. unknown → help message

Uses the same OpenAI client as the conversation engine for classification.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.orm import Session

logger = logging.getLogger("speed-to-lead.telegram_free_text")

Intent = Literal["availability", "new_lead", "no_show_reply", "unknown"]


def classify_message(text: str) -> dict:
    """Use the OpenAI client to classify a free-text message.

    Returns a dict with:
      - intent: Intent string
      - params: dict of extracted parameters
      - raw: the raw LLM response text (for debugging)
    """
    from app.engine.conversation import _get_openai_client, _get_model_name

    client = _get_openai_client()
    model = _get_model_name()

    prompt = f"""Classify the following message from a car dealership sales rep. Return ONLY a JSON object with:
- "intent": one of "availability", "new_lead", "no_show_reply", "unknown"
- "params": extracted details based on intent

For intent "availability":
  - "date": the date mentioned (e.g. "Friday" → compute relative to today 2026-07-09, or explicit date)
  - "start": start time in HH:MM format
  - "end": end time in HH:MM format
  - "note": reason if mentioned (e.g. "dentist", "sick"), empty string otherwise
  If date is a weekday name, convert to YYYY-MM-DD. If ambiguous, use "unknown".

For intent "new_lead":
  - "name": customer name
  - "phone": phone number
  - "vehicle_ref": vehicle interested in (e.g. "Civic", "F-150"), empty string if none

For intent "no_show_reply":
  - "status": "showed" or "no_show"

For intent "unknown": params is empty object.

Message: {text}

JSON:"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=300,
        )
        raw = response.choices[0].message.content or ""
    except Exception:
        logger.exception("LLM classification failed")
        raw = '{"intent": "unknown", "params": {}}'

    try:
        # Strip markdown fences if present
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
        result = json.loads(cleaned)
        intent = result.get("intent", "unknown")
        params = result.get("params", {})
    except (json.JSONDecodeError, KeyError):
        intent = "unknown"
        params = {}

    return {"intent": intent, "params": params, "raw": raw}


_CONFIRMATION_CACHE: dict[str, dict] = {}


def handle_free_text(
    session: Session,
    text: str,
    chat_id: str,
    dealer_config: dict,
    rep_config: dict,
) -> dict:
    """Route a free-text message from a known rep to the correct handler.

    Returns a dict with:
      - action: description of what was done
      - reply: text to send back to the rep (or None if no reply needed)
      - success: bool
    """
    rep_name = rep_config.get("name", "Unknown")

    # Check if this is a confirmation reply to a pending availability change
    pending = _CONFIRMATION_CACHE.pop(chat_id, None)
    if pending and pending.get("type") == "availability" and _is_confirmation(text):
        # Commit the pending availability window
        try:
            from app.config import UnavailableWindow as _UnavailableWindow
            from sqlalchemy.orm.attributes import flag_modified
            import json as _json

            config = dealer_config
            sales_team = config.get("sales_team", [])
            rep_cfg = next(
                (r for r in sales_team if r.get("name", "").lower() == rep_name.lower()),
                None,
            )
            if rep_cfg:
                if "unavailable_windows" not in rep_cfg:
                    rep_cfg["unavailable_windows"] = []
                rep_cfg["unavailable_windows"].append(pending["window"])
                # Persist via dealer object
                from app.models import Dealer
                from sqlalchemy import select
                dealer_obj = session.execute(
                    select(Dealer).where(Dealer.slug == dealer_config.get("dealer", {}).get("slug", ""))
                ).scalars().first()
                if dealer_obj:
                    dealer_obj.config = _json.loads(_json.dumps(config))
                    flag_modified(dealer_obj, "config")
                    session.commit()

            return {
                "action": "availability_confirmed",
                "reply": f"✅ Got it, {rep_name}. Marked you unavailable {pending['window']['date']} {pending['window']['start']}-{pending['window']['end']}.",
                "success": True,
            }
        except Exception:
            logger.exception("Failed to commit availability window")
            return {
                "action": "availability_commit_failed",
                "reply": "Sorry, something went wrong saving that. Try again or use the dashboard.",
                "success": False,
            }

    # If there's a pending confirmation but user didn't confirm, cancel
    if pending:
        return {
            "action": "availability_cancelled",
            "reply": "OK, cancelled. Send me the details again if you want to set unavailability.",
            "success": True,
        }

    # Classify the message
    classification = classify_message(text)
    intent = classification["intent"]
    params = classification["params"]

    if intent == "availability":
        return _handle_availability(session, params, chat_id, dealer_config, rep_config)

    elif intent == "new_lead":
        return _handle_new_lead(session, params, chat_id, dealer_config, rep_config)

    elif intent == "no_show_reply":
        return _handle_no_show_reply(session, params, chat_id, dealer_config, rep_config)

    else:
        return {
            "action": "unknown",
            "reply": (
                "I didn't understand that. You can:\n"
                "• Set unavailability: 'not free 2-4pm Friday'\n"
                "• Add a lead: 'new lead, John, wants a Civic'\n"
                "• Confirm show/no-show: reply to a nudge"
            ),
            "success": True,
        }


def _is_confirmation(text: str) -> bool:
    """Check if text is a confirmation (yes/confirm/ok/y)."""
    lowered = text.strip().lower()
    return lowered in ("yes", "y", "confirm", "ok", "okay", "yeah", "correct", "that's right", "do it")


def _handle_availability(
    session: Session,
    params: dict,
    chat_id: str,
    dealer_config: dict,
    rep_config: dict,
) -> dict:
    """Handle an availability update: store pending, ask for confirmation."""
    from app.config import UnavailableWindow as _UnavailableWindow

    date = params.get("date", "unknown")
    start = params.get("start", "")
    end = params.get("end", "")

    if not start or not end or date == "unknown":
        return {
            "action": "availability_parse_failed",
            "reply": "I couldn't parse your availability. Try: 'not free 2-4pm Friday' or 'out sick tomorrow'.",
            "success": False,
        }

    try:
        window = _UnavailableWindow(date=date, start=start, end=end, note=params.get("note", ""))
    except Exception as e:
        return {
            "action": "availability_invalid",
            "reply": f"Invalid time window: {e}",
            "success": False,
        }

    # Store pending confirmation
    rep_name = rep_config.get("name", "Unknown")
    _CONFIRMATION_CACHE[chat_id] = {
        "type": "availability",
        "window": window.model_dump(),
        "rep_name": rep_name,
    }

    return {
        "action": "availability_pending",
        "reply": f"Got it — marking you unavailable {date} {start}-{end}. Confirm? (reply 'yes' or 'confirm')",
        "success": True,
    }


def _handle_new_lead(
    session: Session,
    params: dict,
    chat_id: str,
    dealer_config: dict,
    rep_config: dict,
) -> dict:
    """Handle a new lead message: extract details, call ingest_lead."""
    name = params.get("name", "").strip()
    phone = params.get("phone", "").strip()
    vehicle = params.get("vehicle_ref", "").strip() or ""

    if not name or not phone:
        return {
            "action": "new_lead_parse_failed",
            "reply": "I need at least a name and phone number. Try: 'new lead, John, 604-555-1234, wants a Civic'.",
            "success": False,
        }

    from app.adapters.intake import NormalizedLead
    from app.models import Channel
    from tools.route_lead import ingest_lead

    # Look up the dealer object
    from app.models import Dealer
    from sqlalchemy import select
    dealer_obj = session.execute(
        select(Dealer).where(Dealer.slug == dealer_config.get("dealer", {}).get("slug", ""))
    ).scalars().first()

    if not dealer_obj:
        return {
            "action": "new_lead_dealer_not_found",
            "reply": "Dealer not found — contact support.",
            "success": False,
        }

    lead_data = NormalizedLead(
        source=Channel.WEBFORM,
        name=name,
        phone=phone,
        vehicle_ref=vehicle or None,
        consent=True,
    )

    try:
        lead = ingest_lead(session, dealer_obj, lead_data)

        # Assign to the rep who submitted it
        rep_name = rep_config.get("name", "")
        if rep_name:
            lead.assigned_rep = rep_name
            session.commit()

        vehicle_line = f" — {vehicle}" if vehicle else ""
        return {
            "action": "new_lead_created",
            "reply": f"✅ Added {name}{vehicle_line} — {phone}",
            "success": True,
        }
    except Exception as e:
        logger.exception("Failed to create lead from Telegram")
        return {
            "action": "new_lead_failed",
            "reply": f"Failed to create lead: {e}",
            "success": False,
        }


def _handle_no_show_reply(
    session: Session,
    params: dict,
    chat_id: str,
    dealer_config: dict,
    rep_config: dict,
) -> dict:
    """Handle a no-show reply: mark showed or no-show on an active nudge appointment."""
    from app.models import Appointment, Lead, LeadEvent
    from sqlalchemy import select
    from datetime import timedelta

    status = params.get("status", "")

    if status not in ("showed", "no_show"):
        return {
            "action": "no_show_parse_failed",
            "reply": "Please say 'he showed' or 'no show' clearly.",
            "success": False,
        }

    rep_name = rep_config.get("name", "")

    # Find the most recent non-final appointment for this rep that has a nudge marker
    now = datetime.now(timezone.utc)
    two_hours_ago = now - timedelta(hours=2)

    # Look for appointments with status='set' that are > 2h past, assigned to this rep,
    # and have a nudge_sent LeadEvent
    appts = session.execute(
        select(Appointment)
        .join(Lead, Appointment.lead_id == Lead.id)
        .where(
            Lead.assigned_rep == rep_name,
            Appointment.status == "set",
            Appointment.scheduled_for < two_hours_ago,
        )
        .order_by(Appointment.scheduled_for.desc())
        .limit(5)
    ).scalars().all()

    # Filter to those that have had a nudge sent
    nudged_appts = []
    for appt in appts:
        nudge_event = session.execute(
            select(LeadEvent).where(
                LeadEvent.lead_id == appt.lead_id,
                LeadEvent.type == "no_show_nudge",
            ).order_by(LeadEvent.created_at.desc())
        ).scalars().first()
        if nudge_event:
            nudged_appts.append(appt)

    if not nudged_appts:
        return {
            "action": "no_show_no_nudge",
            "reply": "I don't see any appointments needing confirmation right now.",
            "success": True,
        }

    # Mark the most recently nudged one
    appt = nudged_appts[0]
    lead = session.get(Lead, appt.lead_id)

    from tools.book_appointment import mark_showed, mark_no_show

    try:
        if status == "showed":
            mark_showed(session, appt, lead)
            msg = f"✅ {lead.name or 'Customer'} marked as showed."
        else:
            mark_no_show(session, appt)
            msg = f"✅ {lead.name or 'Customer'} marked as no-show."

        return {
            "action": f"no_show_{status}",
            "reply": msg,
            "success": True,
        }
    except Exception as e:
        logger.exception("Failed to mark no-show reply")
        return {
            "action": "no_show_failed",
            "reply": f"Failed to update: {e}",
            "success": False,
        }
