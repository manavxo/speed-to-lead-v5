# Speed to Lead v4 — Scale Plan & Upgrade Path

> **Target market:** Small used-car dealerships in BC, Canada
> **Pricing model:** $299–$499/dealer/month
> **Current stack:** FastAPI + SQLModel + SQLite (dev) / Postgres (prod on Render)
> **Deployed at:** https://speed-to-lead-8tfi.onrender.com

---

## Table of Contents

1. [Current Architecture (Day 0)](#1-current-architecture-day-0)
2. [Bottleneck Analysis](#2-bottleneck-analysis)
3. [Scale Tiers — When to Upgrade](#3-scale-tiers--when-to-upgrade)
4. [Tier 0: Free / Solo (1 Dealer)](#4-tier-0-free--solo-1-dealer)
5. [Tier 1: Starter (2–5 Dealers)](#5-tier-1-starter-25-dealers)
6. [Tier 2: Growth (6–15 Dealers)](#6-tier-2-growth-615-dealers)
7. [Tier 3: Scale (16–50 Dealers)](#7-tier-3-scale-1650-dealers)
8. [Tier 4: Enterprise (50+ Dealers)](#8-tier-4-enterprise-50-dealers)
9. [Multi-Tenant Architecture](#9-multi-tenant-architecture)
10. [Database Migration Path](#10-database-migration-path)
11. [Connection Pooling](#11-connection-pooling)
12. [Worker & Scheduler Strategy](#12-worker--scheduler-strategy)
13. [Cost Projections](#13-cost-projections)
14. [Monitoring & Alerts](#14-monitoring--alerts)
15. [Upgrade Trigger Checklist](#15-upgrade-trigger-checklist)

---

## 1. Current Architecture (Day 0)

```
┌─────────────────────────────────────────────┐
│  Render Free Tier Web Service (1 worker)    │
│  uvicorn app.main:app --host 0.0.0.0       │
│                                             │
│  ┌─────────┐  ┌───────────┐  ┌───────────┐ │
│  │ FastAPI  │  │ Scheduler │  │ Dealer    │ │
│  │ Routes   │  │ (in-proc) │  │ YAML cfgs │ │
│  └────┬─────┘  └─────┬─────┘  └───────────┘ │
│       │              │                       │
│       └──────┬───────┘                       │
│              ▼                               │
│       SQLite / Postgres (free)              │
└─────────────────────────────────────────────┘
```

**Key facts:**
- Single uvicorn worker (no --workers flag)
- APScheduler runs in-process with the FastAPI app
- SQLite for local dev, Postgres free tier on Render
- Free web service sleeps after 15 min of inactivity
- Free Postgres expires after 90 days
- No connection pooling (raw SQLAlchemy session per request)
- All dealer configs are YAML files on disk in `dealers/`

---

## 2. Bottleneck Analysis

| # | Bottleneck | Impact | Severity | First Felt At |
|---|-----------|--------|----------|---------------|
| 1 | **SQLite concurrent writes** | Write lock contention → 500s on simultaneous inbound SMS | Critical | 2+ dealers |
| 2 | **Single uvicorn worker** | One slow AI call blocks all other requests | High | 1+ dealers |
| 3 | **Free tier cold start** | 30–90s wake-up time blows the <60s first-response promise | Critical | Day 1 (production) |
| 4 | **No connection pooling** | Each request opens a new DB connection; Postgres max_connections = 97 on free tier | Medium | 5+ dealers |
| 5 | **In-process scheduler** | If the app crashes or deploys, scheduled follow-ups are lost | High | 1+ dealers (production) |
| 6 | **Free Postgres 90-day limit** | Database gets deleted after 90 days | Critical | Day 90 |
| 7 | **Single-process memory** | 512 MB free tier limit; AI prompts + session state consume ~200 MB baseline | Medium | 5+ dealers |
| 8 | **No horizontal scaling** | Can't add more instances behind a load balancer on free tier | Medium | 10+ dealers |

---

## 3. Scale Tiers — When to Upgrade

### Tier Progression Table

| Tier | Dealers | Render Web Plan | DB Plan | Workers | Scheduler | Est. Monthly Cost | Est. Revenue |
|------|---------|----------------|---------|---------|-----------|-------------------|-------------|
| **0** | 1 (dev/staging) | Free ($0) | Free ($0) | 1 | In-process | $0 | $0–299 |
| **1** | 2–5 | Starter ($7/mo) | Basic-256 ($7/mo) | 2 | In-process + DB lock | ~$14/mo | $598–$1,495 |
| **2** | 6–15 | Standard ($25/mo) | Basic-1GB ($15/mo) | 4 | Separate worker service | ~$60/mo | $1,794–$4,485 |
| **3** | 16–50 | Pro ($85/mo) | Pro-4GB ($60/mo) | 8 | Dedicated cron service | ~$215/mo | $4,788–$14,950 |
| **4** | 50+ | Pro multi-instance ($170+/mo) | Pro-16GB+ ($200+/mo) | 16+ | Dedicated + queue | ~$500+/mo | $14,950+ |

### Decision Matrix

```
Upgrade from Tier 0 → 1 when:
  ✓ First real paying dealer on-boarded
  ✓ Need 24/7 uptime (no sleeping)
  ✓ Postgres free tier expiring soon

Upgrade from Tier 1 → 2 when:
  ✓ 5+ active dealers
  ✓ Scheduler jobs starting to pile up
  ✓ Response latency > 5s during peak hours
  ✓ Memory usage > 70% sustained

Upgrade from Tier 2 → 3 when:
  ✓ 15+ dealers / $4,500+ MRR
  ✓ Connection pool exhaustion errors
  ✓ Need zero-downtime deploys
  ✓ DB storage > 500 MB

Upgrade from Tier 3 → 4 when:
  ✓ 50+ dealers / $15,000+ MRR
  ✓ Single server can't handle the load
  ✓ Need dedicated read replicas
  ✓ Regional deployment requirements
```

---

## 4. Tier 0: Free / Solo (1 Dealer)

**When:** Development, staging, single-dealer pilot

### Current State (no changes needed)
- Render Free Web Service
- Render Free Postgres (90-day limit!)
- Single uvicorn worker
- In-process APScheduler
- SQLite for local dev

### Config
```yaml
# render.yaml (current)
services:
  - type: web
    plan: free
    # ...
databases:
  - plan: free
```

```bash
# Startup command
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### Risks
- Free Postgres deleted after 90 days → back up daily
- Service sleeps after 15 min → first response after wake = 30-90s
- No redundancy, no monitoring

---

## 5. Tier 1: Starter (2–5 Dealers)

**Monthly cost: ~$14/mo**
**Revenue: $598–$1,495/mo**
**Profit margin: 97–99%**

### Changes Required

#### 1. Upgrade Render Plans
```yaml
# render.yaml changes
services:
  - type: web
    plan: starter           # $7/mo — 24/7, no sleeping
    scaling:
      numInstances: 1
      minInstances: 1

databases:
  - plan: basic_256mb       # $7/mo — persistent, 256 MB storage
```

#### 2. Force Postgres (no SQLite in prod)
```python
# app/config.py — already reads DATABASE_URL from env
# In render.yaml envVars, DATABASE_URL comes from the database resource
# Ensure no SQLite fallback in production:
```

```python
# app/db.py — add a guard
import os
if os.getenv("ENVIRONMENT") == "production" and "sqlite" in settings.database_url:
    raise RuntimeError("SQLite is not allowed in production. Use Postgres.")
```

#### 3. Add Connection Pooling
```python
# app/db.py — use SQLAlchemy's built-in pool
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=5,           # 5 persistent connections
    max_overflow=10,       # 15 total max
    pool_timeout=30,       # wait up to 30s for a connection
    pool_recycle=300,      # recycle connections every 5 min
    pool_pre_ping=True,    # verify connection is alive before use
)
```

#### 4. Increase Uvicorn Workers
```bash
# Start with 2 workers (matches Starter plan's 512 MB RAM)
uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2
```

**Worker formula:** `workers = (2 * CPU_CORES) + 1`
- Starter: 0.5 CPU → 2 workers
- Standard: 1 CPU → 3 workers
- Pro: 2 CPU → 5 workers

#### 5. Scheduler Safety Net
Keep in-process for now, but add a DB-level lock to prevent double-firing:
```python
# In the scheduler job:
def run_scheduled_job(job_name: str):
    """Acquire a Postgres advisory lock so only one worker runs this job."""
    with get_session() as session:
        # Use pg_try_advisory_lock to prevent concurrent execution
        lock_id = hash(job_name) % (2**31)
        result = session.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": lock_id})
        if not result.scalar():
            return  # Another worker is already running this job
        try:
            # ... run the actual job ...
            pass
        finally:
            session.execute(text("SELECT pg_advisory_unlock(:id)"))
```

---

## 6. Tier 2: Growth (6–15 Dealers)

**Monthly cost: ~$60/mo**
**Revenue: $1,794–$4,485/mo**
**Profit margin: 97–99%**

### Changes Required

#### 1. Upgrade Render Plans
```yaml
services:
  - type: web
    plan: standard           # $25/mo — 1 GB RAM, 1 CPU
    scaling:
      numInstances: 1
  - type: worker             # NEW: separate scheduler service
    name: speed-to-lead-scheduler
    plan: starter            # $7/mo
    # Runs only the scheduler, not the web server

databases:
  - plan: basic_1gb          # $15/mo — 1 GB storage
```

#### 2. Separate the Scheduler
Create a dedicated scheduler entrypoint:

```python
# app/scheduler_worker.py
"""Standalone scheduler process — runs on Render as a Background Worker."""
from apscheduler.schedulers.background import BackgroundScheduler
from app.scheduler import register_all_jobs

def main():
    scheduler = BackgroundScheduler()
    register_all_jobs(scheduler)
    scheduler.start()
    # Keep alive
    import signal, threading
    event = threading.Event()
    signal.signal(signal.SIGINT, lambda s, f: event.set())
    signal.signal(signal.SIGTERM, lambda s, f: event.set())
    event.wait()

if __name__ == "__main__":
    main()
```

```yaml
# render.yaml — new worker service
  - type: worker
    name: speed-to-lead-scheduler
    runtime: docker
    dockerfilePath: ./Dockerfile
    plan: starter
    startCommand: python -m app.scheduler_worker
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: speed-to-lead-db
          property: connectionString
```

#### 3. Increase Workers
```bash
# 3 workers for Standard plan (1 CPU)
uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 3
```

#### 4. Connection Pool Upgrade
```python
engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=10,          # increased from 5
    max_overflow=20,       # 30 total max
    pool_timeout=30,
    pool_recycle=300,
    pool_pre_ping=True,
)
```

---

## 7. Tier 3: Scale (16–50 Dealers)

**Monthly cost: ~$215/mo**
**Revenue: $4,788–$14,950/mo**
**Profit margin: 98–99%**

### Changes Required

#### 1. Upgrade to Pro Plans
```yaml
services:
  - type: web
    plan: pro                # $85/mo — 2 GB RAM, 2 CPU
    scaling:
      numInstances: 1        # vertical scale first
  - type: worker
    name: speed-to-lead-scheduler
    plan: starter            # $7/mo

databases:
  - plan: pro_4gb            # $60/mo — 4 GB storage, connection pooling built-in
```

#### 2. Uvicorn Workers = 5
```bash
# 2 CPU * 2 + 1 = 5 workers
uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 5
```

#### 3. Connection Pool — Use PgBouncer (built into Render Pro DB)
```python
# When using Render's built-in connection pooling (PgBouncer),
# use the pooler URL instead of direct connection:
# DATABASE_URL = postgresql+psycopg://...@...pooler.oregon-postgres.render.com/...
# This gives you 97 max connections shared across all services.

engine = create_engine(
    settings.database_url,
    pool_size=20,            # aggressive pool for 5 workers
    max_overflow=10,
    pool_timeout=10,         # fail fast if pool exhausted
    pool_recycle=180,
    pool_pre_ping=True,
)
```

#### 4. Add Database Indexes for Multi-Tenant
```sql
-- These should already exist from the models, but verify:
CREATE INDEX IF NOT EXISTS idx_lead_dealer_state ON lead(dealer_id, state);
CREATE INDEX IF NOT EXISTS idx_lead_dealer_created ON lead(dealer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_message_lead_created ON message(lead_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_appointment_dealer_sched ON appointment(dealer_id, scheduled_for);
CREATE INDEX IF NOT EXISTS idx_vehicle_dealer_status ON vehicle(dealer_id, status);
```

#### 5. Add Basic Monitoring
```yaml
# Add to render.yaml
  - type: cron                # health check cron
    name: health-monitor
    schedule: "*/5 * * * *"   # every 5 minutes
    startCommand: python -m app.health_check
    plan: starter             # $7/mo
```

---

## 8. Tier 4: Enterprise (50+ Dealers)

**Monthly cost: ~$500+/mo**
**Revenue: $14,950+/mo**
**Profit margin: 97%+**

### Changes Required

#### 1. Horizontal Scaling (Multiple Web Instances)
```yaml
services:
  - type: web
    plan: pro
    scaling:
      numInstances: 3         # 3 instances behind Render's load balancer
      minInstances: 2
      maxInstances: 5
```

#### 2. External Job Queue (Replace In-Process Scheduler)
At this scale, move to a proper job queue:

```python
# Option A: Use Redis + RQ (Render has Redis for $7/mo)
# Option B: Use PostgreSQL-backed tasks (no extra infra)

# app/tasks.py — Postgres-backed task queue (zero extra cost)
class TaskQueue:
    """Simple Postgres-backed task queue. No Redis needed."""
    
    def enqueue(self, task_name: str, payload: dict, run_at: datetime = None):
        """Insert a task row. The scheduler worker picks it up."""
        with get_session() as session:
            task = ScheduledTask(
                task_name=task_name,
                payload=payload,
                run_at=run_at or datetime.utcnow(),
                status="pending",
            )
            session.add(task)
            session.commit()
    
    def claim_next(self) -> ScheduledTask:
        """Atomically claim the next pending task (SELECT ... FOR UPDATE SKIP LOCKED)."""
        with get_session() as session:
            result = session.execute(
                text("""
                    SELECT * FROM scheduled_task
                    WHERE status = 'pending' AND run_at <= now()
                    ORDER BY run_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                """)
            )
            row = result.first()
            if row:
                session.execute(
                    text("UPDATE scheduled_task SET status = 'running' WHERE id = :id"),
                    {"id": row.id}
                )
                session.commit()
                return row
            return None
```

#### 3. Database Upgrade
```yaml
databases:
  - plan: pro_16gb           # $200/mo — 16 GB storage
    # Or migrate to a dedicated Postgres (Neon, Supabase, Railway)
```

#### 4. Consider CDN / Static Assets
```yaml
  - type: static_site        # Serve dashboard static assets separately
    name: speed-to-lead-static
    buildCommand: npm run build
    staticPublishPath: ./dist
```

#### 5. Add Redis for Caching (Optional)
```yaml
  - type: redis
    name: speed-to-lead-cache
    plan: starter             # $7/mo — 256 MB
    # Use for: session cache, rate limiting, dealer config cache
```

---

## 9. Multi-Tenant Architecture

### How It Works Today (Already Multi-Tenant)

The engine is already multi-tenant:
- **Every table has `dealer_id`** as an indexed foreign key
- **Dealer YAML configs** are loaded from `dealers/<slug>.yaml`
- **Tenant resolution** happens via `sms_number`, `whatsapp_sender`, or `web_form_token` on the `Dealer` DB row

### What Needs to Change for Scale

#### Row-Level Isolation
Every query must include `WHERE dealer_id = :id` to prevent cross-tenant data leaks.

```python
# app/middleware.py — add a tenant context
from contextvars import ContextVar

current_dealer_id: ContextVar[int] = ContextVar("current_dealer_id", default=None)

class TenantMiddleware:
    """Sets the current dealer context from the request."""
    async def __call__(self, request, call_next):
        # Resolve dealer from: subdomain, path prefix, or query param
        dealer_slug = request.path_params.get("dealer_slug") or request.query_params.get("dealer")
        if dealer_slug:
            dealer = get_dealer_by_slug(dealer_slug)
            token = current_dealer_id.set(dealer.id)
            try:
                return await call_next(request)
            finally:
                current_dealer_id.reset(token)
        return await call_next(request)
```

#### Per-Tenant Rate Limiting
```python
# Prevent one dealer from consuming all resources
RATE_LIMITS = {
    "tier_1": {"sms_per_hour": 50, "ai_calls_per_hour": 100},
    "tier_2": {"sms_per_hour": 200, "ai_calls_per_hour": 500},
}
```

#### Config Caching
```python
# Cache dealer configs in memory (they change rarely)
from functools import lru_cache

@lru_cache(maxsize=128)
def get_dealer_config_cached(slug: str) -> DealerConfig:
    """Cached dealer config loader. Invalidated on config change."""
    path = Path(f"dealers/{slug}.yaml")
    return load_dealer_config(path)

def invalidate_dealer_config_cache(slug: str):
    get_dealer_config_cached.cache_clear()
```

---

## 10. Database Migration Path

### Phase 1: SQLite → Render Postgres (Already Done)
```
SQLite (dev) → Postgres free tier (prod on Render)
```
- `DATABASE_URL` is set in Render env vars
- SQLModel/SQLAlchemy handles dialect differences automatically
- No schema changes needed

### Phase 2: Render Free Postgres → Render Basic ($7/mo)
**When:** Before the 90-day free tier expires OR first paying customer

```bash
# On Render dashboard:
# 1. Create a new Basic-256MB Postgres instance
# 2. Use Render's built-in migration tool to copy data
# 3. Update DATABASE_URL in the web service env vars
# 4. Verify with: python -c "from app.db import *; print(engine.url)"
```

### Phase 3: Render Basic → Render Pro ($60/mo)
**When:** 10+ dealers OR storage > 200 MB

```bash
# Same process — Render handles the migration with minimal downtime
# The main benefit: built-in connection pooling (PgBouncer)
```

### Phase 4: Render Postgres → Dedicated Postgres
**When:** 50+ dealers OR need for read replicas OR custom extensions

**Options (ranked by simplicity):**

| Provider | Plan | Cost | Storage | Connections | Notes |
|----------|------|------|---------|-------------|-------|
| Neon | Pro | $19/mo | 10 GB | Pooled | Serverless, auto-scaling |
| Supabase | Pro | $25/mo | 8 GB | Direct + pooler | Dashboard included |
| Railway | Pro | $20/mo | 100 GB | 100 | Simple, fast |
| Render (Pro-16GB) | Pro | $200/mo | 16 GB | Built-in pooler | Keep it simple |
| Self-hosted (DO/Hetzner) | Custom | $20–50/mo | 50+ GB | Unlimited | More work |

**Recommended:** Stay on Render until you need read replicas or >16 GB, then move to Neon or Supabase.

### Migration Script
```python
# tools/migrate_db.py
"""Migrate data between databases. Usage:
    python tools/migrate_db.py --from sqlite:///dev.db --to $NEW_DATABASE_URL
"""
import argparse
from sqlalchemy import create_engine, text, inspect

def migrate(from_url: str, to_url: str):
    src = create_engine(from_url)
    dst = create_engine(to_url)
    
    inspector = inspect(src)
    tables = inspector.get_table_names()
    
    for table in tables:
        if table == "alembic_version":
            continue
        print(f"Migrating {table}...")
        rows = src.execute(text(f"SELECT * FROM {table}")).fetchall()
        if not rows:
            continue
        
        columns = inspector.get_columns(table)
        col_names = [c["name"] for c in columns]
        placeholders = ", ".join([f":{c}" for c in col_names])
        insert_sql = f"INSERT INTO {table} ({', '.join(col_names)}) VALUES ({placeholders})"
        
        for row in rows:
            data = dict(zip(col_names, row._mapping))
            dst.execute(text(insert_sql), data)
    
    dst.commit()
    print(f"Migration complete. {len(tables)} tables migrated.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="from_url", required=True)
    parser.add_argument("--to", dest="to_url", required=True)
    args = parser.parse_args()
    migrate(args.from_url, args.to_url)
```

---

## 11. Connection Pooling

### Configuration by Tier

| Tier | Pool Size | Max Overflow | Total Max | Pool Timeout | Pool Recycle |
|------|-----------|-------------|-----------|--------------|-------------|
| 0 (Free) | 1 | 0 | 1 | 30s | 300s |
| 1 (Starter) | 5 | 10 | 15 | 30s | 300s |
| 2 (Standard) | 10 | 20 | 30 | 20s | 180s |
| 3 (Pro) | 20 | 10 | 30 | 10s | 180s |
| 4 (Pro+) | 20 | 10 | 30 | 5s | 120s |

### Implementation

```python
# app/db.py — dynamic pool sizing based on environment
import os

def get_pool_config() -> dict:
    env = os.getenv("ENVIRONMENT", "development")
    configs = {
        "development": {"pool_size": 1, "max_overflow": 0},
        "staging":     {"pool_size": 5, "max_overflow": 10},
        "production":  {"pool_size": 10, "max_overflow": 20},
    }
    return configs.get(env, configs["development"])

pool_cfg = get_pool_config()
engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=pool_cfg["pool_size"],
    max_overflow=pool_cfg["max_overflow"],
    pool_timeout=10,
    pool_recycle=180,
    pool_pre_ping=True,
)
```

### Monitoring Pool Health
```python
# Add to /healthz endpoint
@app.get("/healthz")
async def healthz():
    pool_status = {
        "pool_size": engine.pool.size(),
        "checked_out": engine.pool.checkedout(),
        "overflow": engine.pool.overflow(),
        "checkedin": engine.pool.checkedin(),
    }
    return {"status": "ok", "pool": pool_status}
```

---

## 12. Worker & Scheduler Strategy

### Current: In-Process Scheduler
```
┌──────────────────────────┐
│  uvicorn (1 worker)      │
│  ├─ FastAPI routes       │
│  ├─ APScheduler          │  ← dies if the process restarts
│  └─ DB connection        │
└──────────────────────────┘
```

### Tier 1: In-Process + Advisory Lock
```
┌──────────────────────────┐
│  uvicorn (2 workers)     │
│  ├─ FastAPI routes       │
│  ├─ APScheduler          │  ← runs on all workers, but pg_advisory_lock
│  └─ DB connection        │     ensures only one executes each job
└──────────────────────────┘
```

### Tier 2+: Separate Scheduler Worker
```
┌──────────────────────┐    ┌──────────────────────┐
│  uvicorn (3 workers) │    │  scheduler (1 worker) │
│  ├─ FastAPI routes   │    │  ├─ APScheduler       │
│  └─ DB connections   │    │  └─ DB connection     │
└──────────┬───────────┘    └──────────┬────────────┘
           │                           │
           └─────────┬─────────────────┘
                     ▼
              PostgreSQL DB
```

### Tier 4: Dedicated Task Queue
```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  uvicorn #1  │  │  uvicorn #2  │  │  uvicorn #3  │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       └────────┬────────┴────────┬────────┘
                ▼                 ▼
         ┌──────────────┐  ┌──────────────┐
         │  task_queue   │  │  scheduler    │
         │  (consumer)   │  │  (dispatcher) │
         └──────┬───────┘  └──────┬───────┘
                │                 │
                └────────┬────────┘
                         ▼
                  PostgreSQL DB
```

### Scheduler Jobs to Separate
| Job | Frequency | Priority | Notes |
|-----|-----------|----------|-------|
| Follow-up messages | Every 1 min | Critical | Can't miss — affects lead conversion |
| Inventory sync | Every 3 hours | Low | Can tolerate delays |
| Health check | Every 5 min | Medium | Alert on failure |
| Stale lead cleanup | Daily 2am | Low | Batch operation |
| Analytics aggregation | Daily 3am | Low | Batch operation |

---

## 13. Cost Projections

### Monthly Infrastructure Costs by Tier

| Component | Tier 0 | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|-----------|--------|--------|--------|--------|--------|
| Web Service | $0 | $7 | $25 | $85 | $170+ |
| Database | $0 | $7 | $15 | $60 | $200+ |
| Scheduler Worker | $0 | $0 | $7 | $7 | $7 |
| Health Monitor | $0 | $0 | $0 | $7 | $7 |
| Redis (optional) | $0 | $0 | $0 | $0 | $7 |
| **Total Infra** | **$0** | **$14** | **$47** | **$159** | **$391+** |

### Revenue vs Cost

| Tier | Dealers | Revenue ($299–499) | Infra Cost | Profit | Margin |
|------|---------|-------------------|------------|--------|--------|
| 0 | 1 | $0–299 | $0 | $0–299 | — |
| 1 | 2–5 | $598–2,495 | $14 | $584–2,481 | 97–99% |
| 2 | 6–15 | $1,794–7,485 | $47 | $1,747–7,438 | 97–99% |
| 3 | 16–50 | $4,788–24,950 | $159 | $4,629–24,791 | 97–99% |
| 4 | 50+ | $14,950+ | $391+ | $14,559+ | 97%+ |

### External Service Costs (per dealer)

| Service | Cost | Notes |
|---------|------|-------|
| Twilio SMS | ~$0.0075/msg + $1/mo/number | ~$5–15/dealer/mo |
| Twilio WhatsApp | ~$0.005/msg | ~$3–10/dealer/mo |
| OpenRouter AI | ~$0.001/call | ~$5–20/dealer/mo |
| **Total per dealer** | | **~$13–45/dealer/mo** |

### Break-Even Analysis
- **Fixed costs:** $0–391/mo (infra)
- **Variable costs per dealer:** ~$25/mo (Twilio + AI)
- **Revenue per dealer:** $299–499/mo
- **Profit per dealer:** $274–474/mo
- **Break-even:** 1 dealer (Tier 1) — profitable from day 1

---

## 14. Monitoring & Alerts

### Essential Metrics to Track

| Metric | Warning | Critical | How |
|--------|---------|----------|-----|
| Response time (p95) | > 3s | > 10s | Render metrics + custom |
| Error rate | > 1% | > 5% | Render logs |
| DB connection pool usage | > 70% | > 90% | /healthz endpoint |
| Memory usage | > 70% | > 90% | Render metrics |
| Scheduler job failures | > 2/hour | > 5/hour | Custom logging |
| Twilio delivery failures | > 5% | > 15% | Twilio webhooks |
| Queue depth (pending follow-ups) | > 50 | > 200 | DB count |

### Alerting Setup (Tier 2+)
```python
# app/monitoring.py
import logging
import os

logger = logging.getLogger("speed_to_lead")

def alert_severity(message: str, severity: str = "warning"):
    """Log an alert. In production, this would also send to Slack/email."""
    logger.log(
        getattr(logging, severity.upper(), logging.WARNING),
        f"[ALERT:{severity.upper()}] {message}"
    )
    
    # Future: send to Slack webhook, PagerDuty, etc.
    # slack_webhook = os.getenv("SLACK_ALERT_WEBHOOK")
    # if slack_webhook:
    #     requests.post(slack_webhook, json={"text": f"[{severity}] {message}"})
```

---

## 15. Upgrade Trigger Checklist

### Monitor These Numbers Weekly

```
□ Database storage used (MB)
□ Connection pool peak usage
□ Average response time (p50, p95)
□ Error rate (%)
□ Memory usage (peak %)
□ Active dealers count
□ Monthly Twilio + AI costs
□ Monthly revenue
□ Scheduler job failure rate
□ Cold start frequency (if on free tier)
```

### Decision Tree

```
Is the service sleeping? (Free tier)
  → YES: Upgrade to Starter ($7/mo)

Is the Postgres free tier expiring? (90 days)
  → YES: Upgrade to Basic ($7/mo)

Are you getting "too many connections" errors?
  → YES: Upgrade DB plan OR add connection pooling

Are response times > 5s during business hours?
  → YES: Increase workers OR upgrade web plan

Are scheduled jobs not running after deploys?
  → YES: Separate scheduler into its own worker service

Is DB storage > 80% of plan limit?
  → YES: Upgrade DB plan

Are you onboarding dealers faster than 1/week?
  → YES: Implement the onboarding automation (see 10-CLIENT-ONBOARDING.md)

Is MRR > $5,000?
  → YES: Move to Tier 3 (Pro plans) for reliability
```

---

## Appendix: render.yaml — Fully Commented Production Template

```yaml
# Speed to Lead v4 — Render Blueprint
# Current: Tier 0 (Free). See 09-SCALE-PLAN.md for upgrade path.
#
# TIER PROGRESSION:
#   Tier 0 (Free):      plan: free / free
#   Tier 1 (Starter):   plan: starter ($7) / basic_256mb ($7)        = $14/mo
#   Tier 2 (Growth):    plan: standard ($25) / basic_1gb ($15)       = $47/mo (incl. scheduler worker)
#   Tier 3 (Scale):     plan: pro ($85) / pro_4gb ($60)              = $159/mo
#   Tier 4 (Enterprise):plan: pro (2x $85) / pro_16gb ($200)         = $391+/mo

databases:
  - name: speed-to-lead-db
    databaseName: speedtolead
    plan: free              # TIER 0: free (90 days!)
                              # TIER 1: basic_256mb ($7/mo)
                              # TIER 2: basic_1gb ($15/mo)
                              # TIER 3: pro_4gb ($60/mo)
                              # TIER 4: pro_16gb ($200/mo)
    ipAllowList: []

services:
  - type: web
    name: speed-to-lead
    runtime: docker
    dockerfilePath: ./Dockerfile
    plan: free              # TIER 0: free (sleeps after 15 min!)
                              # TIER 1: starter ($7/mo, 24/7)
                              # TIER 2: standard ($25/mo)
                              # TIER 3: pro ($85/mo)
    region: oregon
    # TIER 3+: Add scaling block:
    # scaling:
    #   numInstances: 1       # Increase to 2-3 for horizontal scaling
    #   minInstances: 1
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
                              # TIER 1: --workers 2
                              # TIER 2: --workers 3
                              # TIER 3: --workers 5
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: speed-to-lead-db
          property: connectionString
      - key: ENVIRONMENT
        value: production
      - key: PUBLIC_BASE_URL
        value: https://speed-to-lead-8tfi.onrender.com
      - key: OUTBOUND_ENABLED
        value: "false"
      # Secrets: set manually in Render dashboard
      # TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, OPENROUTER_API_KEY
    healthCheckPath: /healthz
    autoDeploy: true

  # TIER 2+: Add a dedicated scheduler worker
  # - type: worker
  #   name: speed-to-lead-scheduler
  #   runtime: docker
  #   dockerfilePath: ./Dockerfile
  #   plan: starter              # $7/mo
  #   startCommand: python -m app.scheduler_worker
  #   envVars:
  #     - key: DATABASE_URL
  #       fromDatabase:
  #         name: speed-to-lead-db
  #         property: connectionString
  #     - key: ENVIRONMENT
  #       value: production
```

---

## 16. Critical Fixes Applied (June 2026)

The following critical issues were identified and fixed before production deployment:

### 16.1 Scheduler Corruption (FIXED)
**Severity:** Critical — would crash on import

**Problem:** `app/scheduler.py` had corrupted code (lines 232-325 missing) and a syntax error in `_normalize_db_url()`. The function had an incomplete return statement that would crash on import.

**Fix:** Reconstructed missing code, fixed `_normalize_db_url()`, replaced deprecated `datetime.utcnow()` with `datetime.now(timezone.utc)`, and implemented the follow-up handler (was a TODO stub).

**Status:** ✅ Fixed and tested

---

### 16.2 No Conversation Memory (FIXED)
**Severity:** Critical — AI had no context between turns

**Problem:** `_call_openrouter()` in `conversation.py` only sent the system prompt + ONE user message. The AI had zero memory of prior conversation. Every turn was a fresh conversation.

**Fix:** Modified `_call_openrouter()` to load the last 10 messages from the `Message` table for that lead and include them in the API call. OUTBOUND messages map to "assistant" role, INBOUND to "user" role.

**Status:** ✅ Fixed and tested

---

### 16.3 Round-Robin Infinite Loop (FIXED)
**Severity:** High — would ping-pong forever with 1 active rep

**Problem:** If only 1 active rep kept passing leads, `handle_pass()` would call `assign_lead()` again indefinitely, creating an infinite loop of WhatsApp pings.

**Fix:** Added `pass_count` field to the `Lead` model. `handle_pass()` now increments `pass_count` on each pass. After `max_pass_count` (default 3) passes, it escalates to the dealer's manager instead of reassigning.

**Status:** ✅ Fixed and tested

---

### 16.4 Missing START/Resubscribe Handler (STILL MISSING)
**Severity:** Medium — compliance gap

**Problem:** Opt-out reply says "Reply START to resubscribe" but there's no handler for START/STARTALL keywords. Users who want to resubscribe will get no response.

**Fix needed:** Add START/STARTALL keyword handling in the SMS webhook to:
1. Check if user is opted out
2. If yes, remove opt-out flag and log consent
3. Send confirmation: "You've been resubscribed. Reply STOP to opt out again."

**Status:** ⚠️ Not yet implemented

---

### 16.5 Consent Gating on Intake (STILL MISSING)
**Severity:** Medium — CASL compliance gap

**Problem:** `route_lead.py` ingests leads regardless of consent status. Leads are logged but not gated on consent. CASL requires consent before sending commercial electronic messages.

**Fix needed:** Add consent check before first SMS send:
1. Check if lead has provided express consent (web form submission = implied consent for 6 months)
2. Log consent in ConsentLog table
3. Block sends if no consent exists

**Status:** ⚠️ Not yet implemented

---

### 16.6 No Database Migrations (STILL MISSING)
**Severity:** High — will break on schema changes

**Problem:** Using `SQLModel.metadata.create_all()` which only creates tables, doesn't handle migrations. Adding a column or changing a type requires manual migration or recreating the table.

**Fix needed:** Add Alembic for database migrations:
1. Initialize Alembic: `alembic init alembic`
2. Configure to use same DATABASE_URL
3. Generate initial migration: `alembic revision --autogenerate -m "initial"`
4. Run migrations on deploy: `alembic upgrade head`

**Status:** ⚠️ Not yet implemented

---

### 16.7 OpenRouter Retry Logic (STILL MISSING)
**Severity:** Medium — will fail on transient API errors

**Problem:** No retry logic for OpenRouter API calls. If the API returns a 500 or times out, the conversation fails with a generic error message.

**Fix needed:** Add retry with exponential backoff:
1. Retry up to 3 times on 5xx errors
2. Retry on timeout (10s)
3. Circuit breaker: after 5 consecutive failures, stop calling for 5 minutes
4. Fallback message: "I'm having trouble connecting right now. Please try again in a few minutes."

**Status:** ⚠️ Not yet implemented

---

### 16.8 Max Conversation Turns (STILL MISSING)
**Severity:** Medium — cost guardrail

**Problem:** No limit on conversation turns. A customer could keep texting forever, generating unlimited OpenRouter API calls (~$0.01-0.025 per turn).

**Fix needed:** Add conversation turn limit:
1. Track turn count in Lead model (or count Messages)
2. After 10 turns without resolution, send: "I've passed your information to our team. A rep will follow up shortly."
3. Transition lead to ASSIGNED state for human follow-up

**Status:** ⚠️ Not yet implemented

---

### 16.9 Cold Start Mitigation (PARTIALLY ADDRESSED)
**Severity:** Critical for free tier

**Problem:** Render free tier sleeps after 15 min. First request after sleep takes 30-60s. Twilio webhooks timeout after 15s. First SMS after sleep will FAIL.

**Partial fix:** Render free tier allows a "keep-alive" cron job that pings the service every 10 minutes to prevent sleeping. However, this uses free tier hours (750/mo).

**Full fix:** Upgrade to Render Starter ($7/mo) for 24/7 uptime.

**Status:** ⚠️ Partially addressed (keep-alive cron can be added)

---

## 17. Production Readiness Checklist

Use this checklist before onboarding your first real dealer:

### Critical (Must Fix)
- [x] Fix scheduler.py corruption
- [x] Add conversation history to AI
- [x] Fix round-robin infinite loop
- [ ] Add START/resubscribe handler
- [ ] Add consent gating on intake
- [ ] Add Alembic migrations
- [ ] Test with real Twilio sandbox

### Important (Should Fix)
- [ ] Add OpenRouter retry logic
- [ ] Add max conversation turns (10)
- [ ] Add connection pooling (Tier 1)
- [ ] Add keep-alive cron (free tier) or upgrade to Starter
- [ ] Test end-to-end with real phone numbers

### Nice to Have (Can Wait)
- [ ] Add sentiment analysis for escalation triggers
- [ ] Add appointment slot validation (business hours)
- [ ] Add message delivery tracking and retry
- [ ] Add dashboard authentication (currently just settings exist)
- [ ] Add CRM sync adapters

---

## 18. Free Tier Reality Check

### What You CAN Do on Free Tier
- Develop and test locally
- Demo to investors/partners (with mock data)
- Run a single dealer pilot (with keep-alive cron)
- Validate the product-market fit

### What You CANNOT Do on Free Tier
- Run real customers reliably (cold starts will drop messages)
- Scale beyond 1 dealer (SQLite will break)
- Keep data past 90 days (Postgres deleted)
- Handle concurrent SMS webhooks (SQLite write locks)

### Minimum Viable Production Stack
**Cost:** $14/mo (Render Starter + Basic Postgres)
**What it gives you:**
- 24/7 uptime (no sleeping)
- Persistent database (no 90-day expiry)
- 2 uvicorn workers (handles concurrent requests)
- 512 MB RAM (enough for 5-10 dealers)
- Custom domain support

**Recommendation:** Don't try to run real customers on free tier. The $14/mo investment eliminates the biggest reliability risks and lets you focus on sales instead of infrastructure.

---

*Last updated: 2026-06-06*
*Next review: When onboarding 2nd paying dealer*
