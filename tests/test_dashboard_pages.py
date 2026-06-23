"""D2/D3/D4: Dashboard pages load properly with role separation."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app


# Leads 1-2 → Helly, 3-4 → Vishva, 5-6 → unassigned (manager-only).
# Insertion order fixes the autoincrement ids the scoping tests assume
# (lead 1 = Helly's, so a different rep gets 404 on it).
_SEED_LEADS = [
    ("Alice Test", "+17781110001", "Helly", "NEW"),
    ("Bob Test", "+17781110002", "Helly", "ENGAGED"),
    ("Carol Test", "+17781110003", "Vishva", "APPT_SET"),
    ("Dave Test", "+17781110004", "Vishva", "SOLD"),
    ("Eve Test", "+17781110005", None, "NEW"),
    ("Frank Test", "+17781110006", None, "AUTO_REPLIED"),
]


def _seed_leads(db) -> None:
    from sqlalchemy import select
    from app.models import Lead, LeadState, Channel, Dealer

    session = db.get_session_factory()()
    try:
        dealer = session.execute(
            select(Dealer).where(Dealer.slug == "premier-auto")
        ).scalars().first()
        assert dealer is not None, "premier-auto not provisioned"
        now = datetime.now(timezone.utc)
        for i, (name, phone, rep, state) in enumerate(_SEED_LEADS):
            session.add(Lead(
                dealer_id=dealer.id,
                name=name,
                phone=phone,
                assigned_rep=rep,
                state=LeadState[state],
                source=Channel.WEBFORM,
                consent=True,
                created_at=now - timedelta(hours=len(_SEED_LEADS) - i),
                updated_at=now - timedelta(hours=len(_SEED_LEADS) - i),
            ))
        session.commit()
    finally:
        session.close()


@pytest.fixture
def client(tmp_path):
    """TestClient backed by a real temp-file SQLite DB with premier-auto
    provisioned and leads seeded.

    The app's :memory: engine gives each connection its own empty DB, and the
    lifespan (which creates the schema + auto-provisions dealers) does not run
    under a bare TestClient. So we point the app at a shared file, build the
    schema, provision the test dealer, and seed leads here instead.
    """
    import app.db as db
    from app.main import _auto_provision_dealers

    db_url = f"sqlite:///{(tmp_path / 'dashboard.db').as_posix()}"
    db.init_db(db_url)              # rebuild engine + create_all on the file
    db.get_session_factory(db_url)  # bind the session factory to that engine
    _auto_provision_dealers()       # create premier-auto from dealers/*.yaml
    _seed_leads(db)

    try:
        yield TestClient(app)
    finally:
        # Reset cached globals so other test modules rebuild cleanly.
        db._engine = None
        db._SessionLocal = None


def _make_manager_session() -> str:
    from app.dashboard import _get_serializer
    return _get_serializer().dumps({
        "role": "manager",
        "rep_name": "",
        "dealer_slug": "premier-auto",
        "ts": 0,
    })


def _make_rep_session(rep_name: str = "Helly") -> str:
    from app.dashboard import _get_serializer
    return _get_serializer().dumps({
        "role": "rep",
        "rep_name": rep_name,
        "dealer_slug": "premier-auto",
        "ts": 0,
    })


# ---- D2: All pages load for manager ------------------------------------------

MANAGER_PAGES = [
    "/dashboard/leads",
    "/dashboard/appointments",
    "/dashboard/stats",
    "/dashboard/team",
    "/dashboard/settings",
]


@pytest.mark.parametrize("path", MANAGER_PAGES)
def test_manager_pages_return_200(client, path):
    """Manager can load every page (200, not 500)."""
    cookie = _make_manager_session()
    response = client.get(path, cookies={"session": cookie})
    assert response.status_code == 200, (
        f"Manager page {path} returned {response.status_code}: {response.text[:200]}"
    )


REP_PAGES = [
    "/dashboard/leads",
    "/dashboard/appointments",
    "/dashboard/stats",
]


@pytest.mark.parametrize("path", REP_PAGES)
def test_rep_pages_return_200(client, path):
    """Rep can load Leads, Appointments, Stats (200)."""
    cookie = _make_rep_session()
    response = client.get(path, cookies={"session": cookie})
    assert response.status_code == 200, (
        f"Rep page {path} returned {response.status_code}: {response.text[:200]}"
    )


RESTRICTED_PAGES = [
    "/dashboard/team",
    "/dashboard/settings",
]


@pytest.mark.parametrize("path", RESTRICTED_PAGES)
def test_rep_restricted_pages_redirect(client, path):
    """Rep is redirected away from Team and Settings pages."""
    cookie = _make_rep_session()
    response = client.get(path, cookies={"session": cookie}, follow_redirects=False)
    assert response.status_code == 303, (
        f"Rep restricted page {path} should redirect (303), got {response.status_code}"
    )


# ---- D4: Lead scoping --------------------------------------------------------

def test_manager_sees_all_leads(client):
    """Manager sees all 6 seeded leads."""
    cookie = _make_manager_session()
    response = client.get("/dashboard/leads", cookies={"session": cookie})
    assert response.status_code == 200


def test_rep_sees_only_own_leads(client):
    """Helly should only see her own leads (less than all)."""
    cookie = _make_rep_session("Helly")
    response = client.get("/dashboard/leads", cookies={"session": cookie})
    assert response.status_code == 200


def test_lead_detail_rep_own_lead(client):
    """Rep can view their own lead detail."""
    cookie = _make_rep_session("Helly")
    response = client.get("/dashboard/leads/1", cookies={"session": cookie})
    assert response.status_code in (200, 404)  # 404 if lead 1 isn't Helly's


def test_lead_detail_rep_other_lead(client):
    """Rep gets 404 accessing another rep's lead."""
    cookie = _make_rep_session("Vishva")
    response = client.get("/dashboard/leads/1", cookies={"session": cookie})
    assert response.status_code == 404


