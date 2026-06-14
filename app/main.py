"""FastAPI app — the always-on service. Hosts the webhook routes (one per intake channel),
the dashboard, and the background scheduler (via lifespan).

Run (dev):  uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from xml.sax.saxutils import escape as xml_escape
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session_factory, init_db
from app.models import ConsentLog, Dealer, Lead, LeadState, Message, Direction, Channel
from app.adapters.intake import mask_phone
from app.admin import router as admin_router
from app.dashboard import router as dashboard_router
from app.scheduler import register_jobs

logger = logging.getLogger("speed-to-lead")


_scheduler: BackgroundScheduler | None = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup: init DB + start background scheduler.  Shutdown: stop scheduler."""
    global _scheduler
    init_db()

    # Auto-provision any dealer YAML files that aren't in the DB yet
    _auto_provision_dealers()

    _scheduler = BackgroundScheduler(timezone="UTC")
    register_jobs(_scheduler)
    _scheduler.start()
    logger.info("Scheduler started with %d jobs", len(_scheduler.get_jobs()))

    yield

    logger.info("Shutting down scheduler …")
    _scheduler.shutdown(wait=False)


app = FastAPI(title="Speed-to-Lead", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(admin_router)
app.include_router(dashboard_router)


# ---- Landing page (static HTML + assets) ----------------------------------------------

from pathlib import Path as _Path

_LANDING_DIR = _Path(__file__).resolve().parent.parent / "landing"


@app.get("/", include_in_schema=False)
async def landing_page():
    """Serve the marketing landing page at the root URL."""
    return FileResponse(_LANDING_DIR / "index.html", media_type="text/html")


@app.get("/landing/assets/{filename:path}", include_in_schema=False)
async def landing_assets(filename: str):
    """Serve landing page static assets (Lottie JSON files, etc.)."""
    fpath = (_LANDING_DIR / "assets" / filename).resolve()
    if not fpath.is_file() or not str(fpath).startswith(str(_LANDING_DIR.resolve())):
        return Response(status_code=404)
    return FileResponse(fpath)


# ---- Helpers ---------------------------------------------------------------------------

def _exec(session: Session, stmt):
    return session.execute(stmt).scalars()


def _process_and_send_sync(
    session: Session,
    lead_id: int,
    dealer_id: int,
    dealer_slug: str,
    body: str,
    raw_from: str,
    sms_from_number: str,
) -> None:
    """Sync helper for the SMS webhook background task.

    Runs the AI turn, appends the CASL footer, sends the reply via send_sms,
    and logs the result. Takes a session so it can be tested directly (the
    async wrapper _process_and_send handles session lifecycle).

    Returns silently on missing lead/dealer; logs errors.
    """
    bg_lead = session.get(Lead, lead_id)
    if not bg_lead:
        logger.error("Background task: lead#%s not found", lead_id)
        return

    bg_dealer = session.get(Dealer, dealer_id)
    bg_dealer_config = bg_dealer.config if bg_dealer else {}

    # Get vehicle context
    vehicle = None
    if bg_lead.vehicle_id:
        from app.models import Vehicle
        vehicle = session.get(Vehicle, bg_lead.vehicle_id)

    result = handle_turn(
        session, bg_lead, body,
        dealer_config=bg_dealer_config,
        vehicle=vehicle,
    )

    reply_text = result.get("text", "Thanks for your message!")

    # Append CASL compliance footer
    bg_dealer_name = bg_dealer_config.get("dealer", {}).get("name", "")
    footer = bg_dealer_config.get("compliance", {}).get(
        "consent_text", "Reply STOP to opt out."
    )
    if bg_dealer_name and bg_dealer_name not in reply_text:
        reply_text = f"{reply_text}\n\n— {bg_dealer_name}. {footer}"
    elif footer not in reply_text:
        reply_text = f"{reply_text}\n\n{footer}"

    # Send via send_sms chokepoint (enforces compliance, logs message)
    from tools.send_sms import send_sms
    send_sms(
        session,
        to=raw_from,
        body=reply_text,
        from_number=sms_from_number,
        dealer_slug=dealer_slug,
        dealer_config=bg_dealer_config,
        lead=bg_lead,
        force_send=True,
    )
    logger.info("Background reply sent for lead#%s", lead_id)


def _get_session() -> Session:
    """Get a new DB session."""
    factory = get_session_factory()
    return factory()


def _auto_provision_dealers() -> None:
    """On startup, scan dealers/ for YAML files and upsert any that aren't in the DB."""
    from pathlib import Path
    import json as _json

    dealers_dir = Path(__file__).resolve().parent.parent / "dealers"
    if not dealers_dir.is_dir():
        return

    session = _get_session()
    try:
        for yaml_path in sorted(dealers_dir.glob("*.yaml")):
            if yaml_path.name.startswith("_"):
                continue
            try:
                from app.config import load_dealer_config
                cfg = load_dealer_config(str(yaml_path))

                existing = session.execute(
                    select(Dealer).where(Dealer.slug == cfg.dealer.slug)
                ).scalars().first()

                sms_number = (cfg.channels.sms_number or "").replace(" ", "").replace("-", "")
                whatsapp_sender = (cfg.channels.whatsapp_sender or "").replace(" ", "").replace("-", "")
                web_form_token = cfg.channels.web_form_token or None

                if existing:
                    existing.name = cfg.dealer.name
                    existing.timezone = cfg.dealer.timezone
                    existing.sms_number = sms_number or existing.sms_number
                    existing.whatsapp_sender = whatsapp_sender or existing.whatsapp_sender
                    existing.web_form_token = web_form_token or existing.web_form_token
                    existing.config = _json.loads(cfg.model_dump_json())
                    logger.info("Auto-provision: updated dealer %s", cfg.dealer.slug)
                else:
                    dealer = Dealer(
                        slug=cfg.dealer.slug,
                        name=cfg.dealer.name,
                        timezone=cfg.dealer.timezone,
                        sms_number=sms_number or None,
                        whatsapp_sender=whatsapp_sender or None,
                        web_form_token=web_form_token,
                        config=_json.loads(cfg.model_dump_json()),
                    )
                    session.add(dealer)
                    logger.info("Auto-provision: created dealer %s", cfg.dealer.slug)
            except Exception:
                logger.exception("Auto-provision failed for %s", yaml_path.name)
        session.commit()
    finally:
        session.close()


def _find_dealer_by_token(session: Session, token: str) -> Dealer | None:
    """Find a dealer by their web_form_token.

    Uses the indexed column for fast lookup, with a JSON config fallback for legacy
    dealer rows that pre-date the indexed columns (e.g. test fixtures).
    """
    dealer = _exec(session,
        select(Dealer).where(Dealer.web_form_token == token)
    ).first()
    if dealer:
        return dealer
    # Legacy fallback: scan JSON config
    dealers = _exec(session, select(Dealer)).all()
    for d in dealers:
        config = d.config or {}
        channels = config.get("channels", {})
        if channels.get("web_form_token") == token:
            return d
    return None


def _find_dealer_by_sms(session: Session, number: str) -> Dealer | None:
    """Find a dealer by their SMS number.

    Uses the indexed column for fast lookup, with a JSON config fallback.
    """
    if not number:
        return None
    norm = number.replace(" ", "").replace("-", "")
    dealer = _exec(session,
        select(Dealer).where(Dealer.sms_number == norm)
    ).first()
    if dealer:
        return dealer
    # Legacy fallback: scan JSON config
    dealers = _exec(session, select(Dealer)).all()
    for d in dealers:
        config = d.config or {}
        channels = config.get("channels", {})
        sms = (channels.get("sms_number") or "").replace(" ", "").replace("-", "")
        if sms == norm:
            return d
    return None


def _find_dealer_by_whatsapp(session: Session, number: str) -> Dealer | None:
    """Find a dealer by their WhatsApp sender number.

    Uses the indexed column for fast lookup, with a JSON config fallback.
    """
    if not number:
        return None
    norm = number.replace(" ", "").replace("-", "")
    dealer = _exec(session,
        select(Dealer).where(Dealer.whatsapp_sender == norm)
    ).first()
    if dealer:
        return dealer
    # Legacy fallback: scan JSON config
    dealers = _exec(session, select(Dealer)).all()
    for d in dealers:
        config = d.config or {}
        channels = config.get("channels", {})
        wa = (channels.get("whatsapp_sender") or "").replace(" ", "").replace("-", "")
        if wa == norm:
            return d
    return None


def _twiml(body: str) -> PlainTextResponse:
    """Return a TwiML response with a message."""
    # P0-10 APPLIED DURING MIGRATION (audit only): `xml_escape` (xml.sax.saxutils.escape) was
    # already wrapping `body` here in v4 — equivalent to the spec's `html.escape` for XML element
    # content. TwiML injection via `<script>` in a customer body now breaks safely.
    twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{xml_escape(body)}</Message></Response>'
    return PlainTextResponse(twiml, media_type="application/xml")


def _empty_twiml() -> PlainTextResponse:
    """Return an empty TwiML response (no message sent)."""
    return PlainTextResponse(
        '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )


def _twilio_validator_url(request: Request) -> str:
    """Build the URL Twilio used to sign the request.

    Twilio signs with the external https URL (the one the dealer set as the
    webhook URL). Behind a TLS terminator (Render, Fly, etc.), the request.url
    is the internal http URL. Use public_base_url when it's https, otherwise
    the request URL as-is (dev / test).
    """
    url = str(request.url)
    if settings.public_base_url and settings.public_base_url.startswith("https"):
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        ext = urlparse(settings.public_base_url)
        return urlunparse((
            ext.scheme,
            ext.netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            "",
        ))
    return url


def _validate_twilio_signature(request: Request, form_data: dict | None = None) -> bool:
    """Validate the X-Twilio-Signature header against the request body.

    P0-01: This is the only line of defense against an attacker who knows
    a webhook URL. Fails closed in every failure mode:

    - No auth token configured         => False (never accept unsigned)
    - No signature header              => False
    - Twilio library missing           => False
    - HMAC doesn't match               => False
    - Any exception                    => False

    The signature binds (url, sorted-form-params) to the request, so a
    tampered body fails validation. Tests inject a FakeValidator via
    `monkeypatch.setattr(twilio.request_validator, "RequestValidator", ...)`
    so they can exercise this without HTTPS or a real auth token.

    When REQUIRE_TWILIO_SIGNATURE=false (the default), validation is skipped
    entirely — safe for dev/sandbox testing where signing is impractical.
    """
    if not settings.require_twilio_signature:
        return True

    token = settings.twilio_auth_token
    if not token:
        # Fail closed: cannot validate without a token.
        return False

    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        return False

    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(token)
    except ImportError:
        logger.exception("twilio library not installed — failing closed")
        return False

    url = _twilio_validator_url(request)
    return validator.validate(url, form_data or {}, signature)


def _idempotency_check(session: Session, provider_sid: str | None) -> bool:
    """Return True if a Message with this provider_sid already exists (duplicate webhook)."""
    if not provider_sid:
        return False
    existing = _exec(session,
        select(Message).where(Message.provider_sid == provider_sid)
    ).first()
    return existing is not None


# ---- Health / readiness ---------------------------------------------------------------

@app.get("/healthz")
def healthz() -> dict:
    """Liveness probe — always returns 200 if the process is up."""
    return {"ok": True}


@app.get("/readyz")
def readyz():
    """Readiness probe — checks DB connectivity (SELECT 1). Returns 503 on failure."""
    # P0-09 APPLIED DURING MIGRATION: actually try the DB and return 503 (not 200) on failure,
    # so Render / orchestrators can pull a degraded instance out of the load balancer pool.
    from fastapi.responses import JSONResponse
    session = _get_session()
    try:
        session.execute(select(1))
        return {"ok": True, "db": "connected"}
    except Exception as exc:
        logger.exception("readyz failed")
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": str(exc)},
        )
    finally:
        session.close()


# ---- AXIS 3 intake webhooks -----------------------------------------------------------

@app.post("/webhook/form/{token}")
async def webhook_form(token: str, request: Request) -> dict:
    """Dealer website form. Tenant resolved by `token` (channels.web_form_token).

    Expects JSON body with at least: full_name, phone/email, consent_sms.
    """
    session = _get_session()
    try:
        payload = await request.json()

        dealer = _find_dealer_by_token(session, token)
        if dealer is None:
            return {"error": "Unknown dealer token", "token": token}

        from app.adapters.intake.webform import WebFormAdapter
        lead_data = WebFormAdapter().parse(payload)

        from tools.route_lead import ingest_lead
        lead = ingest_lead(session, dealer, lead_data)

        return {
            "status": "ok",
            "lead_id": lead.id,
            "state": lead.state.value,
            "dealer": dealer.slug,
        }
    except Exception as exc:
        logger.exception("webhook_form error")
        return {"error": "Internal server error"}
    finally:
        session.close()


@app.post("/webhook/twilio/sms")
async def webhook_twilio_sms(request: Request) -> Response:
    """Inbound SMS: customer conversations + rep claim/pass (1/2 replies).

    Tenant resolved by the 'To' number (channels.sms_number).
    If the sender is a sales rep replying '1' or '2', routes to claim/pass handler.
    Otherwise routes to customer conversation engine.
    Returns TwiML response.
    """
    # P0-01: parse the form FIRST, then validate. The HMAC binds to the
    # parsed form params, so we need them before we can check the signature.
    form = await request.form()
    payload = dict(form)

    if not _validate_twilio_signature(request, payload):
        return PlainTextResponse("Forbidden", status_code=403)

    session = _get_session()
    try:
        from_number = mask_phone(payload.get("From", ""))
        to_number = payload.get("To", "")
        body = (payload.get("Body", "") or "").strip()
        message_sid = payload.get("MessageSid", "")

        # Idempotency: short-circuit on duplicate webhook
        if _idempotency_check(session, message_sid):
            logger.info("Duplicate SMS webhook sid=%s — skipping", message_sid)
            return _empty_twiml()

        dealer = _find_dealer_by_sms(session, to_number)
        if dealer is None:
            logger.warning("No dealer found for SMS to=%s", to_number)
            return _empty_twiml()

        dealer_config = dealer.config or {}
        sales_team = dealer_config.get("sales_team", [])

        # Check if sender is a sales rep replying to a claim ping
        raw_from = payload.get("From", "").replace(" ", "").replace("-", "")
        rep = None
        for r in sales_team:
            rep_phone = (r.get("phone", "") or "").replace(" ", "").replace("-", "")
            if rep_phone == raw_from:
                rep = r
                break

        if rep and body.strip() in ("1", "2"):
            # Rep claim/pass via SMS — handle it here
            # Find the most recent ASSIGNED or ESCALATED lead for this rep
            assigned_lead = _exec(session,
                select(Lead).where(
                    Lead.dealer_id == dealer.id,
                    Lead.state == LeadState.ASSIGNED,
                    Lead.assigned_rep == rep["name"],
                ).order_by(Lead.created_at.desc())
            ).first()

            if assigned_lead is None:
                assigned_lead = _exec(session,
                    select(Lead).where(
                        Lead.dealer_id == dealer.id,
                        Lead.state == LeadState.ESCALATED,
                    ).order_by(Lead.created_at.desc())
                ).first()

            if assigned_lead is None:
                return _twiml("No pending leads to claim.")

            # Log the inbound SMS from rep
            rep_msg = Message(
                lead_id=assigned_lead.id,
                direction=Direction.INBOUND,
                channel=Channel.SMS,
                body=body,
                provider_sid=message_sid,
            )
            session.add(rep_msg)
            session.commit()

            sms_number = dealer_config.get("channels", {}).get("sms_number")

            if body.strip() == "1":
                # Claim
                from app.engine.router import handle_claim
                handle_claim(session, assigned_lead, rep["name"])
                return _twiml(f"Lead claimed! {assigned_lead.name or 'Customer'} is yours.")
            elif body.strip() == "2":
                # Pass
                from app.engine.router import handle_pass
                handle_pass(
                    session, assigned_lead, dealer, sales_team, rep["name"],
                    sms_number=sms_number,
                )
                return _twiml("Lead passed to next rep.")

        opt_out_keywords = dealer_config.get("compliance", {}).get(
            "opt_out_keywords", ["STOP", "STOPALL", "UNSUBSCRIBE", "ARRET"]
        )

        # Resubscribe keywords (START / STARTALL / JOIN / UNSTOP)
        resubscribe_keywords = ["START", "STARTALL", "JOIN", "UNSTOP"]
        if body.upper().strip() in resubscribe_keywords:
            # Check if this phone is currently opted out
            opt_out_entry = _exec(session,
                select(ConsentLog).where(
                    ConsentLog.phone == from_number,
                    ConsentLog.action == "opted_out",
                ).order_by(ConsentLog.created_at.desc())
            ).first()

            # Also check for existing re_granted after the opt-out
            already_regranted = False
            if opt_out_entry:
                regrant = _exec(session,
                    select(ConsentLog).where(
                        ConsentLog.phone == from_number,
                        ConsentLog.action == "re_granted",
                        ConsentLog.created_at > opt_out_entry.created_at,
                    )
                ).first()
                already_regranted = regrant is not None

            if opt_out_entry and not already_regranted:
                # Log resubscribe consent
                consent = ConsentLog(
                    dealer_id=dealer.id,
                    phone=from_number,
                    action="re_granted",
                    text=body,
                )
                session.add(consent)
                session.commit()

                # If the lead is OPTED_OUT, move it back to NEW so it can be re-engaged
                lead = _exec(session,
                    select(Lead).where(
                        Lead.dealer_id == dealer.id,
                        Lead.phone == from_number,
                        Lead.state == LeadState.OPTED_OUT,
                    ).order_by(Lead.created_at.desc())
                ).first()

                if lead:
                    from app.engine.lifecycle import transition
                    try:
                        transition(session, lead, LeadState.NEW,
                                   reason=f"resubscribe:{body}")
                    except ValueError:
                        pass  # Already in a compatible state

                return _twiml("Welcome back! You've been resubscribed. Reply STOP to opt out again.")
            else:
                # Not opted out — just acknowledge
                return _twiml("You're already subscribed. Reply STOP to opt out.")

        # Check for opt-out keyword
        if body.upper().strip() in [kw.upper() for kw in opt_out_keywords]:
            opt = ConsentLog(
                dealer_id=dealer.id,
                phone=from_number,
                action="opted_out",
                text=body,
            )
            session.add(opt)
            session.commit()

            # Find and mark lead as OPTED_OUT
            lead = _exec(session,
                select(Lead).where(
                    Lead.dealer_id == dealer.id,
                    Lead.phone == from_number,
                ).order_by(Lead.created_at.desc())
            ).first()

            if lead and lead.state not in (LeadState.SOLD, LeadState.LOST, LeadState.OPTED_OUT):
                from app.engine.lifecycle import transition
                try:
                    transition(session, lead, LeadState.OPTED_OUT, reason=f"opt_out:{body}")
                except ValueError:
                    pass  # Already in terminal state

            return _twiml("You have been unsubscribed. Reply START to resubscribe.")

        # Normal SMS — check for existing conversation or start new lead
        existing_lead = _exec(session,
            select(Lead).where(
                Lead.dealer_id == dealer.id,
                Lead.phone == from_number,
                Lead.state.notin_([LeadState.SOLD, LeadState.LOST, LeadState.OPTED_OUT]),
            ).order_by(Lead.created_at.desc())
        ).first()

        if existing_lead:
            # Existing conversation — route to conversation engine
            from app.engine.conversation import handle_turn

            # Log inbound message (idempotent on provider_sid)
            inbound_msg = Message(
                lead_id=existing_lead.id,
                direction=Direction.INBOUND,
                channel=Channel.SMS,
                body=body,
                provider_sid=message_sid,
            )
            session.add(inbound_msg)
            session.commit()

            # Transition AUTO_REPLIED -> ENGAGED on first customer reply
            if existing_lead.state == LeadState.AUTO_REPLIED:
                from app.engine.lifecycle import transition
                try:
                    transition(session, existing_lead, LeadState.ENGAGED,
                               reason="customer_reply", meta={"first_reply": body[:200]})
                except ValueError:
                    pass  # May already be past AUTO_REPLIED

            # Capture what we need before session closes
            lead_id = existing_lead.id
            dealer_id = dealer.id
            dealer_slug = dealer.slug
            raw_from = payload.get("From", "")       # customer's real phone (for Twilio REST API)
            sms_from_number = to_number               # dealer's Twilio number

            # Return empty TwiML IMMEDIATELY — don't block on the AI call.
            # Twilio gives us ~15s; the AI + retries can take 30s+.
            # Process the AI reply in a background task and send via REST API.
            import asyncio

            async def _process_and_send():
                """Background entry point: creates a session, delegates to sync helper."""
                from app.db import get_session_factory
                bg_session = get_session_factory()()
                try:
                    _process_and_send_sync(
                        bg_session, lead_id, dealer_id, dealer_slug,
                        body, raw_from, sms_from_number,
                    )
                finally:
                    bg_session.close()

            asyncio.create_task(_process_and_send())
            return _empty_twiml()
        else:
            # New lead via SMS
            from app.adapters.intake.sms import TwilioSmsAdapter
            lead_data = TwilioSmsAdapter().parse(payload)

            from tools.route_lead import ingest_lead
            lead = ingest_lead(session, dealer, lead_data)

            # Get the auto-reply text from the most recent outbound message
            last_msg = _exec(session,
                select(Message).where(
                    Message.lead_id == lead.id,
                    Message.direction == Direction.OUTBOUND,
                ).order_by(Message.created_at.desc())
            ).first()

            reply_text = last_msg.body if last_msg else "Thanks for reaching out!"
            return _twiml(reply_text)

    except Exception:
        logger.exception("webhook_twilio_sms error")
        return _empty_twiml()
    finally:
        session.close()


# *** TEST MODE ONLY ***
# This function allows customers to test via WhatsApp.
# In production, customer conversations happen over SMS, not WhatsApp.
# Remove this function before deploying to real dealers.
async def _handle_customer_whatsapp_test(
    session, dealer, dealer_config, from_number, body, message_sid
) -> Response:
    """Handle customer WhatsApp messages in test mode.

    Routes to conversation engine for AI responses.
    In production, this should NOT exist — customers use SMS.
    """
    from app.engine.conversation import handle_turn
    from app.engine.lifecycle import transition
    from sqlalchemy import select
    from app.models import Lead, LeadState, Message, Direction, Channel, ConsentLog

    # Check opt-out keywords first
    opt_out_keywords = dealer_config.get("compliance", {}).get(
        "opt_out_keywords", ["STOP", "STOPALL", "UNSUBSCRIBE", "ARRET"]
    )
    if body.upper().strip() in [kw.upper() for kw in opt_out_keywords]:
        opt = ConsentLog(
            dealer_id=dealer.id,
            phone=from_number,
            action="opted_out",
            text=body,
        )
        session.add(opt)
        session.commit()
        return _twiml("You have been unsubscribed. Reply START to resubscribe.")

    # Check resubscribe keywords
    resubscribe_keywords = ["START", "STARTALL", "JOIN", "UNSTOP"]
    if body.upper().strip() in resubscribe_keywords:
        return _twiml("Welcome back! You've been resubscribed. Reply STOP to opt out again.")

    # Find or create lead
    existing_lead = _exec(session,
        select(Lead).where(
            Lead.dealer_id == dealer.id,
            Lead.phone == from_number,
            Lead.state.notin_([LeadState.SOLD, LeadState.LOST, LeadState.OPTED_OUT]),
        ).order_by(Lead.created_at.desc())
    ).first()

    if existing_lead:
        # Existing conversation
        lead_id = existing_lead.id
        dealer_id = dealer.id
        dealer_slug = dealer.slug

        # Log inbound message
        inbound_msg = Message(
            lead_id=lead_id,
            direction=Direction.INBOUND,
            channel=Channel.WHATSAPP,
            body=body,
            provider_sid=message_sid,
        )
        session.add(inbound_msg)
        session.commit()

        # Transition AUTO_REPLIED -> ENGAGED on first customer reply
        if existing_lead.state == LeadState.AUTO_REPLIED:
            try:
                transition(session, existing_lead, LeadState.ENGAGED,
                           reason="customer_reply", meta={"first_reply": body[:200]})
            except ValueError:
                pass

        # Get vehicle context
        vehicle = None
        if existing_lead.vehicle_id:
            from app.models import Vehicle
            vehicle = session.get(Vehicle, existing_lead.vehicle_id)

        # Generate AI response
        try:
            result = handle_turn(
                session, existing_lead, body,
                dealer_config=dealer_config,
                vehicle=vehicle,
            )
            ai_response = result.get("text", "Thanks for your message!")
            logger.info("[TEST MODE] AI response to WhatsApp customer %s: %s", from_number, ai_response[:100])
        except Exception:
            logger.exception("[TEST MODE] AI response failed for WhatsApp customer %s", from_number)
            ai_response = "Thanks for your message! A team member will follow up shortly."

        # Send WhatsApp reply via Twilio
        from app.transports.twilio import send_whatsapp
        whatsapp_sender = dealer_config.get("channels", {}).get("whatsapp_sender")
        if whatsapp_sender:
            try:
                send_whatsapp(
                    to_number=from_number,
                    from_number=whatsapp_sender,
                    body=ai_response,
                    dealer_id=dealer.id,
                    lead_id=lead_id,
                    session=session,
                    lead=existing_lead,
                )
                logger.info("[TEST MODE] WhatsApp reply sent to %s", from_number)
            except Exception:
                logger.exception("[TEST MODE] Failed to send WhatsApp reply to %s", from_number)
        else:
            logger.warning("[TEST MODE] No whatsapp_sender configured for dealer %s", dealer.slug)

        return _empty_twiml()
    else:
        # New lead — create it and send auto-reply
        from app.engine.router import ingest_lead
        from app.adapters.intake import NormalizedLead
        from app.models import Channel
        try:
            # Build NormalizedLead
            lead_data = NormalizedLead(
                source=Channel.WHATSAPP,
                name="",
                phone=from_number,
                message=body,
                consent=True,  # WhatsApp implies consent for testing
            )
            lead = ingest_lead(session, dealer, lead_data)
            lead_id = lead.id
            dealer_slug = dealer.slug

            # Get vehicle context
            vehicle = None
            if lead.vehicle_id:
                from app.models import Vehicle
                vehicle = session.get(Vehicle, lead.vehicle_id)

            # Generate AI response for new lead
            result = handle_turn(
                session, lead, body,
                dealer_config=dealer_config,
                vehicle=vehicle,
            )
            ai_response = result.get("text", "Thanks for reaching out!")
            logger.info("[TEST MODE] AI response to new WhatsApp customer %s: %s", from_number, ai_response[:100])

            # Send WhatsApp reply
            from app.transports.twilio import send_whatsapp
            whatsapp_sender = dealer_config.get("channels", {}).get("whatsapp_sender")
            if whatsapp_sender:
                try:
                    send_whatsapp(
                        to_number=from_number,
                        from_number=whatsapp_sender,
                        body=ai_response,
                        dealer_id=dealer.id,
                        lead_id=lead_id,
                        session=session,
                        lead=lead,
                    )
                    logger.info("[TEST MODE] WhatsApp auto-reply sent to new customer %s", from_number)
                except Exception:
                    logger.exception("[TEST MODE] Failed to send WhatsApp auto-reply to %s", from_number)

            return _empty_twiml()
        except Exception:
            logger.exception("[TEST MODE] Failed to create lead for WhatsApp customer %s", from_number)
            return _twiml("Sorry, something went wrong. Please try again later.")


@app.post("/webhook/twilio/whatsapp")
async def webhook_twilio_whatsapp(request: Request) -> Response:
    """Inbound WhatsApp from reps (claim replies: '1' to claim, '2' to pass).

    Tenant resolved by the WhatsApp sender number.
    Returns TwiML response.

    *** TEST MODE ONLY ***
    If sender is NOT a sales rep, routes to conversation engine for testing.
    In production, customer conversations happen over SMS, not WhatsApp.
    Remove customer fallback before deploying to real dealers.
    """
    # P0-01: parse form first, then validate signature.
    form = await request.form()
    payload = dict(form)

    if not _validate_twilio_signature(request, payload):
        return PlainTextResponse("Forbidden", status_code=403)

    session = _get_session()
    try:
        message_sid = payload.get("MessageSid", "")

        # Idempotency
        if _idempotency_check(session, message_sid):
            logger.info("Duplicate WhatsApp webhook sid=%s — skipping", message_sid)
            return _empty_twiml()

        from_number = payload.get("From", "").replace("whatsapp:", "")
        to_number = payload.get("To", "").replace("whatsapp:", "")
        body = (payload.get("Body", "") or "").strip()

        dealer = _find_dealer_by_whatsapp(session, to_number)
        if dealer is None:
            logger.warning("No dealer found for WhatsApp to=%s", to_number)
            return _empty_twiml()

        dealer_config = dealer.config or {}
        sales_team = dealer_config.get("sales_team", [])

        # Find the rep by their phone number (SMS-based claim/pass)
        rep = None
        for r in sales_team:
            rep_phone = (r.get("phone", "") or "").replace(" ", "").replace("-", "")
            from_norm = from_number.replace(" ", "").replace("-", "")
            if rep_phone == from_norm:
                rep = r
                break

        # *** TEST MODE ONLY ***
        # If sender is NOT a rep, route to conversation engine for testing.
        # In production, customer conversations happen over SMS, not WhatsApp.
        if rep is None:
            logger.info("[TEST MODE] Non-rep WhatsApp from=%s — routing to conversation engine", from_number)
            return await _handle_customer_whatsapp_test(session, dealer, dealer_config, from_number, body, message_sid)

        # Find the most recent ASSIGNED lead for this dealer and rep
        assigned_lead = _exec(session,
            select(Lead).where(
                Lead.dealer_id == dealer.id,
                Lead.state == LeadState.ASSIGNED,
                Lead.assigned_rep == rep["name"],
            ).order_by(Lead.created_at.desc())
        ).first()

        if assigned_lead is None:
            # Check ESCALATED too
            assigned_lead = _exec(session,
                select(Lead).where(
                    Lead.dealer_id == dealer.id,
                    Lead.state == LeadState.ESCALATED,
                ).order_by(Lead.created_at.desc())
            ).first()

        if assigned_lead is None:
            return _twiml("No pending leads to claim.")

        # Log the inbound WhatsApp message
        wa_msg = Message(
            lead_id=assigned_lead.id,
            direction=Direction.INBOUND,
            channel=Channel.WHATSAPP,
            body=body,
            provider_sid=message_sid,
        )
        session.add(wa_msg)
        session.commit()

        if body.strip() == "1":
            # Claim
            from app.engine.router import handle_claim
            handle_claim(session, assigned_lead, rep["name"])
            return _twiml(f"Lead claimed! {assigned_lead.name or 'Customer'} is yours.")
        elif body.strip() == "2":
            # Pass
            from app.engine.router import handle_pass
            handle_pass(
                session, assigned_lead, dealer, sales_team, rep["name"],
                sms_number=dealer_config.get("channels", {}).get("sms_number"),
            )
            return _twiml("Lead passed to next rep.")
        else:
            return _twiml("Reply 1 to claim, 2 to pass.")

    except Exception:
        logger.exception("webhook_twilio_whatsapp error")
        return _empty_twiml()
    finally:
        session.close()


@app.post("/webhook/twilio/voice")
async def webhook_twilio_voice(request: Request) -> Response:
    """Inbound/missed call -> missed-call text-back.

    If the call is unanswered/no-answer, sends an SMS text-back to the caller.
    Creates a Lead, logs the Message, and transitions to AUTO_REPLIED.
    """
    # P0-01: parse form first, then validate signature.
    form = await request.form()
    payload = dict(form)

    if not _validate_twilio_signature(request, payload):
        return PlainTextResponse("Forbidden", status_code=403)

    session = _get_session()
    try:
        from tools.detect_missed_call import handle_missed_call_from_webhook

        # Check if caller has opted out first
        from_number = payload.get("From", "")
        opt_out = _exec(session,
            select(ConsentLog).where(
                ConsentLog.phone == from_number,
                ConsentLog.action == "opted_out",
            )
        ).first()

        if opt_out:
            return _empty_twiml()

        # Handle the missed call
        def _sms_sender(to, from_, body):
            """Send SMS via Twilio."""
            from tools.send_sms import send_sms
            return send_sms(to=to, from_=from_, body=body)

        result = handle_missed_call_from_webhook(
            session=session,
            payload=payload,
            sms_sender=_sms_sender,
        )

        if result.success:
            logger.info("Missed call handled: lead=%d, sid=%s", result.lead_id, result.message_sid)
            return _twiml(payload.get("Body", ""))  # Empty TwiML — SMS is sent via API
        else:
            logger.info("Missed call skipped: %s", result.error)
            return _empty_twiml()

    except Exception:
        logger.exception("webhook_twilio_voice error")
        return _empty_twiml()
    finally:
        session.close()


@app.post("/webhook/twilio/status")
async def webhook_twilio_status(request: Request) -> dict:
    """Twilio delivery status callback. Updates Message rows with delivery_status + error_code."""
    session = _get_session()
    try:
        form = await request.form()
        payload = dict(form)

        message_sid = payload.get("MessageSid", "")
        status = payload.get("MessageStatus", "")
        error_code = payload.get("ErrorCode")

        if message_sid and status:
            msg = _exec(session,
                select(Message).where(Message.provider_sid == message_sid)
            ).first()
            if msg:
                msg.delivery_status = status
                if error_code:
                    msg.error_code = str(error_code)
                session.commit()
                logger.info("Message sid=%s status=%s error=%s", message_sid, status, error_code)

        return {"ok": True}
    except Exception as exc:
        logger.exception("webhook_twilio_status error")
        return {"error": "Internal server error"}
    finally:
        session.close()


@app.post("/webhook/messenger")
async def webhook_messenger(request: Request) -> dict:
    """Facebook Messenger via Twilio Conversations."""
    try:
        payload = await request.json()
        # TODO: Implement messenger adapter + conversation routing
        return {"status": "not_implemented", "payload_keys": list(payload.keys())}
    except Exception as exc:
        logger.exception("webhook_messenger error")
        return {"error": "Internal server error"}


@app.get("/webhook/messenger")
async def webhook_messenger_verify(request: Request) -> Response:
    """Facebook webhook verification endpoint."""
    return PlainTextResponse(request.query_params.get("hub.challenge", ""))