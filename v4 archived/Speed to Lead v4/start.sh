#!/bin/bash
# Production entrypoint — ensures DB schema, starts uvicorn with scheduler via lifespan.
# Single process: scheduler runs INSIDE the FastAPI app (not as separate process).
set -euo pipefail

echo "=== Speed-to-Lead v4: starting up ==="

# --- Database schema fixup ---
# Before Alembic, ensure critical columns exist on pre-existing tables.
# This handles the case where Render DB was created by an older deploy
# and Alembic's CREATE TABLE fails because tables already exist.
echo "Ensuring critical columns exist..."
python -c "
import os, sqlalchemy
url = os.environ.get('DATABASE_URL', '')
if not url:
    print('No DATABASE_URL — skipping column fixup (local/dev)')
    exit(0)
if url.startswith('postgresql://'):
    url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
if 'render.com' in url and 'sslmode' not in url:
    sep = '&' if '?' in url else '?'
    url = url + sep + 'sslmode=require'
engine = sqlalchemy.create_engine(url)
with engine.connect() as conn:
    # Check what columns exist on the lead table
    result = conn.execute(sqlalchemy.text(
        \"SELECT column_name FROM information_schema.columns WHERE table_name='lead'\"
    ))
    existing = {row[0] for row in result}
    print(f'Existing lead columns: {sorted(existing)}')

    # Add missing columns
    additions = {
        'assigned_rep': 'TEXT',
        'pass_count': 'INTEGER DEFAULT 0',
        'consent': 'BOOLEAN DEFAULT FALSE',
        'vehicle_id': 'INTEGER',
        'loss_reason': 'TEXT',
    }
    for col, coltype in additions.items():
        if col not in existing:
            print(f'  Adding lead.{col} ({coltype})')
            conn.execute(sqlalchemy.text(f'ALTER TABLE lead ADD COLUMN {col} {coltype}'))

    # Check dealer table
    result = conn.execute(sqlalchemy.text(
        \"SELECT column_name FROM information_schema.columns WHERE table_name='dealer'\"
    ))
    existing_dealer = {row[0] for row in result}
    print(f'Existing dealer columns: {sorted(existing_dealer)}')

    dealer_additions = {
        'sms_number': 'TEXT',
        'whatsapp_sender': 'TEXT',
        'web_form_token': 'TEXT',
        'config': 'JSONB',
        'round_robin_pointer': 'INTEGER DEFAULT 0',
        'timezone': 'TEXT DEFAULT \'America/Vancouver\'',
    }
    for col, coltype in dealer_additions.items():
        if col not in existing_dealer:
            print(f'  Adding dealer.{col} ({coltype})')
            conn.execute(sqlalchemy.text(f'ALTER TABLE dealer ADD COLUMN {col} {coltype}'))

    conn.commit()
    print('Column fixup complete.')
" 2>&1 || echo "WARNING: Column fixup failed (may be first deploy — tables don't exist yet)"

# Run Alembic migrations (primary migration path for production)
echo "Running database migrations..."
if alembic upgrade head 2>&1; then
    echo "Alembic migrations complete."
else
    echo "WARNING: Alembic upgrade failed. Attempting to stamp existing DB..."
    alembic stamp head 2>&1 || echo "WARNING: Alembic stamp also failed"
    alembic upgrade head 2>&1 || echo "WARNING: Second Alembic upgrade attempt failed"
fi

# Fallback: create tables if they don't exist (covers edge cases / first deploy)
echo "Ensuring all tables exist (fallback)..."
python -c "from app.db import init_db; init_db()" || echo "WARNING: DB init failed"

# NOTE: Demo inventory seeding removed from startup.
# Dealers should upload their own inventory via the admin dashboard
# or use the /admin/api/seed-vehicles endpoint (dev/staging only).
echo "Startup complete — no auto-seeding."

# Graceful shutdown: let uvicorn finish in-flight requests
cleanup() {
    echo "Shutting down uvicorn..."
    kill "$UVICORN_PID" 2>/dev/null || true
    wait "$UVICORN_PID" 2>/dev/null || true
    echo "Shutdown complete."
}
trap cleanup SIGTERM SIGINT

# Start the FastAPI web server (with scheduler running via lifespan)
# --workers 1 is REQUIRED because the scheduler runs in-process
# PaaS sets $PORT; fall back to 8000 for local/Docker
WEB_PORT="${PORT:-8000}"
echo "Starting uvicorn on port $WEB_PORT (scheduler runs in-process via lifespan)..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "$WEB_PORT" \
    --workers 1 \
    --log-level info \
    --proxy-headers \
    --forwarded-allow-ips '*' &
UVICORN_PID=$!

wait "$UVICORN_PID"
