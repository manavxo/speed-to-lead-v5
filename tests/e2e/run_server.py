"""Launch helper for the Playwright e2e suite.

Starts the FastAPI app on http://127.0.0.1:8000 against a fresh file-based
SQLite DB, auto-provisions the premier-auto dealer, and seeds leads — then
runs uvicorn in the foreground so Playwright's `webServer` can wait on it.

Env is set BEFORE importing app.* (Settings reads env at import time).
Run from tests/e2e/ (Playwright sets cwd to the config dir):  python run_server.py
"""
from __future__ import annotations

import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

# A fresh file DB at the project root (shared across all connections, unlike
# :memory:). Absolute posix path so the sqlite URL is unambiguous on Windows.
DB_FILE = ROOT / "e2e.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE.as_posix()}"
os.environ["OUTBOUND_ENABLED"] = "false"
os.environ["QUIET_HOURS_DISABLED"] = "true"
os.environ["REQUIRE_TWILIO_SIGNATURE"] = "false"
os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault("TWILIO_AUTH_TOKEN", "e2e-twilio-secret")
os.environ.setdefault("DASHBOARD_SECRET", "e2e-dashboard-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "e2e-openrouter-key")

# Start from a clean DB every run so seed counts are deterministic.
if DB_FILE.exists():
    DB_FILE.unlink()

from app.db import init_db  # noqa: E402
from app.main import app, _auto_provision_dealers  # noqa: E402

init_db()                    # create schema on the file DB
_auto_provision_dealers()    # create premier-auto from dealers/premier-auto.yaml

from seed import seed  # noqa: E402  (tests/e2e/seed.py)
seed()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
