"""Regression: the unauthenticated /dashboard/api/sales-team endpoint must
expose ONLY rep names — never `pin` (the login credential), `phone`, or
`telegram_chat_id`. Returning those is a full auth bypass (an attacker can read
the PINs and log in as any rep). Found in the 2026-06-25 audit of the F0-F11 work.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _client(tmp_path):
    import app.db as db
    from app.main import _auto_provision_dealers

    db_url = f"sqlite:///{(tmp_path / 'audit.db').as_posix()}"
    db.init_db(db_url)
    db.get_session_factory(db_url)
    _auto_provision_dealers()
    return TestClient(app)


def test_sales_team_endpoint_exposes_only_names(tmp_path):
    client = _client(tmp_path)
    r = client.get("/dashboard/api/sales-team?dealer_slug=premier-auto")
    assert r.status_code == 200
    data = r.json()

    reps = data.get("sales_team", [])
    names = [rep.get("name") for rep in reps]
    # Only active reps appear in the dropdown.
    assert "Helly" in names, f"Active rep Helly should be in {names}"
    assert "Vishva" not in names, f"Inactive rep Vishva should NOT be in {names}"

    # No secret of any kind may appear in the unauthenticated response.
    for rep in reps:
        assert set(rep.keys()) == {"name"}, f"endpoint leaks extra fields: {rep.keys()}"
    blob = r.text
    for secret in ("7721", "4826", "8990699115", "+17785550199"):
        assert secret not in blob, f"secret leaked in response: {secret}"
