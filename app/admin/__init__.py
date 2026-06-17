"""Admin dashboard — platform-level management (dealers, onboarding, settings).

Separate from the dealer-facing dashboard so that admin-only routes
(clients/dealers, onboarding, global settings) don't leak into dealer views.
"""

from __future__ import annotations
import hashlib
import json
import logging
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

import bcrypt
import yaml
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session_factory
from app.models import Dealer, Lead, LeadState, Vehicle

logger = logging.getLogger("speed-to-lead.admin")

router = APIRouter(prefix="/admin", tags=["admin"])

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# Auth helpers (shared secret with dashboard)
# ---------------------------------------------------------------------------

def _get_serializer() -> URLSafeTimedSerializer:
    if settings.dashboard_secret:
        secret = settings.dashboard_secret
    elif settings.dashboard_password:
        secret = hashlib.sha256(settings.dashboard_password.encode()).hexdigest()
    else:
        if settings.environment == "production":
            raise RuntimeError("DASHBOARD_SECRET or DASHBOARD_PASSWORD must be set in production")
        secret = "speed-to-lead-dev-secret-not-for-production"
    return URLSafeTimedSerializer(secret)


def _verify_password(password: str) -> bool:
    if settings.dashboard_password_hash:
        try:
            return bcrypt.checkpw(password.encode(), settings.dashboard_password_hash.encode())
        except Exception:
            return False
    return password == settings.dashboard_password


def require_admin_auth(session: str = Cookie(None)):
    """FastAPI dependency — redirect to /admin/login if not authenticated."""
    if session is None:
        raise HTTPException(
            status_code=303,
            headers={"Location": "/admin/login"},
        )
    serializer = _get_serializer()
    try:
        data = serializer.loads(session, max_age=86400)
    except (BadSignature, SignatureExpired):
        raise HTTPException(
            status_code=303,
            headers={"Location": "/admin/login"},
        )
    # Reject dealer cookies — they must not work on admin routes
    if data.get("role") == "dealer":
        raise HTTPException(
            status_code=303,
            headers={"Location": "/admin/login"},
        )


# Rate-limiting state (shared with dashboard via same process)
_login_attempts: dict[str, list[float]] = {}
_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 900


def _check_rate_limit(ip: str) -> bool:
    now = time.time()
    cutoff = now - _WINDOW_SECONDS
    if ip in _login_attempts:
        _login_attempts[ip] = [t for t in _login_attempts[ip] if t > cutoff]
        if not _login_attempts[ip]:
            del _login_attempts[ip]
    if len(_login_attempts) > 100:
        for k in list(_login_attempts):
            _login_attempts[k] = [t for t in _login_attempts[k] if t > cutoff]
            if not _login_attempts[k]:
                del _login_attempts[k]
    if ip in _login_attempts and len(_login_attempts[ip]) >= _MAX_ATTEMPTS:
        return True
    return False


def _record_failure(ip: str) -> None:
    _login_attempts.setdefault(ip, []).append(time.time())


def _clear_rate_limit(ip: str) -> None:
    _login_attempts.pop(ip, None)


def _get_session() -> Session:
    return get_session_factory()()


# ---------------------------------------------------------------------------
# Onboarding helpers
# ---------------------------------------------------------------------------

def _generate_web_token(slug: str) -> str:
    return f"{slug}-{secrets.token_hex(3)}"


def _validate_slug(slug: str) -> bool:
    return bool(re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', slug))


def _parse_reps(form_data: dict) -> list[dict]:
    reps = []
    idx = 0
    while f"rep_name_{idx}" in form_data:
        name = form_data.get(f"rep_name_{idx}", "").strip()
        whatsapp = form_data.get(f"rep_whatsapp_{idx}", "").strip()
        active = form_data.get(f"rep_active_{idx}") == "on"
        if name and whatsapp:
            reps.append({"name": name, "whatsapp": whatsapp, "active": active})
        idx += 1
    return reps


def _build_dealer_config(form_data: dict) -> tuple[dict, str]:
    from app.config import DealerConfig

    slug = form_data["slug"].strip()
    name = form_data["business_name"].strip()

    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    hours = {}
    for day in days:
        val = form_data.get(f"hours_{day}", "").strip()
        if val:
            hours[day] = val

    reps = _parse_reps(form_data)

    consent_raw = form_data.get("consent_text", "").strip()
    if not consent_raw:
        consent_raw = f"By submitting you agree to receive texts from {name}. Reply STOP to opt out."
    consent_text = consent_raw.replace("{dealer_name}", name)

    keywords_raw = form_data.get("opt_out_keywords", "").strip()
    opt_out_keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()] if keywords_raw else ["STOP", "STOPALL", "UNSUBSCRIBE", "ARRET"]

    web_token = form_data.get("web_form_token", "").strip() or _generate_web_token(slug)

    config = {
        "dealer": {
            "slug": slug,
            "name": name,
            "timezone": form_data.get("timezone", "America/Vancouver"),
            "hours": hours,
            "location_address": form_data.get("address", "").strip() or None,
            "maps_url": form_data.get("maps_url", "").strip() or None,
            "main_phone": form_data.get("main_phone", "").strip() or None,
        },
        "channels": {
            "sms_number": form_data.get("sms_number", "").strip() or None,
            "whatsapp_sender": form_data.get("whatsapp_sender", "").strip() or None,
            "lead_email_inbox": form_data.get("lead_email_inbox", "").strip() or None,
            "facebook_page_id": form_data.get("facebook_page_id", "").strip() or None,
            "web_form_token": web_token,
        },
        "sales_team": reps,
        "routing": {
            "strategy": form_data.get("routing_strategy", "round_robin"),
            "claim_timeout_min": int(form_data.get("claim_timeout_min", 5)),
            "escalation": ["reassign", "notify_manager"],
            "manager_phone": form_data.get("manager_phone", "").strip() or None,
        },
        "ai": {
            "persona": form_data.get("ai_persona", "").strip() or "friendly, concise, no-pressure local sales rep",
            "goal": form_data.get("ai_goal", "book_appointment"),
            "guardrails": {
                "no_price_negotiation": form_data.get("no_price_negotiation") == "on",
                "no_financing_promises": form_data.get("no_financing_promises") == "on",
            },
        },
        "followups": {
            "cadence_min": [60, 1440, 4320, 10080],
        },
        "inventory": {
            "source": form_data.get("inventory_source", "auto"),
            "url": form_data.get("inventory_url", "").strip() or None,
            "platform": form_data.get("inventory_platform", "").strip() or "",
            "refresh_min": int(form_data.get("inventory_refresh_min", 180)),
            "field_map": "auto",
        },
        "lead_org": {
            "mode": form_data.get("lead_org_mode", "native"),
            "target": form_data.get("lead_org_target", "").strip() or "",
            "credentials_ref": form_data.get("lead_org_credentials_ref", "").strip() or "",
        },
        "compliance": {
            "region": form_data.get("compliance_region", "CA-BC"),
            "consent_text": consent_text,
            "opt_out_keywords": opt_out_keywords,
            "quiet_hours": form_data.get("quiet_hours", "21:00-08:00").strip() or "21:00-08:00",
        },
    }

    DealerConfig.model_validate(config)
    yaml_str = yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return config, yaml_str


