"""Configuration: runtime Settings (env/secrets) + the per-dealer config schema.

The per-dealer config is the heart of the "drop-in" onboarding model: one validated YAML
file per dealership (`dealers/<slug>.yaml`) declares every behavior, including which adapter
to use on each of the three axes (intake / inventory / organization). Validating it with
Pydantic is what lets us onboard a new client without touching core code.

See `dealers/_schema.md` for human docs and `dealers/_example-dealer.yaml` for a filled example.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional
import re

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# --------------------------------------------------------------------------------------
# E.164 phone validator — guards against masked/corrupted dealer phone numbers
# --------------------------------------------------------------------------------------
_E164_PATTERN = re.compile(r"^\+\d{10,15}$")


def _validate_e164(v: str | None) -> str | None:
    """Validate optional phone is E.164 when present (+<digits>, 10-15 digits)."""
    if v is None or v == "":
        return v
    if not _E164_PATTERN.match(v):
        raise ValueError(
            f"Phone number {v!r} does not match E.164 format (+ followed by 10-15 digits). "
            "Expected example: +17787623122"
        )
    return v


# --------------------------------------------------------------------------------------
# Runtime settings (secrets / infra) — loaded from environment / .env. NEVER commit values.
# --------------------------------------------------------------------------------------
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://localhost/speedtolead"

    # Twilio — the backbone (SMS, WhatsApp, Voice/missed-call, Conversations for Messenger).
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""

    # OpenRouter — the conversation reasoning layer (OpenAI-compatible API).
    openrouter_api_key: str = ""
    # NOTE: Using DeepSeek V4 Flash — cheaper than Gemini 2.5 Flash and better
    # conversational quality per production testing.
    openrouter_model: str = "deepseek/deepseek-v4-flash"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Tool-calling model — used when the turn requires structured tool calls
    # (booking, availability, inventory). GPT-4o-mini via OpenRouter is cheap +
    # gold-standard reliable function calling. Swappable via env without code changes.
    tool_model: str = "openai/gpt-4o-mini"

    # DeepSeek direct API — used when DEEPSEEK_API_KEY is set (cheaper than OpenRouter)
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"

    # Public base URL of the always-on service (for Twilio/Meta webhooks).
    public_base_url: str = "http://localhost:8000"

    environment: str = "development"

    # Dashboard auth
    dashboard_user: str = "admin"
    dashboard_password: str = ""
    dashboard_password_hash: str = ""
    dashboard_secret: str = ""

    # Safety gates — outbound sending and signature validation are OFF by default.
    # Flip per-environment (staging first, then prod) after creds are verified.
    outbound_enabled: bool = False
    require_twilio_signature: bool = False
    message_tags_enabled: bool = False

    # Telegram — dealer-side notifications (the ONLY dealer channel per architecture decision)
    telegram_bot_token: str = ""

    # Email ingestion — IMAP inbox for listing site leads
    email_inbox_username: str = ""
    email_inbox_password: str = ""
    email_imap_server: str = "imap.gmail.com"
    email_imap_port: int = 993

    # Debug endpoints — disabled in production by default
    debug_endpoints_enabled: bool = False

    # Email transport — outbound follow-ups and rep replies
    sendgrid_api_key: str = ""
    email_from_address: str = ""
    email_from_name: str = ""

    # Quiet hours: when True, auto-reply SMS sends 24/7 (bypasses 21:00-08:00 window).
    # Set QUIET_HOURS_DISABLED=false in .env to re-enable for production.
    quiet_hours_disabled: bool = True


# --------------------------------------------------------------------------------------
# Per-dealer config schema (the YAML contract)
# --------------------------------------------------------------------------------------
class InventorySourceKind(str, Enum):
    AUTO = "auto"              # run the discovery probe and pick the best rung
    FEED = "feed"             # CSV/TSV/XML (Google Vehicle Ads / FB Catalog specs)
    DMS = "dms"               # known-platform feed/API with a prebuilt mapping
    STRUCTURED_DATA = "structured_data"  # schema.org JSON-LD / internal JSON API
    WEBSITE_SCRAPE = "website_scrape"    # LLM-assisted HTML scrape (fallback)
    MANUAL = "manual"         # CSV upload / dashboard entry (universal floor)
    NONE = "none"


class LeadOrgMode(str, Enum):
    NATIVE = "native"          # our dashboard IS the system of record (floor)
    CRM_SYNC = "crm_sync"      # push / 2-way into an external CRM/DMS
    SHEET = "sheet"            # Google Sheet
    WEBHOOK = "webhook"        # fire a webhook (Zapier/Make)
    EMAIL_DIGEST = "email_digest"


class RoutingStrategy(str, Enum):
    ROUND_ROBIN = "round_robin"
    BY_SOURCE = "by_source"
    SINGLE_POOL = "single_pool"


class Dealer(BaseModel):
    slug: str = Field(..., description="Tenant key, kebab-case, unique")
    name: str
    timezone: str = "America/Vancouver"
    hours: dict[str, str] = Field(
        default_factory=dict,
        description='Per-day open hours, e.g. {"mon": "09:00-18:00"}. Drives the AI-autonomy switch.',
    )
    location_address: Optional[str] = None
    maps_url: Optional[str] = None
    main_phone: Optional[str] = None
    website: Optional[str] = Field(None, description="Dealer website URL — shared with customers who ask")

    @field_validator("main_phone")
    @classmethod
    def _check_main_phone(cls, v: str | None) -> str | None:
        return _validate_e164(v)


class Channels(BaseModel):
    """AXIS 3 — channels the dealer uses to generate leads."""
    sms_number: Optional[str] = Field(None, description="Canadian Twilio number; lead-facing SMS")
    whatsapp_sender: Optional[str] = Field(None, description="Twilio WhatsApp sender; rep-facing")
    lead_email_inbox: Optional[str] = Field(None, description="Inbox that 3rd-party lead emails forward to")
    facebook_page_id: Optional[str] = None
    web_form_token: Optional[str] = Field(None, description="Identifies the dealer at /webhook/form/{token}")
    email_from_address: Optional[str] = Field(None, description="Outbound email From address — the dealer's own domain email, e.g. sales@premierautogroup.com")
    email_from_name: Optional[str] = Field(None, description="Display name for outbound emails, e.g. 'Premier Auto Group'")
    voice_number: Optional[str] = Field(None, description="Twilio number for voice/missed-call. Defaults to sms_number if unset.")
    call_detection: str = Field("always_on", description="Missed-call detection mode: always_on | time_based | voicemail_notify")
    ring_timeout_sec: int = Field(25, description="Seconds before Twilio considers a call unanswered. Suggested 20-30s.")

    @field_validator("sms_number", "whatsapp_sender", "voice_number")
    @classmethod
    def _check_channel_phone(cls, v: str | None) -> str | None:
        return _validate_e164(v)


class UnavailableWindow(BaseModel):
    """A time window when a rep is not available for appointments."""
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    start: str = Field(..., description="Start time in HH:MM format (24h)")
    end: str = Field(..., description="End time in HH:MM format (24h)")
    note: str = Field("", description="Optional reason for the unavailability")

    @field_validator("date")
    @classmethod
    def _check_date_format(cls, v: str) -> str:
        import re as _re
        if not _re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError(f"Date {v!r} does not match YYYY-MM-DD format")
        return v

    @field_validator("start", "end")
    @classmethod
    def _check_time_format(cls, v: str) -> str:
        import re as _re
        if not _re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError(f"Time {v!r} does not match HH:MM format")
        return v

    @field_validator("end")
    @classmethod
    def _check_end_after_start(cls, v: str, info) -> str:
        if "start" in info.data:
            start_hr, start_min = map(int, info.data["start"].split(":"))
            end_hr, end_min = map(int, v.split(":"))
            if (end_hr, end_min) <= (start_hr, start_min):
                raise ValueError(f"End time {v!r} must be after start time {info.data['start']!r}")
        return v


class SalesRep(BaseModel):
    name: str
    pin: str = Field("", description="4-digit PIN for dashboard login — each rep gets their own")
    phone: str = Field(..., description="Phone number for round-robin claim pings")
    active: bool = True
    notify_backend: str = Field(
        "telegram",
        description="How to ping this rep: telegram (default) | twilio_whatsapp | sms | email | dashboard",
    )
    notify_template_sid: Optional[str] = Field(
        None, description="Twilio approved-template SID for business-initiated rep pings"
    )
    telegram_chat_id: Optional[str] = Field(
        None, description="Telegram chat_id for telegram notify_backend"
    )
    unavailable_windows: list[UnavailableWindow] = Field(
        default_factory=list,
        description="Time windows when this rep is not available for appointments",
    )

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: str) -> str:
        return _validate_e164(v)


class Routing(BaseModel):
    strategy: RoutingStrategy = RoutingStrategy.ROUND_ROBIN
    claim_timeout_min: int = 5
    escalation: list[str] = Field(default_factory=lambda: ["reassign", "notify_manager"])
    manager_phone: Optional[str] = None
    digest_enabled: bool = False
    digest_time: str = "08:00"

    @field_validator("manager_phone")
    @classmethod
    def _check_manager_phone(cls, v: str | None) -> str | None:
        return _validate_e164(v)


class AIConfig(BaseModel):
    persona: str = "friendly, concise, no-pressure local sales rep"
    goal: str = "book_appointment"
    guardrails: dict[str, bool] = Field(
        default_factory=lambda: {"no_price_negotiation": True, "no_financing_promises": True}
    )
    business_facts: str = Field(
        "",
        description="Per-dealer facts the AI can state verbatim (fees, inspection reports, "
        "sub-prime credit, trade-ins, warranty). If a fact is NOT listed here, the AI must "
        "defer ('let me check with the team'). Empty = no extra facts.",
    )


class Followups(BaseModel):
    cadence_min: list[int] = Field(
        default_factory=lambda: [60, 1440, 4320, 10080],
        description="Minutes after going cold to send each follow-up (1h, 1d, 3d, 7d).",
    )


class Inventory(BaseModel):
    """AXIS 1 — how the dealer maintains their website / lists cars."""
    source: InventorySourceKind = InventorySourceKind.AUTO
    url: Optional[str] = Field(None, description="Website / feed / API URL (probed if source=auto)")
    platform: str = Field("", description="Optional hint: dealerpull | dealercenter | autosync | ...")
    refresh_min: int = 180
    field_map: str | dict[str, str] = Field("auto", description="'auto' or explicit column overrides")


class LeadOrg(BaseModel):
    """AXIS 2 — how the dealer organizes / tracks their leads (system of record)."""
    mode: LeadOrgMode = LeadOrgMode.NATIVE
    target: str = Field("", description="CRM/DMS name, Google Sheet ID, or webhook URL (per mode)")
    credentials_ref: str = Field("", description="Name of the secret in .env/host vault; never inline")


class Compliance(BaseModel):
    region: str = "CA-BC"
    consent_text: str = (
        "By submitting you agree to receive texts from {dealer.name}. Reply STOP to opt out."
    )
    opt_out_keywords: list[str] = Field(
        default_factory=lambda: ["STOP", "STOPALL", "UNSUBSCRIBE", "ARRET"]
    )
    quiet_hours: str = Field("21:00-08:00", description="No outbound sends during this window (dealer tz)")
    reply_during_quiet_hours_if_customer_initiated: bool = Field(
        True,
        description=(
            "If the customer texts in during quiet hours, reply right away anyway "
            "(default). If false, the AI's reply waits and sends after quiet hours end."
        ),
    )


class DealerConfig(BaseModel):
    """Root per-dealer config. One file = one live tenant."""
    dealer: Dealer
    channels: Channels = Field(default_factory=Channels)
    # PIN for manager login (rep picks "Manager" from the dropdown + enters this).
    # Without this field the YAML's manager_pin was dropped on load, so managers
    # could not sign in to the dashboard at all.
    manager_pin: str = ""
    sales_team: list[SalesRep] = Field(default_factory=list)
    routing: Routing = Field(default_factory=Routing)
    ai: AIConfig = Field(default_factory=AIConfig)
    followups: Followups = Field(default_factory=Followups)
    inventory: Inventory = Field(default_factory=Inventory)
    lead_org: LeadOrg = Field(default_factory=LeadOrg)
    compliance: Compliance = Field(default_factory=Compliance)

    @field_validator("sales_team")
    @classmethod
    def _at_least_consider_team(cls, v: list[SalesRep]) -> list[SalesRep]:
        # Empty team is allowed (AI-only / after-hours), but warn loudly elsewhere at provision time.
        return v


def load_dealer_config(path: str | Path) -> DealerConfig:
    """Load + validate a dealer YAML into a DealerConfig. Raises pydantic.ValidationError on bad input."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return DealerConfig.model_validate(data)


settings = Settings()
