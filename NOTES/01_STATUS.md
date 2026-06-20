# Project Status (Start of Refactoring — June 20, 2026)

## Where we are

Just before Phase 0.1. Full test suite passes (128 passed, 1 skipped). Codebase is on GitHub (origin/main, commit c4ca0ff).

## What works

- Webform → auto-reply → AI proactive follow-up → ENGAGED state
- SMS/WhatsApp inbound → AI conversation → appointment booking
- STOP/START opt-out (CASL compliant)
- Phone normalization
- Cross-day dedup (same phone + same dealer = one lead)
- DRYRUN dedup fix (stale DRYRUN leads re-send correctly)
- Phone masking fix (stored unmasked, masked at display time)
- PostgreSQL on Render
- Async webhook processing (no Twilio timeout)
- notify_rep chokepoint (all dealer notifications centralized)
- Manager escalation after 3 passes
- Dashboard with leaderboard, analytics, attention widgets
- Admin panel with onboarding wizard
- Debug endpoints for troubleshooting
- CORS for Vercel dealership site
- 128 passing tests

## What's broken (known bugs to fix in Phase 1)

| Bug | Severity | File |
|-----|----------|------|
| Daily digest crashes — undefined `dealer` var | CRITICAL | `app/scheduler.py` |
| `greeting_only` mode bypasses lifecycle (no LeadEvent) | HIGH | `app/engine/conversation.py` |
| `pass_count` not persisted to DB | HIGH | `app/engine/router.py` |
| Email adapter masks phone at parse time | HIGH | `app/adapters/intake/email_lead.py` |
| Email adapter sets consent=False (should be True) | HIGH | `app/adapters/intake/email_lead.py` |
| WhatsApp test handler is 180 lines of prod code in test route | CRITICAL | `app/main.py` |

## Architecture decisions (locked in, don't reverse)

- **Telegram** = ONLY dealer notification channel. Twilio = customer-facing ONLY.
- **Rep assignment** = DEFERRED. AI qualifies → books appointment → THEN rep assigned.
- **Transport abstraction** = mandatory. No hardcoded Twilio outside `app/transports/`.
- **One transaction per lead ingestion.** No partial commits.
- **TDD mandatory.** RED before GREEN.

## The 12-phase plan

| Phase | What | Est. time | Status |
|-------|------|-----------|--------|
| 0 | Cleanup (scaffolding, test handler) | 30 min | ✅ |
| 1 | Critical bugs (digest, lifecycle, pass_count, email) | 2.5h | ✅ Complete |
| 2 | Database (Alembic, pool size, dedup) | 1h | ✅ |
| 3 | Transaction safety (date val, claim, ingest tx) | 2h | ✅ |
| 4 | Transport abstraction (base, Telegram) | 2h | ✅ |
| 5 | Fix stubs (email, settings, template SID) | 2h | 🔲 |
| 6 | Rate limiting & auth | 30 min | 🔲 |
| 7 | Conversation memory | 1h | 🔲 |
| 8 | Testing (ongoing) | ongoing | 🔲 |
| 9 | Email channel | 10h | 🔲 |
| 10 | Manager vs Rep roles | 3h | 🔲 |
| 11 | UI redesign | 4h | 🔲 |
| 12 | Dealership demo site | 8h | 🔲 |

## Test suite baseline

- `pytest tests/ -x --tb=short` → 128 passed, 1 skipped (test_notify_rep_real.py — needs live creds)
- 1 warning (SAWarning identity map, benign)
- No errors
