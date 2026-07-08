"""Tool / CLI: the drop-in onboarding entrypoint.

    python tools/provision_dealer.py dealers/<slug>.yaml

Steps:
  1. Load + validate the YAML (DealerConfig). Bad config fails loudly here.
  2. Run a discovery probe per axis (inventory source; confirm channels; lead_org reachability).
  3. Upsert the tenant (Dealer row, config persisted as JSON, indexed columns populated).
  4. Link Twilio numbers / Conversations; verify WhatsApp templates exist.
  5. Run the first inventory sync and print a preview ("found N vehicles — confirm?").

No code changes per dealer — everything is config.
"""

from __future__ import annotations

import json
import logging
import sys

from sqlalchemy import select

from app.config import load_dealer_config

logger = logging.getLogger("speed-to-lead.provision")


def provision(config_path: str, *, confirm: bool = False) -> dict:
    """Validate + onboard a dealer from a YAML path. Returns an onboarding summary."""
    cfg = load_dealer_config(config_path)  # raises on invalid config

    # Normalize the indexed lookup columns
    sms_number = (cfg.channels.sms_number or "").replace(" ", "").replace("-", "")
    whatsapp_sender = (cfg.channels.whatsapp_sender or "").replace(" ", "").replace("-", "")
    web_form_token = cfg.channels.web_form_token or None

    from app.db import get_session_factory
    from app.models import Dealer

    session = get_session_factory()()
    try:
        # Upsert: find by slug or create new
        existing = session.execute(
            select(Dealer).where(Dealer.slug == cfg.dealer.slug)
        ).scalars().first()

        if existing:
            existing.name = cfg.dealer.name
            existing.timezone = cfg.dealer.timezone
            existing.sms_number = sms_number or None
            existing.whatsapp_sender = whatsapp_sender or None
            existing.web_form_token = web_form_token
            existing.config = json.loads(cfg.model_dump_json())
            dealer = existing
        else:
            dealer = Dealer(
                slug=cfg.dealer.slug,
                name=cfg.dealer.name,
                timezone=cfg.dealer.timezone,
                sms_number=sms_number or None,
                whatsapp_sender=whatsapp_sender or None,
                web_form_token=web_form_token,
                config=json.loads(cfg.model_dump_json()),
            )
            session.add(dealer)

        session.commit()
        session.refresh(dealer)

        logger.info("Dealer %s provisioned (id=%s, sms=%s, wa=%s, token=%s)",
                     dealer.slug, dealer.id, dealer.sms_number,
                     dealer.whatsapp_sender, dealer.web_form_token)

        # TODO: discovery per axis; link Twilio; first sync + preview
        return {
            "slug": dealer.slug,
            "dealer_id": dealer.id,
            "validated": True,
            "sms_number": dealer.sms_number,
            "whatsapp_sender": dealer.whatsapp_sender,
            "web_form_token": dealer.web_form_token,
        }
    finally:
        session.close()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    summary = provision(argv[1])
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))