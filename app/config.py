"""Configuration: runtime Settings (env/secrets) + the per-dealer config schema.

The per-dealer config is the heart of the "drop-in" onboarding model: one validated YAML
file per dealership (`dealers/<slug>.yaml`) declares every behavior, including which adapter
to use on each of the three axes (intake / inventory / organization). Validating it with
Pydantic is what lets us onboard a new client without touching core code.

See `dealers/_schema.md` for human docs and `dealers/example-dealer.yaml` for a filled example.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    # NOTE: google/gemini-2.0-flash-001 was retired from OpenRouter (no 2.0 flash
    # variants remain). gemini-2.5-flash is the tool-capable successor, same price tier.
    openrouter_model: str = "google/gemini-2.5-flash"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

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
        description='Per-day open hours, e.g. {"mon": "09:00-19:00"}. Drives the AI-autonomy switch.',
    )
    location_address: Optional[str] = None
    maps_url: Optional[str] = None
    main_phone: Optional[str] = None


class Channels(BaseModel):
    """AXIS 3 — channels the dealer uses to generate leads."""
    sms_number: Optional[str] = Field(None, description="Canadian Twilio number; lead-facing SMS")
    whatsapp_sender: Optional[str] = Field(None, description="Twilio WhatsApp sender; rep-facing")
    lead_email_inbox: Optional[str] = Field(None, description="Inbox that 3rd-party lead emails forward to")
    facebook_page_id: Optional[str] = None
    web_form_token: Optional[str] = Field(None, description="Identifies the dealer at /webhook/form/{token}")


class SalesRep(BaseModel):
    name: str
    phone: str = Field(..., description="Phone number for round-robin claim pings")
    active: bool = True
    notify_backend: str = Field(
        "twilio_whatsapp",
        description="How to ping this rep: twilio_whatsapp (default) | sms | email | dashboard",
    )
    notify_template_sid: Optional[str] = Field(
        None, description="Twilio approved-template SID for business-initiated rep pings"
    )


class Routing(BaseModel):
    strategy: RoutingStrategy = RoutingStrategy.ROUND_ROBIN
    claim_timeout_min: int = 5
    escalation: list[str] = Field(default_factory=lambda: ["reassign", "notify_manager"])
    manager_phone: Optional[str] = None
    digest_enabled: bool = False
    digest_time: str = "08:00"


class AIConfig(BaseModel):
    persona: str = "friendly, concise, no-pressure local sales rep"
    goal: str = "book_appointment"
    guardrails: dict[str, bool] = Field(
        default_factory=lambda: {"no_price_negotiation": True, "no_financing_promises": True}
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


class DealerConfig(BaseModel):
    """Root per-dealer config. One file = one live tenant."""
    dealer: Dealer
    channels: Channels = Field(default_factory=Channels)
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
