"""Email parsers — extract lead data from site-specific notification email formats.

Supports:
- CarGurus / AutoTrader / Cars.com listing-site emails
- Dealer website form notification emails (generic fallback)
- Plain-text and HTML emails

Each parser returns a NormalizedLead or None if it can't parse the email.
"""

from __future__ import annotations

import re
import logging

from app.adapters.intake import NormalizedLead
from app.adapters.intake import normalize_phone as _norm_phone
from app.models import Channel

logger = logging.getLogger("speed-to-lead.email_parsers")


# ── Parser registry ──────────────────────────────────────────────────────────

_PARSERS: list[callable] = []


def register(parser_fn):
    """Register an email parser function. Functions are tried in registration order."""
    _PARSERS.append(parser_fn)
    return parser_fn


# ── Helpers ──────────────────────────────────────────────────────────────────

def _clean_html(html: str) -> str:
    """Strip HTML tags to get plain text."""
    clean = re.sub(r"<[^>]+>", " ", html)
    clean = re.sub(r"&nbsp;", " ", clean)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def _extract_field(text: str, *labels: str) -> str | None:
    """Extract a field value following one of the given labels (case-insensitive).
    Example: _extract_field(text, 'Name:', 'Full Name:') -> 'John Doe'
    """
    for label in labels:
        pattern = re.escape(label) + r"\s*(.+?)(?:\n|$|\s{2,})"
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _extract_phone_loose(text: str) -> str | None:
    """Extract a phone number using a loose pattern."""
    # Common US/CA phone patterns
    patterns = [
        r"\b(\+?1[-\s.]?)?\(?(\d{3})\)?[-\s.]?(\d{3})[-\s.]?(\d{4})\b",
        r"\b(\d{3})[-\s.](\d{3})[-\s.](\d{4})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            groups = m.groups()
            if len(groups) == 4:
                return f"+1{groups[1]}{groups[2]}{groups[3]}"
            elif len(groups) == 3:
                return f"+1{groups[0]}{groups[1]}{groups[2]}"
    return None


# ── Site-specific parsers ────────────────────────────────────────────────────

@register
def parse_cargurus(text: str, subject: str = "", from_addr: str = "") -> NormalizedLead | None:
    """Parse CarGurus lead notification emails."""
    if "cargurus" not in text.lower() and "cargurus" not in subject.lower():
        return None

    name = _extract_field(text, "Customer Name:", "Name:")
    phone = _extract_field(text, "Phone:")
    phone = _norm_phone(phone) if phone else None
    email_addr = _extract_field(text, "Email:", "Email Address:")
    vehicle_ref = _extract_field(text, "Vehicle:", "Vehicle of Interest:", "Car of Interest:")
    message = _extract_field(text, "Message:", "Comments:", "Question:")

    # If no structured fields match, try loose extraction
    if not name:
        name = _extract_field(text, "Customer:", "From:")
    if not vehicle_ref:
        # Try to extract year/make/model from subject or text
        ym = re.search(r"(?:re:|about:)\s*(\d{4}\s+\w+\s+\w+)", text, re.IGNORECASE)
        if ym:
            vehicle_ref = ym.group(1).strip()

    return NormalizedLead(
        source=Channel.EMAIL,
        name=name,
        phone=phone,
        email=email_addr,
        vehicle_ref=vehicle_ref,
        message=message,
        consent=True,
        raw={"raw": text, "subject": subject, "parser": "cargurus"},
    )


@register
def parse_autotrader(text: str, subject: str = "", from_addr: str = "") -> NormalizedLead | None:
    """Parse AutoTrader.ca lead notification emails."""
    if "autotrader" not in text.lower() and "trader" not in subject.lower():
        return None

    name = _extract_field(text, "Name:", "Full Name:", "Customer Name:")
    phone = _extract_field(text, "Phone:", "Phone Number:", "Tel:")
    phone = _norm_phone(phone) if phone else None
    email_addr = _extract_field(text, "Email:", "Email Address:")
    vehicle_ref = _extract_field(text, "Vehicle:", "Vehicle of Interest:", "Listing:")
    message = _extract_field(text, "Message:", "Comments:", "Question:", "Inquiry:")

    if not vehicle_ref:
        ym = re.search(r"(?:re:|about:)\s*(\d{4}\s+\w+\s+\w+)", text, re.IGNORECASE)
        if ym:
            vehicle_ref = ym.group(1).strip()

    return NormalizedLead(
        source=Channel.EMAIL,
        name=name,
        phone=phone,
        email=email_addr,
        vehicle_ref=vehicle_ref,
        message=message,
        consent=True,
        raw={"raw": text, "subject": subject, "parser": "autotrader"},
    )


@register
def parse_cars_com(text: str, subject: str = "", from_addr: str = "") -> NormalizedLead | None:
    """Parse Cars.com lead notification emails."""
    if "cars.com" not in text.lower() and "cars" not in subject.lower():
        # too generic — only match if cars.com is in the text
        if "cars.com" not in text.lower():
            return None

    name = _extract_field(text, "Name:", "Full Name:", "Customer:")
    phone = _extract_field(text, "Phone:", "Phone Number:")
    phone = _norm_phone(phone) if phone else None
    email_addr = _extract_field(text, "Email:", "Email Address:")
    vehicle_ref = _extract_field(text, "Vehicle:", "Listing:")
    message = _extract_field(text, "Message:", "Comments:", "Question:")

    return NormalizedLead(
        source=Channel.EMAIL,
        name=name,
        phone=phone,
        email=email_addr,
        vehicle_ref=vehicle_ref,
        message=message,
        consent=True,
        raw={"raw": text, "subject": subject, "parser": "cars_com"},
    )


# ── Dealer website form parser (universal fallback) ──────────────────────────

@register
def parse_dealer_website_form(text: str, subject: str = "", from_addr: str = "") -> NormalizedLead | None:
    """Parse a dealer's own website-form notification email.

    Most dealer website forms send an email to the dealer's inbox with lead details.
    These typically have labels like 'Name', 'Email', 'Phone', 'Message' in the body.
    This parser handles the generic case — specific dealers should extend it.
    """
    name = _extract_field(text, "Name:", "Full Name:", "First Name:")
    phone = _extract_field(text, "Phone:", "Phone Number:", "Mobile:", "Cell:")
    phone = _norm_phone(phone) if phone else None
    email_addr = _extract_field(text, "Email:", "Email Address:", "E-mail:")
    vehicle_ref = _extract_field(
        text,
        "Vehicle of Interest:", "Vehicle:", "Car of Interest:",
        "Model of Interest:", "Model:", "Stock #:",
    )
    message = _extract_field(text, "Message:", "Comments:", "Question:", "Notes:")

    # If we still have nothing, try a loose phone extract
    if not phone:
        phone = _extract_phone_loose(text)
        if phone:
            phone = _norm_phone(phone)

    # Require at least SOME lead data to consider this parsed
    if not name and not email_addr and not phone:
        return None

    return NormalizedLead(
        source=Channel.EMAIL,
        name=name,
        phone=phone,
        email=email_addr,
        vehicle_ref=vehicle_ref,
        message=message,
        consent=True,
        raw={"raw": text, "subject": subject, "parser": "dealer_website_form"},
    )


# ── Generic fallback ─────────────────────────────────────────────────────────

@register
def parse_generic(text: str, subject: str = "", from_addr: str = "") -> NormalizedLead | None:
    """Generic fallback parser — try to extract ANY useful lead data."""
    # Try everything
    name = _extract_field(text, "Name:", "Full Name:", "First:", "Customer:", "From:")
    phone = _extract_phone_loose(text)
    phone = _norm_phone(phone) if phone else None
    email_addr = re.search(r"(\S+@\S+\.\S+)", text)
    email_addr = email_addr.group(1).strip().lower() if email_addr else None
    vehicle_ref = _extract_field(
        text, "Vehicle:", "Car:", "Model:", "Interest:", "Looking for:",
        "Vehicle of Interest:", "Stock #:",
    )
    message = _extract_field(text, "Message:", "Comments:", "Question:", "Inquiry:")

    if not name and not email_addr and not phone:
        return None

    return NormalizedLead(
        source=Channel.EMAIL,
        name=name,
        phone=phone,
        email=email_addr,
        vehicle_ref=vehicle_ref,
        message=message,
        consent=True,
        raw={"raw": text, "subject": subject, "parser": "generic"},
    )


# ── Public entry point ───────────────────────────────────────────────────────

def parse_email(body: str, *, subject: str = "", from_addr: str = "") -> NormalizedLead | None:
    """Parse an email body into a NormalizedLead using registered parsers.

    Parsers are tried in registration order. The first parser that returns a
    non-None result wins. Text is cleaned of HTML before parsing.

    Returns None if no parser can extract lead data.
    """
    if not body:
        return None

    # Clean HTML if present
    if "<html" in body.lower() or "<br" in body.lower():
        text = _clean_html(body)
    else:
        text = body

    for parser in _PARSERS:
        try:
            result = parser(text, subject=subject, from_addr=from_addr)
            if result is not None:
                logger.info("Email parsed by %s: name=%s phone=%s", parser.__name__, result.name, result.phone)
                return result
        except Exception:
            logger.exception("Parser %s failed on email", parser.__name__)

    logger.info("No parser matched email: subject=%s", subject[:80])
    return None
