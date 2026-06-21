"""Generic email lead parser — fallback for unknown templates.

Uses the original EmailLeadAdapter regex approach plus LLM fallback
when regex can't extract meaningful data.
"""

from __future__ import annotations

import re

from app.adapters.intake import NormalizedLead
from app.adapters.intake.email_lead import EmailLeadAdapter
from app.models import Channel


def parse_generic(raw: str, subject: str = "", from_addr: str = "") -> NormalizedLead | None:
    """Parse an unknown-format email using the existing EmailLeadAdapter.

    Args:
        raw: Raw email body text.
        subject: Email subject.
        from_addr: Sender email address.

    Returns:
        NormalizedLead if parsing succeeded, else None.
    """
    if not raw:
        return None

    # Use the existing adapter
    adapter = EmailLeadAdapter()
    payload = {"raw": raw, "subject": subject, "from": from_addr}
    result = adapter.parse(payload)

    # If the generic adapter couldn't extract anything, try a minimal regex
    if not result.phone and not result.email and not result.name:
        # Extract anything that looks like a name at the start of the email
        lines = raw.strip().split("\n")
        first_line = lines[0].strip() if lines else ""
        # If the first line looks like a person's name (2-3 words, not all caps)
        if first_line and len(first_line.split()) in (2, 3) and not first_line.isupper():
            result.name = first_line
        # Try to find any email address in the body
        email_match = re.search(r"(\S+@\S+\.\S+)", raw)
        if email_match and not result.email:
            result.email = email_match.group(1).strip()

    return result if (result.phone or result.email) else None