# ===========================================================================
# ROUTES
# ===========================================================================

# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

@router.get("/login")
async def admin_login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin_login.html",
        context={"request": request, "active_page": "login", "error": None},
    )


@router.post("/login")
async def admin_login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    ip = request.client.host if request.client else "unknown"

    if _check_rate_limit(ip):
        return templates.TemplateResponse(
            request=request,
            name="admin_login.html",
            context={"request": request, "error": "Too many attempts. Try again later."},
            status_code=429,
        )

    if username == settings.dashboard_user and _verify_password(password):
        _clear_rate_limit(ip)
        serializer = _get_serializer()
        token = serializer.dumps({"user": username, "ts": time.time()})
        response = RedirectResponse("/admin/dealers", status_code=303)
        response.set_cookie("session", token, httponly=True, max_age=86400, samesite="lax")
        return response

    _record_failure(ip)
    return templates.TemplateResponse(
        request=request,
        name="admin_login.html",
        context={"request": request, "error": "Invalid credentials"},
        status_code=401,
    )


@router.get("/logout")
async def admin_logout():
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie("session")
    return response


# ---------------------------------------------------------------------------
# Protected routes
# ---------------------------------------------------------------------------

@router.get("")
@router.get("/")
async def admin_index(request: Request, _auth: None = Depends(require_admin_auth)):
    return RedirectResponse(url="/admin/dealers")


# ---------------------------------------------------------------------------
# Dealers (was clients)
# ---------------------------------------------------------------------------

@router.get("/dealers")
async def dealers_list(request: Request, _auth: None = Depends(require_admin_auth)):
    session = _get_session()
    try:
        dealers = session.execute(
            select(Dealer).order_by(Dealer.created_at.desc())
        ).scalars().all()

        lead_count_rows = session.execute(
            select(Lead.dealer_id, func.count(Lead.id)).group_by(Lead.dealer_id)
        ).all()
        lead_counts: dict[int, int] = {row[0]: row[1] for row in lead_count_rows}

        clients = []
        for dealer in dealers:
            config = dealer.config or {}
            channels = config.get("channels", {})
            lead_total = lead_counts.get(dealer.id, 0)
            is_active = bool(dealer.sms_number) and lead_total > 0

            has_sms = bool(channels.get("sms_number") or dealer.sms_number)
            has_whatsapp = bool(channels.get("whatsapp_sender") or dealer.whatsapp_sender)
            has_web_form = bool(channels.get("web_form_token") or dealer.web_form_token)

            created_at = dealer.created_at
            if created_at:
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                created_display = created_at.strftime("%b %d, %Y")
            else:
                created_display = "—"

            clients.append({
                "slug": dealer.slug,
                "name": dealer.name,
                "timezone": dealer.timezone,
                "is_active": is_active,
                "lead_count": lead_total,
                "has_sms": has_sms,
                "has_whatsapp": has_whatsapp,
                "has_web_form": has_web_form,
                "created_display": created_display,
            })

        total_clients = len(clients)
        active_clients = sum(1 for c in clients if c["is_active"])
        total_leads = sum(c["lead_count"] for c in clients)
        pending_clients = total_clients - active_clients

        return templates.TemplateResponse(request=request, name="dealers.html", context={
            "request": request,
            "active_page": "dealers",
            "clients": clients,
            "total_clients": total_clients,
            "active_clients": active_clients,
            "total_leads": total_leads,
            "pending_clients": pending_clients,
        })
    finally:
        session.close()


@router.get("/dealers/export-all")
async def dealers_export_all(request: Request, _auth: None = Depends(require_admin_auth)):
    import io
    import zipfile

    session = _get_session()
    try:
        dealers = session.execute(select(Dealer)).scalars().all()

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for dealer in dealers:
                config = dealer.config or {}
                yaml_str = yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)
                zf.writestr(f"{dealer.slug}.yaml", yaml_str)

            manifest_lines = ["# Speed to Lead - Dealer Config Export", f"# Exported: {datetime.now(timezone.utc).isoformat()}", ""]
            for dealer in dealers:
                manifest_lines.append(f"- {dealer.slug}: {dealer.name}")
            zf.writestr("manifest.yaml", "\n".join(manifest_lines))

        zip_buffer.seek(0)

        return Response(
            content=zip_buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="all-dealers-{datetime.now(timezone.utc).strftime("%Y%m%d")}.zip"',
            },
        )
    finally:
        session.close()


