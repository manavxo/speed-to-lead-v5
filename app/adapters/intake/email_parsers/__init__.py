"""Site-specific email parsers registry.

Each parser takes raw email text and returns a NormalizedLead or None.
The registry tries parsers in order and falls back to the generic parser.
"""

from __future__ import annotations

from app.adapters.intake import NormalizedLead


def parse_email(raw: str, subject: str = "", from_addr: str = "") -> NormalizedLead | None:
    """Try each site-specific parser, fall back to generic.

    Args:
        raw: Raw email body text.
        subject: Email subject line.
        from_addr: Sender email address.

    Returns:
        NormalizedLead if any parser succeeded, else None.
    """
    from app.adapters.intake.email_parsers.autotrader_ca import parse_autotrader
    from app.adapters.intake.email_parsers.cargurus import parse_cargurus
    from app.adapters.intake.email_parsers.generic import parse_generic

    # Try AutoTrader first (most common)
    result = parse_autotrader(raw, subject, from_addr)
    if result:
        return result

    # Try CarGurus
    result = parse_cargurus(raw, subject, from_addr)
    if result:
        return result

    # Fall back to generic/LLM
    result = parse_generic(raw, subject, from_addr)
    if result:
        return result

    return None