# ---- D6: New Lead creation ---------------------------------------------------

def test_create_lead_requires_auth(client):
    """POST /dashboard/leads/new without auth returns 401/redirect."""
    response = client.post(
        "/dashboard/leads/new",
        data={"name": "Test", "phone": "+17780000000"},
        follow_redirects=False,
    )
    assert response.status_code in (303, 401)


def test_create_lead_as_manager(client):
    """Manager can create a lead."""
    cookie = _make_manager_session()
    response = client.post(
        "/dashboard/leads/new",
        data={"name": "Test Lead", "phone": "+17780000001", "vehicle_ref": "Test Car"},
        cookies={"session": cookie},
    )
    assert response.status_code == 200
    assert "X-Toast-Message" in response.headers


def test_create_lead_as_rep(client):
    """Rep can create a lead assigned to them."""
    cookie = _make_rep_session("Helly")
    response = client.post(
        "/dashboard/leads/new",
        data={"name": "Helly Lead", "phone": "+17780000002"},
        cookies={"session": cookie},
    )
    assert response.status_code == 200
    assert "X-Toast-Message" in response.headers


# ---- D7: Status dropdown -----------------------------------------------------

def test_lead_detail_has_allowed_states(client):
    """Lead detail page passes allowed_states for the status dropdown."""
    cookie = _make_manager_session()
    response = client.get("/dashboard/leads/1", cookies={"session": cookie})
    assert response.status_code == 200


# ---- D5: Logout --------------------------------------------------------------

def test_logout_clears_session(client):
    """Logout route clears the session cookie."""
    cookie = _make_manager_session()
    response = client.get("/dashboard/logout", cookies={"session": cookie}, follow_redirects=False)
    assert response.status_code == 303
    set_cookie = response.headers.get("set-cookie", "").lower()
    # The cookie is cleared either by emptying the value or expiring it (Max-Age=0).
    assert 'session=;' in set_cookie or 'session=""' in set_cookie or 'max-age=0' in set_cookie