@router.get("/dealers/{slug}")
async def dealer_detail(request: Request, slug: str, _auth: None = Depends(require_admin_auth)):
    session = _get_session()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == slug)
        ).scalars().first()

        if not dealer:
            return HTMLResponse("<h1>Dealer not found</h1>", status_code=404)

        config = dealer.config or {}
        channels = config.get("channels", {})
        dealer_cfg = config.get("dealer", {})
        ai_cfg = config.get("ai", {})
        routing_cfg = config.get("routing", {})
        compliance_cfg = config.get("compliance", {})
        sales_team = config.get("sales_team", [])
        hours = dealer_cfg.get("hours", {})

        all_leads = session.execute(
            select(Lead).where(Lead.dealer_id == dealer.id)
        ).scalars().all()
        total_leads = len(all_leads)
        active_leads = sum(
            1 for l in all_leads
            if l.state not in (LeadState.SOLD, LeadState.LOST, LeadState.OPTED_OUT)
        )
        sold_leads = sum(1 for l in all_leads if l.state == LeadState.SOLD)

        provisioning = config.get("provisioning", {})
        sales_team_list = config.get("sales_team", [])

        def _prov(key, fallback):
            if key in provisioning:
                return bool(provisioning[key])
            return fallback

        has_sms = bool(channels.get("sms_number") or dealer.sms_number)
        has_team = bool(sales_team_list) or bool(config.get("sales_team"))
        has_ai = bool(ai_cfg.get("persona", ""))
        has_leads = total_leads > 0

        checklist = {
            "yaml_created": True,
            "twilio_number": _prov("dealer_info", has_sms),
            "sms_webhook": _prov("sms_configured", has_sms),
            "whatsapp_sandbox": _prov("sms_configured", has_sms),
            "test_sms": _prov("test_lead", has_leads),
            "auto_reply": _prov("test_lead", has_leads),
            "rep_notify": _prov("team_configured", has_team),
            "opt_out": any(l.state == LeadState.OPTED_OUT for l in all_leads) if all_leads else False,
            "dashboard": True,
            "go_live": _prov("live", has_sms and has_leads),
        }
        completed_steps = sum(1 for v in checklist.values() if v)
        total_steps = len(checklist)

        base_url = config.get("public_base_url", "https://your-domain.com")
        webhook_url = f"{base_url}/webhook/sms"
        web_token = channels.get("web_form_token", dealer.web_form_token or "")
        embed_code = f'<form action="{base_url}/webhook/form/{web_token}" method="POST">\n  <input type="text" name="name" placeholder="Name" required>\n  <input type="tel" name="phone" placeholder="Phone" required>\n  <input type="email" name="email" placeholder="Email">\n  <button type="submit">Get Info</button>\n</form>' if web_token else "<!-- Configure web_form_token first -->"

        return templates.TemplateResponse(request=request, name="dealer_detail.html", context={
            "request": request,
            "active_page": "dealers",
            "dealer_name": dealer.name,
            "dealer_slug": dealer.slug,
            "timezone": dealer.timezone,
            "sms_number": channels.get("sms_number") or dealer.sms_number,
            "whatsapp_sender": channels.get("whatsapp_sender") or dealer.whatsapp_sender,
            "web_form_token": channels.get("web_form_token") or dealer.web_form_token,
            "main_phone": dealer_cfg.get("main_phone", ""),
            "location_address": dealer_cfg.get("location_address", ""),
            "sales_team": sales_team,
            "hours": hours,
            "ai_persona": ai_cfg.get("persona", ""),
            "compliance": compliance_cfg if compliance_cfg else None,
            "total_leads": total_leads,
            "active_leads": active_leads,
            "sold_leads": sold_leads,
            "checklist": checklist,
            "completed_steps": completed_steps,
            "total_steps": total_steps,
            "webhook_url": webhook_url,
            "embed_code": embed_code,
            "config": config,
            "dealer_obj": dealer,
        })
    finally:
        session.close()


@router.get("/dealers/{slug}/export-yaml")
async def dealer_export_yaml(request: Request, slug: str, _auth: None = Depends(require_admin_auth)):
    session = _get_session()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == slug)
        ).scalars().first()

        if not dealer:
            return HTMLResponse("<h1>Dealer not found</h1>", status_code=404)

        config = dealer.config or {}
        yaml_str = yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return Response(
            content=yaml_str,
            media_type="application/x-yaml",
            headers={
                "Content-Disposition": f'attachment; filename="{slug}.yaml"',
            },
        )
    finally:
        session.close()


@router.post("/dealers/{slug}/edit")
async def dealer_edit(request: Request, slug: str, _auth: None = Depends(require_admin_auth)):
    session = _get_session()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == slug)
        ).scalars().first()

        if not dealer:
            return HTMLResponse("<h1>Dealer not found</h1>", status_code=404)

        form_data = await request.form()
        config = dict(dealer.config) if dealer.config else {}

        business_name = form_data.get("business_name", "").strip()
        if business_name:
            dealer.name = business_name
            config.setdefault("dealer", {})["name"] = business_name

        sms_number = form_data.get("sms_number", "").strip()
        config.setdefault("channels", {})["sms_number"] = sms_number or None
        dealer.sms_number = sms_number or None

        whatsapp_number = form_data.get("whatsapp_number", "").strip()
        config.setdefault("channels", {})["whatsapp_sender"] = whatsapp_number or None
        dealer.whatsapp_sender = whatsapp_number or None

        team_members_raw = form_data.get("team_members", "").strip()
        if team_members_raw:
            try:
                team_members = json.loads(team_members_raw)
                config["sales_team"] = team_members
            except (json.JSONDecodeError, TypeError):
                pass

        ai_persona = form_data.get("ai_persona", "").strip()
        config.setdefault("ai", {})["persona"] = ai_persona or config.get("ai", {}).get("persona", "")

        business_hours_raw = form_data.get("business_hours", "").strip()
        if business_hours_raw:
            try:
                business_hours = json.loads(business_hours_raw)
                config.setdefault("dealer", {})["hours"] = business_hours
            except (json.JSONDecodeError, TypeError):
                pass

        dealer.config = config
        session.add(dealer)
        session.commit()

        return RedirectResponse(url=f"/admin/dealers/{slug}", status_code=303)
    finally:
        session.close()


@router.post("/dealers/{slug}/delete")
async def dealer_delete(request: Request, slug: str, _auth: None = Depends(require_admin_auth)):
    session = _get_session()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == slug)
        ).scalars().first()

        if not dealer:
            return HTMLResponse("<h1>Dealer not found</h1>", status_code=404)

        if hasattr(dealer, 'is_active'):
            dealer.is_active = False
            session.add(dealer)
            session.commit()
        else:
            session.delete(dealer)
            session.commit()

        return RedirectResponse(url="/admin/dealers", status_code=303)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------

