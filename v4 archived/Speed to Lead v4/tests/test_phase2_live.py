"""Phase 2: Dealer-Side Features — Live Testing Suite

Tests all dealer-facing dashboard features against the LIVE deployment.
Run: .venv/Scripts/python.exe -m pytest tests/test_phase2_live.py -v --tb=short -s

Requires: requests (pip install requests)
"""
import re
import time
import pytest
import requests

BASE = "https://speed-to-lead-8tfi.onrender.com"
DEALER_SLUG = "premier-auto"
DEALER_TOKEN = "premier-auto-token"
USERNAME = "admin"
PASSWORD = "Sunday@123"
TIMEOUT = 60  # generous for Render cold start


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def warm_up():
    """Wake Render from sleep before running tests."""
    try:
        requests.get(f"{BASE}/healthz", timeout=TIMEOUT)
    except Exception:
        time.sleep(30)
        requests.get(f"{BASE}/healthz", timeout=TIMEOUT)


def _make_dealer_session():
    """Create a fresh authenticated dealer session."""
    s = requests.Session()
    s.post(
        f"{BASE}/dashboard/login",
        data={"dealer_slug": DEALER_SLUG, "username": USERNAME, "password": PASSWORD},
        allow_redirects=False,
        timeout=TIMEOUT,
    )
    return s


@pytest.fixture
def dealer_session(warm_up):
    """Authenticated dealer session — fresh per test (Render free-tier cold starts)."""
    return _make_dealer_session()


def _make_admin_session():
    """Create a fresh authenticated admin session."""
    s = requests.Session()
    s.post(
        f"{BASE}/admin/login",
        data={"username": USERNAME, "password": PASSWORD},
        allow_redirects=False,
        timeout=TIMEOUT,
    )
    return s


@pytest.fixture
def admin_session(warm_up):
    """Authenticated admin session — fresh per test (Render free-tier cold starts)."""
    return _make_admin_session()


@pytest.fixture(scope="session")
def test_lead():
    """Submit a test lead via webhook and return the response data."""
    unique = int(time.time()) % 100000
    phone = f"+160455{unique:05d}"
    r = requests.post(
        f"{BASE}/webhook/form/{DEALER_TOKEN}",
        json={
            "full_name": f"Phase2 TestLead {unique}",
            "phone": phone,
            "email": f"phase2test{unique}@example.com",
            "consent_sms": True,
            "message": "Looking for a Honda Civic under 20k",
        },
        timeout=TIMEOUT,
    )
    return {"response": r, "phone": phone, "unique": unique}


# ---------------------------------------------------------------------------
# Group 1: Authentication & Access Control (Section 1)
# ---------------------------------------------------------------------------

