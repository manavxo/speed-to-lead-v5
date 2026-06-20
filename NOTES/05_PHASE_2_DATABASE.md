# Phase 2: Database & Migrations

## Task 2.1: Install Alembic ✅

**What:** Installed alembic via pip, ran `alembic init alembic`, configured `alembic/env.py` to:
- Import all models from `app.models` (auto-discovery via SQLModel.metadata)
- Read `DATABASE_URL` from `app.config.settings` (same as app runtime)
- Use `_normalize_db_url()` from `app.db` for URL normalization

**Files created:**
- `alembic.ini`
- `alembic/env.py`
- `alembic/script.py.mako`
- `alembic/versions/` (migration directory)

## Task 2.2: Create initial migration ✅

**What:** `alembic revision --autogenerate -m "initial_schema"` created `82864cde1dc2_initial_schema.py`. Detected all 7 tables (dealer, vehicle, lead, message, leadevent, appointment, consentlog) with all columns, indexes, foreign keys, and enums.

**Note:** This is a BASELINE migration — it creates the current schema from scratch. On Render (where tables already exist), it should be run with `--fake` to mark it as applied without attempting to create existing tables.

**Files created:**
- `alembic/versions/82864cde1dc2_initial_schema.py`

## Task 2.3: Increase connection pool size ✅

**What:** Changed `pool_size` from 2→5 and `max_overflow` from 2→10 in `app/db.py`. The previous values (2+2=4 max connections) were too small for production under load, especially with background scheduler jobs competing with web requests.

**Files changed:** `app/db.py` — `_pool_kwargs()`

## Task 2.4: Remove duplicated `_normalize_db_url` ✅

**What:** Removed the duplicate `_normalize_db_url()` function from `app/scheduler.py` (definition + call site). `build_scheduler()` now imports from `from app.db import _normalize_db_url`.

**Note:** This was a textbook "copy-paste multiplication" from the Zero-Rework Doctrine. Same function in two files was a maintenance risk.

**Files changed:** `app/scheduler.py` — removed 7-line duplicate function, added 1-line import

## Verification
- Full suite: 140 passed, 1 skipped (no regressions)
- Alembic autogenerate detects all 7 tables correctly

**Commit:** `879d582 Phase 2: Alembic, pool size, duplicate _normalize_db_url cleanup`

---

# Next: Phase 3 — Transaction Safety

Tasks:
- 3.1: Add future-date validation to appointments
- 3.2: Fix handle_claim to verify rep identity
- 3.3: Wrap ingest_lead() in a single transaction