@router.get("/onboarding")
async def onboarding_page(request: Request, _auth: None = Depends(require_admin_auth)):
    return templates.TemplateResponse(request=request, name="onboarding.html", context={
        "request": request,
        "active_page": "onboarding",
        "form": {},
        "success": False,
        "error": None,
    })


@router.post("/onboarding")
async def onboarding_submit(request: Request, _auth: None = Depends(require_admin_auth)):
    form_data = await request.form()
    form_dict = dict(form_data)

    for key in ["no_price_negotiation", "no_financing_promises"]:
        if key not in form_dict:
            form_dict[key] = "off"
    idx = 0
    while f"rep_name_{idx}" in form_dict:
        if f"rep_active_{idx}" not in form_dict:
            form_dict[f"rep_active_{idx}"] = "off"
        idx += 1

    slug = form_dict.get("slug", "").strip()

    if not slug or not _validate_slug(slug):
        return templates.TemplateResponse(request=request, name="onboarding.html", context={
            "request": request,
            "active_page": "onboarding",
            "form": form_dict,
            "success": False,
            "error": "Invalid slug. Use lowercase letters, numbers, and hyphens only (e.g. sunrise-auto).",
        })

    session = _get_session()
    try:
        existing = session.execute(
            select(Dealer).where(Dealer.slug == slug)
        ).scalars().first()
        if existing:
            return templates.TemplateResponse(request=request, name="onboarding.html", context={
                "request": request,
                "active_page": "onboarding",
                "form": form_dict,
                "success": False,
                "error": f"A dealer with slug '{slug}' already exists in the database.",
            })
    finally:
        session.close()

    try:
        config, yaml_str = _build_dealer_config(form_dict)
    except Exception as exc:
        return templates.TemplateResponse(request=request, name="onboarding.html", context={
            "request": request,
            "active_page": "onboarding",
            "form": form_dict,
            "success": False,
            "error": f"Validation error: {exc}",
        })

    session = _get_session()
    try:
        dealer = Dealer(
            slug=slug,
            name=form_dict["business_name"].strip(),
            timezone=form_dict.get("timezone", "America/Vancouver"),
            sms_number=form_dict.get("sms_number", "").strip() or None,
            whatsapp_sender=form_dict.get("whatsapp_sender", "").strip() or None,
            web_form_token=config["channels"]["web_form_token"],
            config=config,
        )
        session.add(dealer)
        session.commit()
        session.refresh(dealer)
    except Exception as exc:
        session.rollback()
        return templates.TemplateResponse(request=request, name="onboarding.html", context={
            "request": request,
            "active_page": "onboarding",
            "form": form_dict,
            "success": False,
            "error": f"Failed to create dealer record: {exc}",
        })
    finally:
        session.close()

    return templates.TemplateResponse(request=request, name="onboarding.html", context={
        "request": request,
        "active_page": "onboarding",
        "form": {},
        "success": True,
        "error": None,
        "dealer_name": form_dict["business_name"].strip(),
        "dealer_slug": slug,
        "yaml_content": yaml_str,
    })


# ---------------------------------------------------------------------------
# Seed Inventory (one-shot endpoint)
# ---------------------------------------------------------------------------