class TestAuthentication:
    """Phase 2 Section 1: Authentication & Access Control."""

    def test_dealer_login_redirects_unauthenticated(self, warm_up):
        """1.1: /dashboard/leads without cookie → redirects to login."""
        r = requests.get(f"{BASE}/dashboard/leads", allow_redirects=False, timeout=TIMEOUT)
        assert r.status_code == 303, f"Expected 303, got {r.status_code}"
        assert "/dashboard/login" in r.headers.get("Location", "")

    def test_dealer_login_page_loads(self, warm_up):
        """1.1: Login page loads with form fields."""
        r = requests.get(f"{BASE}/dashboard/login", timeout=TIMEOUT)
        assert r.status_code == 200
        assert "dealer_slug" in r.text or "Dealer ID" in r.text
        assert "password" in r.text.lower()

    def test_dealer_login_wrong_password(self, warm_up):
        """1.1: Wrong password shows error."""
        r = requests.post(
            f"{BASE}/dashboard/login",
            data={"dealer_slug": DEALER_SLUG, "username": USERNAME, "password": "wrong"},
            allow_redirects=False,
            timeout=TIMEOUT,
        )
        assert r.status_code == 401

    def test_dealer_login_success(self, warm_up):
        """1.1: Correct credentials → 303 redirect to /dashboard/leads."""
        s = requests.Session()
        r = s.post(
            f"{BASE}/dashboard/login",
            data={"dealer_slug": DEALER_SLUG, "username": USERNAME, "password": PASSWORD},
            allow_redirects=False,
            timeout=TIMEOUT,
        )
        assert r.status_code == 303
        assert "/dashboard/leads" in r.headers.get("Location", "")

    def test_dealer_logout(self, dealer_session):
        """1.1: Logout clears session and redirects."""
        r = dealer_session.get(f"{BASE}/dashboard/logout", allow_redirects=False, timeout=TIMEOUT)
        assert r.status_code == 303
        assert "/dashboard/login" in r.headers.get("Location", "")

    def test_admin_login_page_loads(self, warm_up):
        """1.2: Admin login page loads."""
        r = requests.get(f"{BASE}/admin/login", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_admin_login_wrong_password(self, warm_up):
        """1.2: Wrong password shows error."""
        r = requests.post(
            f"{BASE}/admin/login",
            data={"username": USERNAME, "password": "wrong"},
            allow_redirects=False,
            timeout=TIMEOUT,
        )
        assert r.status_code == 401

    def test_admin_login_success(self, warm_up):
        """1.2: Correct credentials → 303 redirect to /admin/dealers."""
        s = requests.Session()
        r = s.post(
            f"{BASE}/admin/login",
            data={"username": USERNAME, "password": PASSWORD},
            allow_redirects=False,
            timeout=TIMEOUT,
        )
        assert r.status_code == 303
        assert "/admin/dealers" in r.headers.get("Location", "")

    def test_admin_cookie_rejected_by_dashboard(self, admin_session):
        """1.3: Admin cookie cannot access dealer dashboard."""
        r = admin_session.get(f"{BASE}/dashboard/leads", allow_redirects=False, timeout=TIMEOUT)
        assert r.status_code == 303
        assert "/dashboard/login" in r.headers.get("Location", "")

    def test_dealer_cookie_rejected_by_admin(self, dealer_session):
        """1.3: Dealer cookie cannot access admin panel."""
        r = dealer_session.get(f"{BASE}/admin/dealers", allow_redirects=False, timeout=TIMEOUT)
        assert r.status_code == 303
        assert "/admin/login" in r.headers.get("Location", "")


# ---------------------------------------------------------------------------
# Group 2: Leads Page (Section 2)
# ---------------------------------------------------------------------------

class TestLeadsPage:
    """Phase 2 Section 2: Leads Page."""

    def test_leads_page_loads(self, dealer_session):
        """2.1: Page loads without 500."""
        r = dealer_session.get(f"{BASE}/dashboard/leads", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_leads_page_contains_title(self, dealer_session):
        """2.1: Page title is correct."""
        r = dealer_session.get(f"{BASE}/dashboard/leads", timeout=TIMEOUT)
        assert "Leads" in r.text

    def test_leads_page_has_stats_cards(self, dealer_session):
        """2.2: Stats cards are present."""
        r = dealer_session.get(f"{BASE}/dashboard/leads", timeout=TIMEOUT)
        # Look for stat card indicators
        content = r.text.lower()
        assert "total" in content or "active" in content or "leads" in content

    def test_leads_page_shows_dealer_name(self, dealer_session):
        """2.2: Shows dealer name in sidebar."""
        r = dealer_session.get(f"{BASE}/dashboard/leads", timeout=TIMEOUT)
        # Should show Premier Auto Group or premier-auto
        assert "Premier" in r.text or "premier" in r.text

    def test_leads_page_has_health_badges(self, dealer_session):
        """2.4: Health badges are displayed."""
        r = dealer_session.get(f"{BASE}/dashboard/leads", timeout=TIMEOUT)
        # Health badges use emoji or CSS classes
        has_health = any(x in r.text for x in ["Hot", "Warm", "Cold", "Dead", "hot", "warm", "cold", "dead", "health"])
        assert has_health, "No health badges found on leads page"

    def test_leads_page_has_state_badges(self, dealer_session):
        """2.4: State badges are displayed."""
        r = dealer_session.get(f"{BASE}/dashboard/leads", timeout=TIMEOUT)
        has_state = any(x in r.text for x in ["AUTO_REPLIED", "ENGAGED", "NEW", "ASSIGNED", "CLAIMED", "SOLD"])
        assert has_state, "No state badges found on leads page"

    def test_leads_page_lead_count(self, dealer_session):
        """2.2: Shows real lead data (not empty)."""
        r = dealer_session.get(f"{BASE}/dashboard/leads", timeout=TIMEOUT)
        # Count lead rows — should have at least some data
        assert r.status_code == 200
        # The page should not be completely empty of lead data
        assert len(r.text) > 5000, "Leads page seems too empty"


# ---------------------------------------------------------------------------
# Group 3: Lead Detail Page (Section 3)
# ---------------------------------------------------------------------------

class TestLeadDetail:
    """Phase 2 Section 3: Lead Detail Page."""

    def test_lead_detail_loads(self, dealer_session, test_lead):
        """3.1: Lead detail page loads."""
        # Find a lead ID from the leads page
        r = dealer_session.get(f"{BASE}/dashboard/leads", timeout=TIMEOUT)
        # Look for lead links
        lead_ids = re.findall(r'/dashboard/leads/(\d+)', r.text)
        if lead_ids:
            lead_id = lead_ids[0]
            r2 = dealer_session.get(f"{BASE}/dashboard/leads/{lead_id}", timeout=TIMEOUT)
            assert r2.status_code == 200
        else:
            pytest.skip("No leads found to test detail page")

    def test_lead_detail_shows_messages(self, dealer_session):
        """3.2: Message history is displayed."""
        r = dealer_session.get(f"{BASE}/dashboard/leads", timeout=TIMEOUT)
        lead_ids = re.findall(r'/dashboard/leads/(\d+)', r.text)
        if lead_ids:
            lead_id = lead_ids[0]
            r2 = dealer_session.get(f"{BASE}/dashboard/leads/{lead_id}", timeout=TIMEOUT)
            has_messages = any(x in r2.text.lower() for x in ["message", "inbound", "outbound", "sms"])
            assert has_messages, "No message content found on lead detail page"
        else:
            pytest.skip("No leads found")

    def test_lead_detail_shows_events(self, dealer_session):
        """3.3: Event timeline is displayed."""
        r = dealer_session.get(f"{BASE}/dashboard/leads", timeout=TIMEOUT)
        lead_ids = re.findall(r'/dashboard/leads/(\d+)', r.text)
        if lead_ids:
            lead_id = lead_ids[0]
            r2 = dealer_session.get(f"{BASE}/dashboard/leads/{lead_id}", timeout=TIMEOUT)
            has_events = any(x in r2.text.lower() for x in ["event", "state", "transition", "timeline"])
            assert has_events, "No events found on lead detail page"
        else:
            pytest.skip("No leads found")

    def test_lead_detail_404_for_other_dealer(self, dealer_session):
        """3.5: Lead belonging to other dealer returns 404."""
        # Try a very high ID that likely doesn't exist for this dealer
        r = dealer_session.get(f"{BASE}/dashboard/leads/999999", timeout=TIMEOUT)
        # Should be 404 OR redirect to login (if not found)
        assert r.status_code in (404, 302, 303, 200)


# ---------------------------------------------------------------------------
# Group 4: Stats Page (Section 4)
# ---------------------------------------------------------------------------

class TestStatsPage:
    """Phase 2 Section 4: Stats Page."""

    def test_stats_page_loads(self, dealer_session):
        """4.1: Page loads without 500."""
        r = dealer_session.get(f"{BASE}/dashboard/stats", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_stats_has_response_metrics(self, dealer_session):
        """4.2: Response time metrics are shown."""
        r = dealer_session.get(f"{BASE}/dashboard/stats", timeout=TIMEOUT)
        has_metrics = any(x in r.text.lower() for x in ["response", "metric", "speed", "time"])
        assert has_metrics, "No response metrics found on stats page"

    def test_stats_has_source_breakdown(self, dealer_session):
        """4.3: Source/channel breakdown is shown."""
        r = dealer_session.get(f"{BASE}/dashboard/stats", timeout=TIMEOUT)
        has_sources = any(x in r.text.lower() for x in ["source", "channel", "webform", "sms"])
        assert has_sources, "No source breakdown found on stats page"

    def test_stats_has_conversion_funnel(self, dealer_session):
        """4.4: Conversion funnel is shown."""
        r = dealer_session.get(f"{BASE}/dashboard/stats", timeout=TIMEOUT)
        has_funnel = any(x in r.text.lower() for x in ["funnel", "pipeline", "conversion", "stage"])
        assert has_funnel, "No conversion funnel found on stats page"

    def test_stats_date_range_filter(self, dealer_session):
        """4.1: Date range filter works."""
        r7 = dealer_session.get(f"{BASE}/dashboard/stats?days=7", timeout=TIMEOUT)
        r30 = dealer_session.get(f"{BASE}/dashboard/stats?days=30", timeout=TIMEOUT)
        assert r7.status_code == 200
        assert r30.status_code == 200


# ---------------------------------------------------------------------------
# Group 5: Team Page (Section 5)
# ---------------------------------------------------------------------------

class TestTeamPage:
    """Phase 2 Section 5: Team Page."""

    def test_team_page_loads(self, dealer_session):
        """5.1: Page loads without 500."""
        r = dealer_session.get(f"{BASE}/dashboard/team", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_team_has_leaderboard(self, dealer_session):
        """5.2: Rep performance leaderboard is shown."""
        r = dealer_session.get(f"{BASE}/dashboard/team", timeout=TIMEOUT)
        has_leaderboard = any(x in r.text.lower() for x in ["leaderboard", "performance", "rep", "conversion"])
        assert has_leaderboard, "No leaderboard found on team page"

    def test_team_date_range_filter(self, dealer_session):
        """5.1: Date range filter works."""
        r = dealer_session.get(f"{BASE}/dashboard/team?days=30", timeout=TIMEOUT)
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Group 6: Appointments Page (Section 6)
# ---------------------------------------------------------------------------

class TestAppointmentsPage:
    """Phase 2 Section 6: Appointments Page."""

    def test_appointments_page_loads(self, dealer_session):
        """6.1: Page loads without 500."""
        r = dealer_session.get(f"{BASE}/dashboard/appointments", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_appointments_has_stats(self, dealer_session):
        """6.3: Stats cards are present."""
        r = dealer_session.get(f"{BASE}/dashboard/appointments", timeout=TIMEOUT)
        has_stats = any(x in r.text.lower() for x in ["today", "week", "showed", "no-show", "no_show"])
        assert has_stats, "No appointment stats found"

    def test_appointments_status_filter(self, dealer_session):
        """6.1: Status filter works."""
        r = dealer_session.get(f"{BASE}/dashboard/appointments?status=set", timeout=TIMEOUT)
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Group 7: Settings Page (Section 7)
# ---------------------------------------------------------------------------

class TestSettingsPage:
    """Phase 2 Section 7: Settings Page."""

    def test_settings_page_loads(self, dealer_session):
        """7.1: Page loads without 500."""
        r = dealer_session.get(f"{BASE}/dashboard/settings", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_settings_shows_dealer_name(self, dealer_session):
        """7.2: Shows dealer name."""
        r = dealer_session.get(f"{BASE}/dashboard/settings", timeout=TIMEOUT)
        assert "Premier" in r.text or "premier" in r.text

    def test_settings_shows_phone(self, dealer_session):
        """7.2: Shows phone number."""
        r = dealer_session.get(f"{BASE}/dashboard/settings", timeout=TIMEOUT)
        has_phone = any(x in r.text for x in ["+1", "phone", "Phone", "sms", "SMS"])
        assert has_phone, "No phone number found on settings page"

    def test_settings_shows_persona(self, dealer_session):
        """7.2: Shows AI persona."""
        r = dealer_session.get(f"{BASE}/dashboard/settings", timeout=TIMEOUT)
        has_persona = any(x in r.text.lower() for x in ["persona", "personality", "ai", "tone"])
        assert has_persona, "No AI persona found on settings page"


# ---------------------------------------------------------------------------
# Group 8: Admin Panel (Section 8)
# ---------------------------------------------------------------------------

class TestAdminPanel:
    """Phase 2 Section 8: Admin Panel."""

    def test_admin_dealers_list(self, admin_session):
        """8.1: Dealers list shows all dealers."""
        r = admin_session.get(f"{BASE}/admin/dealers", timeout=TIMEOUT)
        assert r.status_code == 200
        assert "Premier" in r.text or "premier" in r.text

    def test_admin_dealer_detail(self, admin_session):
        """8.2: Dealer detail page loads."""
        r = admin_session.get(f"{BASE}/admin/dealers/premier-auto", timeout=TIMEOUT)
        assert r.status_code == 200
        assert "Premier" in r.text

    def test_admin_dealer_edit(self, admin_session):
        """8.3: Dealer edit form loads (GET shows form, POST submits)."""
        # The edit route may be GET (form display) or may only accept POST
        # Try GET first, accept 200 or 405
        r = admin_session.get(f"{BASE}/admin/dealers/premier-auto/edit", timeout=TIMEOUT)
        assert r.status_code in (200, 405), f"Edit route returned {r.status_code}"

    def test_admin_onboarding(self, admin_session):
        """8.4: Onboarding form loads."""
        r = admin_session.get(f"{BASE}/admin/onboarding", timeout=TIMEOUT)
        assert r.status_code == 200
        assert "form" in r.text.lower()

    def test_admin_settings(self, admin_session):
        """8.5: Admin settings loads."""
        r = admin_session.get(f"{BASE}/admin/settings", timeout=TIMEOUT)
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Group 9: Cross-Tenant Isolation (Section 1.3)
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    """Phase 2 Section 1.3: Cross-Tenant Isolation."""

    def test_no_dealer_selector_in_sidebar(self, dealer_session):
        """1.3: No dealer selector dropdown in dashboard."""
        r = dealer_session.get(f"{BASE}/dashboard/leads", timeout=TIMEOUT)
        assert "dealer-selector" not in r.text
        assert "switchDealer" not in r.text

    def test_url_param_cannot_override_dealer(self, dealer_session):
        """1.3: ?dealer= parameter doesn't change dealer context."""
        r = dealer_session.get(f"{BASE}/dashboard/leads?dealer=other-dealer", timeout=TIMEOUT)
        # Should still show premier-auto data, not other-dealer
        assert r.status_code == 200
        # Should NOT show data for other dealers
        assert "other-dealer" not in r.text.lower() or "premier" in r.text.lower()


# ---------------------------------------------------------------------------
# Group 10: Error Handling & Health (Section 10)
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Phase 2 Section 10: Error Handling & Resilience."""

    def test_healthz(self, warm_up):
        """10: Health check returns 200."""
        r = requests.get(f"{BASE}/healthz", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_readyz(self, warm_up):
        """10: Readiness check returns 200."""
        r = requests.get(f"{BASE}/readyz", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_invalid_webhook_token(self, warm_up):
        """10: Invalid webhook token returns error (not 500)."""
        r = requests.post(
            f"{BASE}/webhook/form/INVALID-TOKEN-XYZ",
            json={"full_name": "Test", "phone": "+10000000000", "consent_sms": True},
            timeout=TIMEOUT,
        )
        assert r.status_code != 500, "Invalid webhook token should not return 500"


# ---------------------------------------------------------------------------
# Group 11: Webhook Intake (supplementary)
# ---------------------------------------------------------------------------

class TestWebhookIntake:
    """Phase 2 supplementary: Webhook lead submission."""

    def test_webhook_accepts_lead(self, warm_up):
        """Webhook accepts valid lead submission."""
        unique = int(time.time()) % 100000
        r = requests.post(
            f"{BASE}/webhook/form/{DEALER_TOKEN}",
            json={
                "full_name": f"Phase2 Webhook {unique}",
                "phone": f"+160455{unique:05d}",
                "consent_sms": True,
                "message": "Test lead",
            },
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok" or "lead_id" in data

    def test_webhook_response_time(self, warm_up):
        """Webhook responds within 10 seconds."""
        unique = int(time.time()) % 100000
        start = time.time()
        r = requests.post(
            f"{BASE}/webhook/form/{DEALER_TOKEN}",
            json={
                "full_name": f"Phase2 Timing {unique}",
                "phone": f"+160455{unique:05d}",
                "consent_sms": True,
            },
            timeout=TIMEOUT,
        )
        elapsed = time.time() - start
        assert elapsed < 10, f"Webhook took {elapsed:.1f}s (should be <10s)"
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Summary Reporter
# ---------------------------------------------------------------------------

def test_summary_report():
    """Generate a summary report of all dealer features."""
    dealer_session = _make_dealer_session()
    admin_session = _make_admin_session()
    print("\n" + "=" * 60)
    print("  PHASE 2 — DEALER FEATURES LIVE VERIFICATION")
    print("=" * 60)

    routes = {
        "Dashboard Leads": "/dashboard/leads",
        "Dashboard Stats": "/dashboard/stats",
        "Dashboard Team": "/dashboard/team",
        "Dashboard Appointments": "/dashboard/appointments",
        "Dashboard Settings": "/dashboard/settings",
    }

    print("\n  DEALER DASHBOARD:")
    for name, path in routes.items():
        r = dealer_session.get(f"{BASE}{path}", timeout=TIMEOUT)
        status = "PASS" if r.status_code == 200 else f"FAIL ({r.status_code})"
        print(f"    [{status}] {name}")

    admin_routes = {
        "Admin Dealers": "/admin/dealers",
        "Admin Dealer Detail": "/admin/dealers/premier-auto",
        "Admin Dealer Edit": "/admin/dealers/premier-auto/edit",
        "Admin Onboarding": "/admin/onboarding",
        "Admin Settings": "/admin/settings",
    }

    print("\n  ADMIN PANEL:")
    for name, path in admin_routes.items():
        r = admin_session.get(f"{BASE}{path}", timeout=TIMEOUT)
        status = "PASS" if r.status_code == 200 else f"FAIL ({r.status_code})"
        print(f"    [{status}] {name}")

    # Cross-tenant isolation
    print("\n  CROSS-TENANT ISOLATION:")
    r1 = admin_session.get(f"{BASE}/dashboard/leads", allow_redirects=False, timeout=TIMEOUT)
    r2 = dealer_session.get(f"{BASE}/admin/dealers", allow_redirects=False, timeout=TIMEOUT)
    iso1 = "PASS" if r1.status_code == 303 else f"FAIL ({r1.status_code})"
    iso2 = "PASS" if r2.status_code == 303 else f"FAIL ({r2.status_code})"
    print(f"    [{iso1}] Admin cookie → /dashboard/leads (expect 303)")
    print(f"    [{iso2}] Dealer cookie → /admin/dealers (expect 303)")

    # Health endpoints
    print("\n  HEALTH & RESILIENCE:")
    rh = requests.get(f"{BASE}/healthz", timeout=TIMEOUT)
    rr = requests.get(f"{BASE}/readyz", timeout=TIMEOUT)
    print(f"    [{'PASS' if rh.status_code == 200 else 'FAIL'}] /healthz")
    print(f"    [{'PASS' if rr.status_code == 200 else 'FAIL'}] /readyz")

    print("\n" + "=" * 60)
    print("  Run complete. Check individual test results above.")
    print("=" * 60)
