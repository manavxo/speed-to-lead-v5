"""APScheduler worker — fires escalation + follow-up timers + inventory sync in the cloud, 24/7.

Jobs are persisted in Postgres (SQLAlchemy jobstore) so nothing is lost on restart and no Redis
is needed. Runs as its own process alongside the web process (same container/codebase).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from app.config import settings

logger = logging.getLogger("speed-to-lead.scheduler")


def _on_job_event(event):
    """Log job execution results."""
    if event.exception:
        logger.error("Job %s raised: %s", event.job_id, event.exception)
    else:
        logger.info("Job %s completed", event.job_id)


# ---------------------------------------------------------------------------
# Escalation sweep (replaces the old per-lead schedule_escalation / _handle_escalation).
# Runs every 1 min, finds ASSIGNED leads past their dealer's claim_timeout_min,
# and calls on_claim_timeout.  Restart-safe, scalable, no schema column needed —
# derives the assignment time from the LeadEvent stream.
# ---------------------------------------------------------------------------

def _run_escalation_sweep_session(session) -> None:
    """Business logic for the escalation sweep. Takes a session for testability.

    Sweep all dealers for ASSIGNED leads past claim_timeout_min and escalate them.
    """
    from app.models import Dealer, Lead, LeadEvent, LeadState
    from sqlalchemy import select, func

    dealers = session.execute(select(Dealer)).scalars().all()
    now = datetime.now(timezone.utc)

    for dealer in dealers:
        dealer_config = dealer.config or {}
        timeout_min = dealer_config.get("routing", {}).get("claim_timeout_min", 5)
        cutoff = now - timedelta(minutes=timeout_min)

        # Find leads that are ASSIGNED and whose most recent ASSIGNED event is older than cutoff
        assigned_leads = session.execute(
            select(Lead).where(
                Lead.dealer_id == dealer.id,
                Lead.state == LeadState.ASSIGNED,
            )
        ).scalars().all()

        for lead in assigned_leads:
            # Find the most recent "to=ASSIGNED" LeadEvent for this lead
            latest_assigned_event = session.execute(
                select(LeadEvent).where(
                    LeadEvent.lead_id == lead.id,
                    LeadEvent.type == "state_change",
                ).order_by(LeadEvent.created_at.desc())
            ).scalars().first()

            if latest_assigned_event is None:
                continue

            event_time = latest_assigned_event.created_at
            # Ensure timezone-aware comparison
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)

            if event_time < cutoff:
                payload = latest_assigned_event.payload or {}
                if payload.get("to") == "ASSIGNED":
                    sales_team = dealer_config.get("sales_team", [])
                    sms_number = dealer_config.get("channels", {}).get("sms_number")
                    try:
                        from app.engine.escalation import on_claim_timeout
                        on_claim_timeout(
                            session, lead.id, dealer, sales_team,
                            sms_number=sms_number,
                        )
                        logger.info(
                            "Escalation sweep: lead#%s escalated (assigned %d min ago)",
                            lead.id, (now - event_time).total_seconds() / 60,
                        )
                    except Exception:
                        logger.exception("Escalation failed for lead#%s", lead.id)


def _run_escalation_sweep():
    """Cron entry point: creates a session, delegates to _run_escalation_sweep_session."""
    from app.db import get_session_factory
    logger.info("Running escalation sweep")
    session = get_session_factory()()
    try:
        _run_escalation_sweep_session(session)
    except Exception:
        logger.exception("Escalation sweep failed")
    finally:
        session.close()


def schedule_followup(scheduler, lead_id: int, dealer_slug: str, minutes: int):
    """Schedule a follow-up message for a cold lead."""
    job_id = f"followup-{lead_id}-{minutes}"
    scheduler.add_job(
        _handle_followup,
        "date",
        run_date=datetime.now(timezone.utc) + timedelta(minutes=minutes),
        args=[lead_id, dealer_slug, minutes],
        id=job_id,
        replace_existing=True,
        misfire_grace_time=120,
    )


def _handle_followup_session(session, lead_id: int, dealer_slug: str, minutes: int):
    """Business logic for the follow-up job. Takes a session for testability.

    Loads the lead, checks it's still active, then sends a follow-up message
    via the conversation engine (which uses the AI to generate context-aware text).
    """
    from app.models import Lead, LeadState, Dealer, Message, Direction, Channel
    from sqlalchemy import select

    logger.info("Follow-up for lead %s (%d min)", lead_id, minutes)
    lead = session.execute(select(Lead).where(Lead.id == lead_id)).scalar()
    if lead is None:
        logger.warning("Follow-up: lead %s not found", lead_id)
        return

    if lead.state in (LeadState.SOLD, LeadState.LOST, LeadState.OPTED_OUT):
        logger.info("Follow-up: lead %s in terminal state %s — skipping", lead_id, lead.state)
        return

    # Load dealer config
    dealer = session.execute(select(Dealer).where(Dealer.slug == dealer_slug)).scalar()
    if dealer is None:
        logger.warning("Follow-up: dealer %s not found", dealer_slug)
        return

    dealer_config = dealer.config or {}

    # Generate a follow-up message via the conversation engine
    followup_prompt = f"Following up after {minutes} minutes of no response. Be friendly and brief."
    try:
        from app.engine.conversation import handle_turn
        result = handle_turn(
            session, lead, followup_prompt,
            dealer_config=dealer_config,
        )
        text = result.get("text", "Just checking in — let us know if you have any questions!")
    except Exception:
        logger.exception("Follow-up AI generation failed for lead %s", lead_id)
        text = "Just checking in — let us know if you have any questions!"

    # Store the follow-up message in the Message table (no footer — first msg already has it)
    outbound_msg = Message(
        lead_id=lead.id,
        direction=Direction.OUTBOUND,
        channel=lead.source or Channel.SMS,
        body=text,
        ai_generated=True,
    )
    session.add(outbound_msg)

    # Send via Twilio
    try:
        from tools.send_sms import send_sms
        sms_number = dealer_config.get("channels", {}).get("sms_number")
        if lead.phone:
            send_sms(
                session=session,
                to=lead.phone,
                body=text,
                from_number=sms_number or "",
                lead=lead,
                role="AI",
                fake_twilio=None,
                force_send=True,
            )
            logger.info("Follow-up sent to lead %s", lead_id)
    except Exception:
        logger.exception("Follow-up send failed for lead %s", lead_id)

    session.commit()


def _handle_followup(lead_id: int, dealer_slug: str, minutes: int):
    """Cron entry point: creates a session, delegates to _handle_followup_session.

    Production code calls this — it manages session lifecycle. Tests should
    call _handle_followup_session directly with their own session.
    """
    from app.db import get_session_factory
    session = get_session_factory()()
    try:
        _handle_followup_session(session, lead_id, dealer_slug, minutes)
    except Exception:
        logger.exception("Follow-up failed for lead %s", lead_id)
    finally:
        session.close()


def _run_inventory_sync_session(session) -> None:
    """Business logic for the inventory sync job. Takes a session for testability."""
    from app.models import Dealer
    from sqlalchemy import select

    dealers = session.execute(select(Dealer)).scalars().all()
    for dealer in dealers:
        config = dealer.config or {}
        refresh_min = config.get("inventory", {}).get("refresh_min", 180)
        try:
            from tools.sync_inventory import sync_inventory
            sync_inventory(session, dealer)
            logger.info("Inventory synced for %s (refresh_min=%d)", dealer.slug, refresh_min)
        except Exception:
            logger.exception("Inventory sync failed for %s", dealer.slug)


def _run_inventory_sync():
    """Cron entry point: creates a session, delegates to _run_inventory_sync_session."""
    from app.db import get_session_factory
    logger.info("Running scheduled inventory sync")
    session = get_session_factory()()
    try:
        _run_inventory_sync_session(session)
    finally:
        session.close()


def _run_org_sink_flush_session(session) -> None:
    """Business logic for the org sink flush job. Takes a session for testability."""
    from app.models import Dealer
    from sqlalchemy import select

    dealers = session.execute(select(Dealer)).scalars().all()
    for dealer in dealers:
        config = dealer.config or {}
        mode = config.get("lead_org", {}).get("mode", "native")
        if mode == "native":
            continue
        try:
            from tools.sync_crm import flush_events
            flush_events(session, dealer)
            logger.info("Org sink flushed for %s", dealer.slug)
        except Exception:
            logger.exception("Org sink flush failed for %s", dealer.slug)


def _run_org_sink_flush():
    """Cron entry point: creates a session, delegates to _run_org_sink_flush_session."""
    from app.db import get_session_factory
    logger.info("Running org sink flush")
    session = get_session_factory()()
    try:
        _run_org_sink_flush_session(session)
    finally:
        session.close()


def _run_stuck_lead_sweep_session(session) -> None:
    """Business logic for the stuck-lead sweep. Takes a session for testability."""
    from app.models import Dealer, Lead, LeadState
    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    dealers = session.execute(select(Dealer)).scalars().all()
    for dealer in dealers:
        config = dealer.config or {}
        timeout_min = config.get("routing", {}).get("claim_timeout_min", 5)
        new_threshold = now - timedelta(minutes=5)
        assigned_threshold = now - timedelta(minutes=timeout_min * 2)

        # Leads stuck in NEW for >5 min
        stuck_new = session.execute(
            select(Lead).where(
                Lead.dealer_id == dealer.id,
                Lead.state == LeadState.NEW,
                Lead.created_at < new_threshold,
            )
        ).scalars().all()
        for lead in stuck_new:
            created_at = lead.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            logger.warning("STUCK lead#%s in NEW for %d min (dealer=%s)",
                           lead.id, (now - created_at).total_seconds() / 60, dealer.slug)

        # Leads stuck in ASSIGNED for >2x timeout
        stuck_assigned = session.execute(
            select(Lead).where(
                Lead.dealer_id == dealer.id,
                Lead.state == LeadState.ASSIGNED,
                Lead.updated_at < assigned_threshold,
            )
        ).scalars().all()
        for lead in stuck_assigned:
            updated_at = lead.updated_at
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            logger.warning("STUCK lead#%s in ASSIGNED for %d min (dealer=%s)",
                           lead.id, (now - updated_at).total_seconds() / 60, dealer.slug)


def _run_stuck_lead_sweep():
    """Cron entry point: creates a session, delegates to _run_stuck_lead_sweep_session."""
    from app.db import get_session_factory
    logger.info("Running stuck-lead sweep")
    session = get_session_factory()()
    try:
        _run_stuck_lead_sweep_session(session)
    except Exception:
        logger.exception("Stuck-lead sweep failed")
    finally:
        session.close()



def _run_daily_digest_for_all_dealers_session(session) -> None:
    """Business logic for the daily digest job. Takes a session for testability."""
    from app.models import Dealer
    from sqlalchemy import select

    now_utc = datetime.now(timezone.utc)
    dealers = session.execute(select(Dealer)).scalars().all()
    for dealer in dealers:
        config = dealer.config or {}
        routing = config.get("routing", {})
        if not routing.get("digest_enabled", False):
            continue

        # Check if current dealer-local time matches digest_time
        digest_time = routing.get("digest_time", "08:00")
        tz_name = config.get("dealer", {}).get("timezone", "America/Vancouver")
        try:
            from zoneinfo import ZoneInfo
            now_local = now_utc.astimezone(ZoneInfo(tz_name))
        except Exception:
            now_local = now_utc

        try:
            digest_h, digest_m = map(int, digest_time.split(":"))
        except (ValueError, AttributeError):
            digest_h, digest_m = 8, 0

        # Only fire if we're within the target hour
        if now_local.hour == digest_h:
            try:
                send_daily_digest(session, dealer.slug, config)
            except Exception:
                logger.exception("Daily digest failed for %s", dealer.slug)


def _run_daily_digest_for_all_dealers():
    """Cron entry point: creates a session, delegates to _run_daily_digest_for_all_dealers_session."""
    from app.db import get_session_factory
    logger.info("Checking daily digests for all dealers")
    session = get_session_factory()()
    try:
        _run_daily_digest_for_all_dealers_session(session)
    finally:
        session.close()


def send_daily_digest(session, dealer_slug: str, dealer_config: dict = None):
    """Send a daily SMS digest of lead activity to the manager.

    Queries yesterday's leads, builds a summary, and sends via the
    existing send_sms chokepoint.
    """
    from sqlalchemy import select, func as sa_func
    from app.models import Dealer, Lead, LeadEvent, LeadState, Message, Direction

    if dealer_config is None:
        return

    routing = dealer_config.get("routing", {})
    manager_phone = routing.get("manager_phone")
    if not manager_phone:
        logger.info("No manager_phone for %s — skipping digest", dealer_slug)
        return

    # Load the Dealer object so dealer.id is available (fix: was previously undefined)
    dealer = session.execute(
        select(Dealer).where(Dealer.slug == dealer_slug)
    ).scalars().first()
    if dealer is None:
        logger.warning("No dealer found for slug %s — skipping digest", dealer_slug)
        return

    # Calculate yesterday in dealer timezone
    tz_name = dealer_config.get("dealer", {}).get("timezone", "America/Vancouver")
    try:
        from zoneinfo import ZoneInfo
        now_local = datetime.now(timezone.utc).astimezone(ZoneInfo(tz_name))
    except Exception:
        now_local = datetime.now(timezone.utc)

    yesterday_start_local = (now_local - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    yesterday_end_local = yesterday_start_local + timedelta(days=1)

    # Convert to UTC for DB queries
    yesterday_start_utc = yesterday_start_local.astimezone(timezone.utc)
    yesterday_end_utc = yesterday_end_local.astimezone(timezone.utc)

    # Query leads created yesterday
    leads = session.execute(
        select(Lead).where(
            Lead.created_at >= yesterday_start_utc,
            Lead.created_at < yesterday_end_utc,
            Lead.dealer_id == dealer.id,
        )
    ).scalars().all()

    total_new = len(leads)
    if total_new == 0:
        logger.info("No new leads yesterday for %s — skipping digest", dealer_slug)
        return

    # Count by state
    state_counts = {}
    for state in LeadState:
        state_counts[state.value] = 0
    for lead in leads:
        state_counts[lead.state.value] = state_counts.get(lead.state.value, 0) + 1

    # Calculate average response time
    avg_response_seconds = 0
    response_times = []
    for lead in leads:
        first_in = session.execute(
            select(Message.created_at).where(
                Message.lead_id == lead.id,
                Message.direction == Direction.INBOUND,
            ).order_by(Message.created_at.asc()).limit(1)
        ).scalars().first()
        first_out = session.execute(
            select(Message.created_at).where(
                Message.lead_id == lead.id,
                Message.direction == Direction.OUTBOUND,
            ).order_by(Message.created_at.asc()).limit(1)
        ).scalars().first()
        if first_in and first_out:
            delta = (first_out - first_in).total_seconds()
            if delta >= 0:
                response_times.append(delta)
    if response_times:
        avg_response_seconds = sum(response_times) / len(response_times)

    # Top performing rep by engagement count
    rep_engaged = {}
    for lead in leads:
        if lead.assigned_rep and lead.state in (
            LeadState.ENGAGED, LeadState.APPT_SET, LeadState.SHOWED, LeadState.SOLD
        ):
            rep_engaged[lead.assigned_rep] = rep_engaged.get(lead.assigned_rep, 0) + 1
    top_rep = ""
    top_rep_count = 0
    if rep_engaged:
        top_rep = max(rep_engaged, key=rep_engaged.get)
        top_rep_count = rep_engaged[top_rep]

    # Count appointments
    appt_count = state_counts.get("APPT_SET", 0) + state_counts.get("SHOWED", 0) + state_counts.get("SOLD", 0)

    # Format response time
    if avg_response_seconds < 60:
        resp_display = f"{int(avg_response_seconds)}s"
    elif avg_response_seconds < 3600:
        resp_display = f"{int(avg_response_seconds // 60)}m {int(avg_response_seconds % 60)}s"
    else:
        resp_display = f"{int(avg_response_seconds // 3600)}h"

    # Build summary parts
    dealer_name = dealer_config.get("dealer", {}).get("name", dealer_slug)
    parts = [f"Good morning! Yesterday at {dealer_name}: {total_new} new leads"]

    # Add state breakdown (only non-zero)
    state_parts = []
    state_labels = {
        "AUTO_REPLIED": "auto-replied",
        "ASSIGNED": "assigned",
        "CLAIMED": "claimed",
        "ENGAGED": "engaged",
        "APPT_SET": "appt set",
        "SHOWED": "showed",
        "SOLD": "sold",
        "LOST": "lost",
    }
    for state_key, label in state_labels.items():
        count = state_counts.get(state_key, 0)
        if count > 0:
            state_parts.append(f"{count} {label}")
    if state_parts:
        parts[0] += ", " + ", ".join(state_parts)
    parts[0] += "."

    # Response time
    if response_times:
        parts.append(f"Avg response: {resp_display}.")

    # Top rep
    if top_rep:
        parts.append(f"Top rep: {top_rep} ({top_rep_count} engaged).")

    # Appointments
    if appt_count > 0:
        parts.append(f"{appt_count} appt{'s' if appt_count != 1 else ''} set.")

    # Dashboard URL
    from app.config import settings
    dashboard_url = f"{settings.public_base_url}/dashboard"
    parts.append(f"Login for details: {dashboard_url}")

    body = " ".join(parts)

    # Send via send_sms chokepoint
    sms_number = dealer_config.get("channels", {}).get("sms_number", "")
    try:
        from tools.send_sms import send_sms as _send_sms
        _send_sms(
            session,
            to=manager_phone,
            body=body,
            from_number=sms_number,
            dealer_slug=dealer_slug,
            dealer_config=dealer_config,
            force_send=True,
        )
        logger.info("Daily digest sent for %s to %s", dealer_slug, manager_phone)
    except Exception:
        logger.exception("Failed to send daily digest for %s", dealer_slug)


def _run_morning_followup_session(session, now: datetime | None = None) -> None:
    """Send first-touch messages that were queued overnight, now that the dealer is open.

    Leads that arrive after hours don't get texted at night (quiet hours). Instead
    they carry a 'morning_queue' LeadEvent holding the intended message body. As soon
    as the dealer is back inside business hours, we send that body and write a
    'morning_sent' event so the same lead is never messaged twice.

    Takes a session (and optional fixed `now`) for testability.
    """
    from app.models import Dealer, Lead, LeadEvent, LeadState
    from tools.send_sms import _is_quiet_hours
    from sqlalchemy import select

    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)  # don't resurrect leads older than a day
    dealers = session.execute(select(Dealer)).scalars().all()

    for dealer in dealers:
        config = dealer.config or {}
        # Release the queue as soon as quiet hours END (e.g. 08:00), NOT when the
        # showroom opens. Keying off business hours would strand a Saturday-night
        # lead all through a closed Sunday until it ages past the 24h cutoff and is
        # lost. Quiet-hours-end always fires within ~11h of queueing, so the lead
        # is sent first thing in the morning even on a day the lot is closed.
        if _is_quiet_hours(config, now):
            continue  # still quiet hours — leave the queue alone

        queued = session.execute(
            select(LeadEvent).where(
                LeadEvent.dealer_id == dealer.id,
                LeadEvent.type == "morning_queue",
                LeadEvent.created_at >= cutoff,
            ).order_by(LeadEvent.created_at.asc())
        ).scalars().all()

        for ev in queued:
            lead = session.get(Lead, ev.lead_id)
            if lead is None or not lead.phone:
                continue
            if lead.state in (LeadState.SOLD, LeadState.LOST, LeadState.OPTED_OUT):
                continue

            # Idempotency: skip anything we've already flushed.
            already_sent = session.execute(
                select(LeadEvent).where(
                    LeadEvent.lead_id == lead.id,
                    LeadEvent.type == "morning_sent",
                )
            ).scalars().first()
            if already_sent:
                continue

            body = (ev.payload or {}).get("body", "")
            if not body:
                continue

            sms_number = config.get("channels", {}).get("sms_number", "")
            try:
                from tools.send_sms import send_sms
                # Business hours now, so send_sms will NOT suppress for quiet hours.
                sid = send_sms(
                    session,
                    to=lead.phone,
                    body=body,
                    from_number=sms_number,
                    dealer_slug=dealer.slug,
                    dealer_config=config,
                    lead=lead,
                )
                # Mark sent even if send_sms suppressed (e.g. opted out) — that's a
                # terminal outcome, not something to retry every 15 minutes.
                session.add(LeadEvent(
                    lead_id=lead.id, dealer_id=dealer.id, type="morning_sent",
                    payload={"sid": sid}, synced=False,
                ))
                session.commit()
                logger.info("Morning first-touch sent for lead#%s (sid=%s)", lead.id, sid)
            except Exception:
                logger.exception("Morning first-touch failed for lead#%s", lead.id)
                session.rollback()


def _run_morning_followup():
    """Cron entry point: creates a session, delegates to _run_morning_followup_session."""
    from app.db import get_session_factory
    logger.info("Running morning follow-up sweep")
    session = get_session_factory()()
    try:
        _run_morning_followup_session(session)
    except Exception:
        logger.exception("Morning follow-up sweep failed")
    finally:
        session.close()


def register_jobs(scheduler) -> None:
    """Register all background jobs on the given scheduler instance.

    Used by the FastAPI lifespan to run jobs in-process instead of a
    separate ``python -m app.scheduler`` process.
    """
    scheduler.add_job(
        _run_escalation_sweep,
        "interval",
        minutes=1,
        id="escalation-sweep",
        replace_existing=True,
        misfire_grace_time=120,
    )
    scheduler.add_job(
        _run_inventory_sync,
        "interval",
        minutes=180,
        id="inventory-sync",
        replace_existing=True,
        misfire_grace_time=600,
    )
    scheduler.add_job(
        _run_org_sink_flush,
        "interval",
        minutes=5,
        id="org-sink-flush",
        replace_existing=True,
        misfire_grace_time=120,
    )
    scheduler.add_job(
        _run_stuck_lead_sweep,
        "interval",
        minutes=5,
        id="stuck-lead-sweep",
        replace_existing=True,
        misfire_grace_time=120,
    )
    # Daily digest runs every hour to check if any dealer's digest_time matches.
    # Uses dealer-local timezone comparison so different dealers get their digest
    # at the right wall-clock time regardless of server timezone.
    scheduler.add_job(
        _run_daily_digest_for_all_dealers,
        "cron",
        hour="*",
        minute=0,
        id="daily-digest",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # Email intake polling — check for new listing site leads every 5 minutes
    scheduler.add_job(
        _run_email_poll_for_all_dealers,
        "interval",
        minutes=5,
        id="email-poll",
        replace_existing=True,
        misfire_grace_time=120,
    )

    # Morning follow-up — flush after-hours leads queued overnight once the dealer
    # reopens. Every 15 min so the first message lands shortly after opening time.
    scheduler.add_job(
        _run_morning_followup,
        "interval",
        minutes=15,
        id="morning-followup",
        replace_existing=True,
        misfire_grace_time=600,
    )


def _run_email_poll_for_all_dealers():
    """Cron entry point: poll IMAP inbox for each dealer and create leads."""
    from app.db import get_session_factory
    from app.models import Dealer
    from sqlalchemy import select

    logger.info("Checking email inboxes for all dealers")
    session = get_session_factory()()
    try:
        from app.adapters.intake.email_ingest import poll_inbox
        dealers = session.execute(select(Dealer)).scalars().all()
        for dealer in dealers:
            try:
                count = poll_inbox(session, dealer)
                if count > 0:
                    logger.info("Email poll for %s: %d new leads", dealer.slug, count)
            except Exception:
                logger.exception("Email poll failed for dealer %s", dealer.slug)
    finally:
        session.close()


def build_scheduler() -> BlockingScheduler:
    """Build and configure the APScheduler instance with a Postgres jobstore."""
    from app.db import _normalize_db_url
    db_url = _normalize_db_url(settings.database_url)
    jobstores = {
        "default": SQLAlchemyJobStore(url=db_url),
    }
    scheduler = BlockingScheduler(jobstores=jobstores)
    scheduler.add_listener(_on_job_event, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)
    register_jobs(scheduler)
    return scheduler


def main() -> None:
    """Entry point for the standalone scheduler process."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    logger.info("Starting scheduler")
    build_scheduler().start()


if __name__ == "__main__":
    main()