# Enriched spec data keyed by stock_no
_ENRICHED_SPECS: dict[str, dict] = {
    "TDM001": {
        "engine": "2.0L 4-cyl", "transmission": "CVT", "drivetrain": "FWD",
        "horsepower": "158 hp", "torque": "138 lb-ft",
        "fuel_economy": "7.1 L/100km combined",
        "exterior_color": "Crystal Black Pearl", "interior": "Black cloth",
        "vin": "2HGFC2F59PH000001",
        "features": ["Honda Sensing suite", "Apple CarPlay", "Android Auto", "7\" touchscreen", "Lane Keep Assist", "Adaptive Cruise Control", "18\" alloy wheels", "LED headlights", "sunroof"],
    },
    "TDM002": {
        "engine": "5.0L V8", "transmission": "10-speed automatic", "drivetrain": "RWD",
        "horsepower": "460 hp", "torque": "420 lb-ft",
        "fuel_economy": "12.4 L/100km combined",
        "exterior_color": "Oxford White", "interior": "Ebony leather",
        "vin": "1FA6P8CF3M5100002",
        "features": ["SYNC 3", "8\" touchscreen", "Brembo brakes", "limited-slip differential", "launch control", "line lock", "selectable drive modes", "dual exhaust", "rear spoiler"],
    },
    "TDM003": {
        "engine": "2.5L 4-cyl", "transmission": "8-speed automatic", "drivetrain": "AWD",
        "horsepower": "203 hp", "torque": "184 lb-ft",
        "fuel_economy": "8.0 L/100km combined",
        "exterior_color": "Magnetic Grey Metallic", "interior": "Black SofTex",
        "vin": "2T3P1RFV7PW000003",
        "features": ["Toyota Safety Sense 2.5+", "8\" touchscreen", "Apple CarPlay", "Android Auto", "blind spot monitor", "rear cross-traffic alert", "dual-zone climate", "power liftgate", "17\" alloy wheels"],
    },
    "TDM004": {
        "engine": "2.0L 4-cyl", "transmission": "CVT (IVT)", "drivetrain": "FWD",
        "horsepower": "147 hp", "torque": "132 lb-ft",
        "fuel_economy": "7.3 L/100km combined",
        "exterior_color": "Phantom Black", "interior": "Black cloth",
        "vin": "KMHD84LF3LU000004",
        "features": ["8\" touchscreen", "Apple CarPlay", "Android Auto", "forward collision avoidance", "lane keep assist", "driver attention warning", "heated front seats", "heated steering wheel", "16\" alloy wheels"],
    },
    "TDM005": {
        "engine": "1.4L Turbo 4-cyl", "transmission": "8-speed automatic", "drivetrain": "FWD",
        "horsepower": "147 hp", "torque": "184 lb-ft",
        "fuel_economy": "6.9 L/100km combined",
        "exterior_color": "Pure White", "interior": "Titan Black",
        "vin": "3VWC57BU3KM000005",
        "features": ["VW Digital Cockpit", "6.5\" touchscreen", "App-Connect", "blind spot monitor", "rear traffic alert", "heated front seats", "heated steering wheel", "LED headlights", "16\" alloy wheels"],
    },
    "TDM006": {
        "engine": "2.5L 4-cyl", "transmission": "8-speed automatic", "drivetrain": "FWD",
        "horsepower": "203 hp", "torque": "184 lb-ft",
        "fuel_economy": "7.1 L/100km combined",
        "exterior_color": "Celestial Silver Metallic", "interior": "Black SofTex",
        "vin": "4T1B61HK3NU000006",
        "features": ["Toyota Safety Sense 2.5+", "9\" touchscreen", "Apple CarPlay", "Android Auto", "wireless charging", "sport-tuned suspension", "18\" black alloy wheels", "dual exhaust", "LED headlights"],
    },
    "TDM007": {
        "engine": "2.5L 4-cyl", "transmission": "CVT", "drivetrain": "FWD",
        "horsepower": "188 hp", "torque": "180 lb-ft",
        "fuel_economy": "7.5 L/100km combined",
        "exterior_color": "Brilliant Silver Metallic", "interior": "Charcoal cloth",
        "vin": "1N4BL4CV3NN000007",
        "features": ["Nissan Safety Shield 360", "8\" touchscreen", "Apple CarPlay", "Android Auto", "blind spot warning", "rear cross-traffic alert", "intelligent cruise control", "heated front seats", "17\" alloy wheels"],
    },
    "TDM008": {
        "engine": "5.7L HEMI V8", "transmission": "8-speed automatic", "drivetrain": "RWD",
        "horsepower": "375 hp", "torque": "410 lb-ft",
        "fuel_economy": "13.1 L/100km combined",
        "exterior_color": "Go Mango", "interior": "Black Nappa leather",
        "vin": "2C3CDZBT9NH000008",
        "features": ["Uconnect 4C", "8.4\" touchscreen", "Apple CarPlay", "Android Auto", "performance suspension", "Brembo brakes", "launch assist", "line lock", "super track pack", "20\" satin carbon wheels"],
    },
    "TDM009": {
        "engine": "Single electric motor", "transmission": "Single-speed fixed", "drivetrain": "RWD",
        "horsepower": "283 hp", "torque": "307 lb-ft",
        "range": "423 km",
        "exterior_color": "Pearl White Multi-Coat", "interior": "Black vegan leather",
        "vin": "5YJ3E1EA2MF000009",
        "features": ["15\" touchscreen", "Autopilot", "over-the-air updates", "sentry mode", "dashcam", "heated front and rear seats", "glass roof", "wireless phone docking", "LED fog lights", "18\" Aero wheels"],
    },
    "TDM010": {
        "engine": "3.6L V6", "transmission": "8-speed automatic", "drivetrain": "RWD",
        "horsepower": "335 hp", "torque": "284 lb-ft",
        "fuel_economy": "10.7 L/100km combined",
        "exterior_color": "Riverside Blue Metallic", "interior": "Jet Black cloth",
        "vin": "1G1FB1RS5L0100010",
        "features": ["Chevrolet Infotainment 3", "7\" touchscreen", "Apple CarPlay", "Android Auto", "rear vision camera", "Brembo front brakes", "limited-slip differential", "sport-tuned suspension", "18\" wheels"],
    },
    "TDM011": {
        "engine": "2.0L Turbo 4-cyl", "transmission": "8-speed automatic (Steptronic)", "drivetrain": "AWD",
        "horsepower": "255 hp", "torque": "295 lb-ft",
        "fuel_economy": "8.1 L/100km combined",
        "exterior_color": "Alpine White", "interior": "Black Vernasca leather",
        "vin": "WBA5R7C09NFK00011",
        "features": ["BMW iDrive 7", "10.25\" touchscreen", "wireless Apple CarPlay", "Harman Kardon surround sound", "gesture control", "wireless charging", "M Sport suspension", "LED headlights", "18\" M wheels"],
    },
    "TDM012": {
        "engine": "1.5L Turbo 4-cyl", "transmission": "CVT", "drivetrain": "AWD",
        "horsepower": "190 hp", "torque": "179 lb-ft",
        "fuel_economy": "7.7 L/100km combined",
        "exterior_color": "Platinum White Pearl", "interior": "Black leather",
        "vin": "2HKRW2H5XPH000012",
        "features": ["Honda Sensing suite", "9\" touchscreen", "wireless Apple CarPlay", "wireless Android Auto", "wireless charging", "Bose 12-speaker audio", "power tailgate", "heated front and rear seats", "18\" alloy wheels"],
    },
    "TDM013": {
        "engine": "2.0L Turbo 4-cyl", "transmission": "9-speed automatic", "drivetrain": "AWD",
        "horsepower": "246 hp", "torque": "269 lb-ft",
        "fuel_economy": "9.8 L/100km combined",
        "exterior_color": "Eiger Grey", "interior": "Ebony grained leather",
        "vin": "SALZA2BN7MH000013",
        "features": ["Pivi Pro", "10\" touchscreen", "Apple CarPlay", "Android Auto", "Meridian sound system", "terrain response 2", "clear sight rear view mirror", "3D surround camera", "heated front seats", "20\" alloy wheels"],
    },
    "TDM014": {
        "engine": "2.0L Turbo 4-cyl + mild hybrid", "transmission": "9-speed automatic (9G-TRONIC)", "drivetrain": "AWD",
        "horsepower": "255 hp", "torque": "295 lb-ft",
        "fuel_economy": "8.3 L/100km combined",
        "exterior_color": "Obsidian Black Metallic", "interior": "Black MB-Tex",
        "vin": "W1KAF4GB3NN000014",
        "features": ["MBUX", "11.9\" central touchscreen", "12.3\" digital instrument cluster", "wireless Apple CarPlay", "wireless Android Auto", "Burmester 3D surround sound", "heated front seats", "ambient lighting", "18\" AMG wheels"],
    },
    "TDM015": {
        "engine": "2.5L 4-cyl", "transmission": "8-speed automatic", "drivetrain": "AWD",
        "horsepower": "187 hp", "torque": "178 lb-ft",
        "fuel_economy": "8.4 L/100km combined",
        "exterior_color": "Phantom Black", "interior": "Black cloth",
        "vin": "KM8J3CA26PU000015",
        "features": ["Hyundai SmartSense", "10.25\" touchscreen", "Apple CarPlay", "Android Auto", "wireless charging", "blind spot collision avoidance", "rear cross-traffic avoidance", "heated front seats", "heated steering wheel", "LED headlights", "17\" alloy wheels"],
    },
    "TDM016": {
        "engine": "2.7L EcoBoost V6 Twin-Turbo", "transmission": "10-speed automatic", "drivetrain": "4WD",
        "horsepower": "325 hp", "torque": "400 lb-ft",
        "fuel_economy": "11.8 L/100km combined",
        "exterior_color": "Iconic Silver Metallic", "interior": "Medium Earth Grey cloth",
        "vin": "1FTEW1EP3MKD00016",
        "features": ["SYNC 4", "12\" touchscreen", "Apple CarPlay", "Android Auto", "Ford Co-Pilot360", "pro power onboard (2.4kW)", "trailer tow package", "tailgate step", "spray-in bedliner", "18\" chrome wheels"],
    },
    "TDM017": {
        "engine": "2.5L 4-cyl", "transmission": "6-speed automatic (SKYACTIV-Drive)", "drivetrain": "AWD",
        "horsepower": "187 hp", "torque": "186 lb-ft",
        "fuel_economy": "8.2 L/100km combined",
        "exterior_color": "Soul Red Crystal Metallic", "interior": "Black cloth",
        "vin": "JM3KFBCM6P0000017",
        "features": ["Mazda Connect", "10.25\" display", "Apple CarPlay", "Android Auto", "i-Activsense safety suite", "smart brake support", "blind spot monitoring", "rear cross-traffic alert", "heated front seats", "17\" alloy wheels"],
    },
    "TDM018": {
        "engine": "2.0L 4-cyl", "transmission": "CVT (Dynamic Shift)", "drivetrain": "FWD",
        "horsepower": "169 hp", "torque": "151 lb-ft",
        "fuel_economy": "6.8 L/100km combined",
        "exterior_color": "Blue Crush Metallic", "interior": "Black fabric",
        "vin": "JTDKNRDU3L0000018",
        "features": ["Toyota Safety Sense 2.0", "8\" touchscreen", "Apple CarPlay", "Android Auto", "blind spot monitor", "sport driving mode", "18\" machined alloy wheels", "LED headlights", "rear spoiler"],
    },
    "TDM019": {
        "engine": "1.5L Turbo 4-cyl", "transmission": "6-speed automatic", "drivetrain": "FWD",
        "horsepower": "170 hp", "torque": "203 lb-ft",
        "fuel_economy": "8.2 L/100km combined",
        "exterior_color": "Iron Grey Metallic", "interior": "Jet Black cloth",
        "vin": "3GNAXHEV3NS000019",
        "features": ["Chevrolet Infotainment 3", "7\" touchscreen", "Apple CarPlay", "Android Auto", "rear vision camera", "teen driver technology", "keyless open", "heated front seats", "17\" aluminum wheels"],
    },
    "TDM020": {
        "engine": "2.0L Turbo 4-cyl", "transmission": "7-speed dual-clutch (S tronic)", "drivetrain": "AWD (quattro)",
        "horsepower": "248 hp", "torque": "273 lb-ft",
        "fuel_economy": "8.1 L/100km combined",
        "exterior_color": "Ibis White", "interior": "Black leather",
        "vin": "WAUENAF4XKN000020",
        "features": ["Audi MMI", "10.1\" touchscreen", "wireless Apple CarPlay", "Bang & Olufsen 3D sound", "virtual cockpit plus", "adaptive cruise control", "lane departure warning", "heated front seats", "sport suspension", "18\" 5-spoke wheels"],
    },
}


