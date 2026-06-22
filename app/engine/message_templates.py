"""Single message-template module — the ONE place all rep-facing messages are composed.

Six visibly distinct event types, each with its own emoji prefix + call-to-action:
- NEW_LEAD         → fresh inbound lead
- COVER_ME         → reassign/handoff to another rep (@ T4)
- HANDOFF_RECEIVED → rep receives a passed lead (@ T4/T5)
- CLAIM_CONFIRM    → rep successfully claimed the lead (@ T5)
- ESCALATION       → lead escalated past 3 passes
- DAILY_DIGEST     → morning summary of open/pending leads
"""

from __future__ import annotations


# ── Template catalog ──────────────────────────────────────────────────────────

TEMPLATES: dict[str, dict] = {
    "NEW_LEAD": {
        "emoji": "🔔",
        "header": "NEW LEAD",
        "body": (
            "🔔 <b>NEW LEAD</b>\n"
            "<b>{customer_name}</b>\n"
            "{vehicle_line}"
            "📞 {phone}\n"
            "💬 <i>{message_preview}</i>\n\n"
            "Reply in the dashboard or claim below."
        ),
    },
    "COVER_ME": {
        "emoji": "🆘",
        "header": "COVER REQUEST",
        "body": (
            "🆘 <b>COVER REQUEST</b>\n"
            "{rep_name}, {customer_name} has been reassigned to you.\n"
            "{vehicle_line}"
            "📞 {phone}\n"
            "Please take over this lead."
        ),
    },
    "HANDOFF_RECEIVED": {
        "emoji": "📨",
        "header": "HANDED TO YOU",
        "body": (
            "📨 <b>HANDED TO YOU</b>\n"
            "{rep_name}, {customer_name} has been sent your way.\n"
            "{vehicle_line}"
            "📞 {phone}\n"
            "Tap Claim to take it or Pass to send to next rep."
        ),
    },
    "CLAIM_CONFIRM": {
        "emoji": "✅",
        "header": "CLAIMED",
        "body": (
            "✅ <b>CLAIMED</b>\n"
            "{rep_name}, you've been assigned to {customer_name}.\n"
            "{vehicle_line}"
            "📞 {phone}\n"
            "They're yours — follow up in the dashboard."
        ),
    },
    "ESCALATION": {
        "emoji": "🚨",
        "header": "ESCALATION",
        "body": (
            "🚨 <b>ESCALATION</b>\n"
            "{rep_name}, {customer_name} needs attention.\n"
            "{vehicle_line}"
            "📞 {phone}\n"
            "Reason: {reason}\n"
            "All reps have passed. Please review immediately."
        ),
    },
    "DAILY_DIGEST": {
        "emoji": "📊",
        "header": "DAILY DIGEST",
        "body": (
            "📊 <b>DAILY DIGEST</b> — {dealer_name}\n"
            "📋 Open leads: {open_count}\n"
            "📅 Appointments today: {appt_count}\n"
            "⏳ Unclaimed: {unclaimed_count}\n"
            "{extra_line}"
            "Check your dashboard for details."
        ),
    },
}


# ── Builder ───────────────────────────────────────────────────────────────────

def build_message(
    template_key: str,
    **kwargs,
) -> str:
    """Render a message from a template key + keyword substitutions.

    Unknown keys return a plain fallback. Extra kwargs are silently ignored.
    """
    template = TEMPLATES.get(template_key)
    if not template:
        return f"[{template_key}] {kwargs}"

    try:
        return template["body"].format(**kwargs)
    except KeyError as e:
        return template["body"] + f"  (missing: {e})"


def build_inline_keyboard(
    lead_id: int,
    *,
    show_claim: bool = True,
    show_pass: bool = True,
) -> list[list[dict]]:
    """Build an inline keyboard for claim/pass actions.

    Returns a 2-row keyboard:
      [✅ Claim] [➡️ Pass]

    Each button carries callback_data like "claim:<lead_id>" or "pass:<lead_id>".
    """
    buttons = []
    row = []
    if show_claim:
        row.append({
            "text": "✅ Claim",
            "callback_data": f"claim:{lead_id}",
        })
    if show_pass:
        row.append({
            "text": "➡️ Pass",
            "callback_data": f"pass:{lead_id}",
        })
    if row:
        buttons.append(row)
    return buttons


# ── Helpers for template filler ───────────────────────────────────────────────

def fill_vehicle_line(vehicle_ref: str | None = None) -> str:
    """Return a vehicle line for the template, or empty string."""
    if vehicle_ref:
        return f"🚗 {vehicle_ref}\n"
    return ""