@router.post("/api/seed-vehicles")
async def seed_vehicles(request: Request, _auth: None = Depends(require_admin_auth)):
    """One-shot endpoint: seed 20 demo vehicles for a given dealer slug.

    POST /admin/api/seed-vehicles  (JSON body: {"slug": "premier-auto"})
    Requires admin authentication. DISABLED in production.
    """
    if settings.environment == "production":
        seed_secret = request.headers.get("X-Seed-Secret", "")
        import os
        expected = os.environ.get("SEED_SECRET", "")
        if not expected or seed_secret != expected:
            return {"error": "Seed endpoints are disabled in production"}

    from datetime import datetime, timezone
    from app.models import Vehicle
    from app.adapters.inventory.base import VehicleRecord
    from tools.sync_inventory import sync_inventory

    body = await request.json()
    slug = body.get("slug", "premier-auto")

    session = _get_session()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == slug)
        ).scalars().first()

        if not dealer:
            return {"error": f"Dealer '{slug}' not found"}

        # Build VehicleRecords from the demo CSV data
        demo_vehicles = [
            {"vin": "2HGFC2F50KH500001", "stock_no": "TDM001", "year": 2022, "make": "Honda", "model": "Civic", "trim": "Sport", "body": "Sedan", "mileage": 24500, "price": 24900},
            {"vin": "1FATP8UH1J5500002", "stock_no": "TDM002", "year": 2021, "make": "Ford", "model": "Mustang", "trim": "GT", "body": "Coupe", "mileage": 32000, "price": 35950},
            {"vin": "5TDZA23C13S500003", "stock_no": "TDM003", "year": 2023, "make": "Toyota", "model": "RAV4", "trim": "XLE", "body": "SUV", "mileage": 15800, "price": 34995},
            {"vin": "KMHD84LF5JU500004", "stock_no": "TDM004", "year": 2020, "make": "Hyundai", "model": "Elantra", "trim": "Preferred", "body": "Sedan", "mileage": 51000, "price": 16450},
            {"vin": "3VWDX7AJ5BM500005", "stock_no": "TDM005", "year": 2019, "make": "Volkswagen", "model": "Jetta", "trim": "Comfortline", "body": "Sedan", "mileage": 68000, "price": 15990},
            {"vin": "4T1BZ1HK5KU500006", "stock_no": "TDM006", "year": 2022, "make": "Toyota", "model": "Camry", "trim": "SE", "body": "Sedan", "mileage": 29000, "price": 27900},
            {"vin": "1N4AL3AP5KC500007", "stock_no": "TDM007", "year": 2021, "make": "Nissan", "model": "Altima", "trim": "SV", "body": "Sedan", "mileage": 42000, "price": 19850},
            {"vin": "2C3CDXCT5NH500008", "stock_no": "TDM008", "year": 2022, "make": "Dodge", "model": "Challenger", "trim": "RT", "body": "Coupe", "mileage": 21000, "price": 39900},
            {"vin": "5YJ3E1EA5KF500009", "stock_no": "TDM009", "year": 2021, "make": "Tesla", "model": "Model 3", "trim": "Standard Plus", "body": "Sedan", "mileage": 38000, "price": 31500},
            {"vin": "1G1YY2D58H500010", "stock_no": "TDM010", "year": 2020, "make": "Chevrolet", "model": "Camaro", "trim": "LT", "body": "Coupe", "mileage": 29000, "price": 28750},
            {"vin": "WBA8E9C59JA500011", "stock_no": "TDM011", "year": 2022, "make": "BMW", "model": "330i", "trim": "xDrive", "body": "Sedan", "mileage": 26000, "price": 38500},
            {"vin": "JHMCG2638AC500012", "stock_no": "TDM012", "year": 2023, "make": "Honda", "model": "CR-V", "trim": "EX-L", "body": "SUV", "mileage": 12000, "price": 36200},
            {"vin": "SALWR2WK5HA500013", "stock_no": "TDM013", "year": 2021, "make": "Range Rover", "model": "Evoque", "trim": "S", "body": "SUV", "mileage": 35000, "price": 42900},
            {"vin": "WDCTG4GB5JJ500014", "stock_no": "TDM014", "year": 2022, "make": "Mercedes-Benz", "model": "C300", "trim": "4MATIC", "body": "Sedan", "mileage": 22000, "price": 41500},
            {"vin": "5NPE34AF4HH500015", "stock_no": "TDM015", "year": 2023, "make": "Hyundai", "model": "Tucson", "trim": "Preferred", "body": "SUV", "mileage": 18000, "price": 29900},
            {"vin": "1FTFW1E8XKK500016", "stock_no": "TDM016", "year": 2021, "make": "Ford", "model": "F-150", "trim": "XLT", "body": "Truck", "mileage": 45000, "price": 38750},
            {"vin": "3MYU6YEC5MF500017", "stock_no": "TDM017", "year": 2023, "make": "Mazda", "model": "CX-5", "trim": "GX", "body": "SUV", "mileage": 14500, "price": 31200},
            {"vin": "2T3DFREV5GW500018", "stock_no": "TDM018", "year": 2020, "make": "Toyota", "model": "Corolla", "trim": "SE", "body": "Sedan", "mileage": 52000, "price": 17900},
            {"vin": "1GNSCJKC5MR500019", "stock_no": "TDM019", "year": 2022, "make": "Chevrolet", "model": "Equinox", "trim": "LT", "body": "SUV", "mileage": 31000, "price": 25800},
            {"vin": "WBAPH5C55BA500020", "stock_no": "TDM020", "year": 2019, "make": "Audi", "model": "A4", "trim": "Premium Plus", "body": "Sedan", "mileage": 58000, "price": 26500},
        ]

        # Build image URLs from placeholder
        records = []
        for v in demo_vehicles:
            img_text = f"{v['year']}+{v['make'].replace(' ', '+')}+{v['model'].replace(' ', '+')}"
            if v['trim']:
                img_text += f"+{v['trim'].replace(' ', '+')}"
            img_url = f"https://placehold.co/800x500/1a1a2e/e0e0e0?text={img_text}"
            records.append(VehicleRecord(
                vin=v["vin"],
                stock_no=v["stock_no"],
                year=v["year"],
                make=v["make"],
                model=v["model"],
                trim=v["trim"],
                body=v["body"],
                mileage=v["mileage"],
                price=v["price"],
                status="available",
                url=img_url,
                photos=[img_url],
                raw=v,
            ))

        result = sync_inventory(session, dealer, records)
        # Now apply enriched specs to raw column
        enriched_count = 0
        for stock_no, specs in _ENRICHED_SPECS.items():
            vehicle = session.execute(
                select(Vehicle).where(
                    Vehicle.dealer_id == dealer.id,
                    Vehicle.stock_no == stock_no,
                )
            ).scalars().first()
            if vehicle:
                vehicle.raw = specs
                enriched_count += 1
        session.commit()

        return {
            "status": "ok",
            "dealer": slug,
            "dealer_id": dealer.id,
            "specs_enriched": enriched_count,
            **result,
        }
    except Exception as exc:
        logger.exception("seed_vehicles error")
        session.rollback()
        return {"error": str(exc)}
    finally:
        session.close()


@router.post("/api/cleanup-test-leads")
async def cleanup_test_leads(request: Request, _auth: None = Depends(require_admin_auth)):
    """Delete test/placeholder leads (555 phone numbers) and their events.
    POST /admin/api/cleanup-test-leads  (JSON body: {"slug": "premier-auto"})
    Works in production — safe because 555 numbers are never real.
    """
    from app.models import Lead, LeadEvent, Message, Appointment, ConsentLog
    from sqlalchemy import delete as sa_delete

    body = await request.json()
    slug = body.get("slug", "premier-auto")

    session = _get_session()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == slug)
        ).scalars().first()

        if not dealer:
            return {"error": f"Dealer '{slug}' not found"}

        # Find leads with 555 in phone (test numbers)
        test_leads = session.execute(
            select(Lead).where(
                Lead.dealer_id == dealer.id,
                Lead.phone.like('%555%')
            )
        ).scalars().all()

        lead_ids = [l.id for l in test_leads]
        deleted_events = 0
        deleted_messages = 0
        deleted_appointments = 0
        deleted_consent = 0
        deleted_leads = len(lead_ids)

        if lead_ids:
            # Delete all child records first (FK constraints)
            r1 = session.execute(sa_delete(LeadEvent).where(LeadEvent.lead_id.in_(lead_ids)))
            deleted_events = r1.rowcount

            r2 = session.execute(sa_delete(Message).where(Message.lead_id.in_(lead_ids)))
            deleted_messages = r2.rowcount

            r3 = session.execute(sa_delete(Appointment).where(Appointment.lead_id.in_(lead_ids)))
            deleted_appointments = r3.rowcount

            r4 = session.execute(sa_delete(ConsentLog).where(ConsentLog.lead_id.in_(lead_ids)))
            deleted_consent = r4.rowcount

            # Now safe to delete leads
            session.execute(sa_delete(Lead).where(Lead.id.in_(lead_ids)))

        session.commit()
        return {
            "status": "ok",
            "dealer": slug,
            "leads_deleted": deleted_leads,
            "events_deleted": deleted_events,
            "messages_deleted": deleted_messages,
            "appointments_deleted": deleted_appointments,
            "consent_deleted": deleted_consent,
            "lead_names": [l.name for l in test_leads],
        }
    except Exception as exc:
        logger.exception("cleanup_test_leads error")
        session.rollback()
        return {"error": str(exc)}
    finally:
        session.close()


@router.post("/api/reset-all-data")
async def reset_all_data(request: Request, _auth: None = Depends(require_admin_auth)):
    """Delete ALL leads and related data for a dealer. Nuclear reset.

    POST /admin/api/reset-all-data  (JSON body: {"slug": "premier-auto"})
    Requires admin authentication.
    """
    from app.models import Lead, LeadEvent, Message, Appointment, ConsentLog
    from sqlalchemy import delete as sa_delete

    body = await request.json()
    slug = body.get("slug", "premier-auto")

    session = _get_session()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == slug)
        ).scalars().first()

        if not dealer:
            return {"error": f"Dealer '{slug}' not found"}

        did = dealer.id

        # Get all lead IDs for this dealer
        lead_ids = list(session.execute(
            select(Lead.id).where(Lead.dealer_id == did)
        ).scalars().all())

        deleted_events = 0
        deleted_messages = 0
        deleted_appointments = 0
        deleted_consent = 0
        deleted_leads = len(lead_ids)

        if lead_ids:
            # Delete all child records first (FK constraints)
            r1 = session.execute(sa_delete(LeadEvent).where(LeadEvent.lead_id.in_(lead_ids)))
            deleted_events = r1.rowcount

            r2 = session.execute(sa_delete(Message).where(Message.lead_id.in_(lead_ids)))
            deleted_messages = r2.rowcount

            r3 = session.execute(sa_delete(Appointment).where(Appointment.lead_id.in_(lead_ids)))
            deleted_appointments = r3.rowcount

            r4 = session.execute(sa_delete(ConsentLog).where(ConsentLog.lead_id.in_(lead_ids)))
            deleted_consent = r4.rowcount

            # Now safe to delete leads
            session.execute(sa_delete(Lead).where(Lead.id.in_(lead_ids)))

        # Reset round-robin pointer
        dealer.round_robin_pointer = 0
        session.commit()

        return {
            "status": "ok",
            "dealer": slug,
            "leads_deleted": deleted_leads,
            "events_deleted": deleted_events,
            "messages_deleted": deleted_messages,
            "appointments_deleted": deleted_appointments,
            "consent_deleted": deleted_consent,
        }
    except Exception as exc:
        logger.exception("reset_all_data error")
        session.rollback()
        return {"error": str(exc)}
    finally:
        session.close()


@router.post("/api/enrich-specs")
async def enrich_specs(request: Request, _auth: None = Depends(require_admin_auth)):
    """Update the raw column of existing vehicles with enriched spec data.

    POST /admin/api/enrich-specs  (JSON body: {"slug": "premier-auto"})
    Idempotent — safe to re-run. DISABLED in production.
    Requires admin authentication.
    """
    if settings.environment == "production":
        return {"error": "Seed endpoints are disabled in production"}

    body = await request.json()
    slug = body.get("slug", "premier-auto")

    session = _get_session()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == slug)
        ).scalars().first()

        if not dealer:
            return {"error": f"Dealer '{slug}' not found"}

        updated = 0
        skipped = []
        for stock_no, specs in _ENRICHED_SPECS.items():
            vehicle = session.execute(
                select(Vehicle).where(
                    Vehicle.dealer_id == dealer.id,
                    Vehicle.stock_no == stock_no,
                )
            ).scalars().first()
            if vehicle:
                vehicle.raw = specs
                updated += 1
            else:
                skipped.append(stock_no)

        session.commit()
        return {
            "status": "ok",
            "dealer": slug,
            "updated": updated,
            "skipped": skipped,
        }
    except Exception as exc:
        logger.exception("enrich_specs error")
        session.rollback()
        return {"error": str(exc)}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Platform Settings
# ---------------------------------------------------------------------------

@router.get("/settings")
async def admin_settings_page(request: Request, _auth: None = Depends(require_admin_auth)):
    """Global platform settings — info about the running instance."""
    session = _get_session()
    try:
        total_dealers = session.execute(select(func.count(Dealer.id))).scalar() or 0
        total_leads = session.execute(select(func.count(Lead.id))).scalar() or 0
        active_leads = session.execute(
            select(func.count(Lead.id)).where(
                Lead.state.notin_([LeadState.SOLD, LeadState.LOST, LeadState.OPTED_OUT])
            )
        ).scalar() or 0

        return templates.TemplateResponse(request=request, name="admin_settings.html", context={
            "request": request,
            "active_page": "settings",
            "total_dealers": total_dealers,
            "total_leads": total_leads,
            "active_leads": active_leads,
            "environment": settings.environment,
            "public_base_url": settings.public_base_url,
            "outbound_enabled": settings.outbound_enabled,
            "openrouter_model": settings.openrouter_model,
        })
    finally:
        session.close()
