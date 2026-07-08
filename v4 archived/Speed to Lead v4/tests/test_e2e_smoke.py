"""End-to-end smoke test — exercises the full lifecycle locally using TestClient.

This is the "pre-deploy gate" test: provision → form lead → auto-reply → claim → book → opt-out.
Run before every deploy to verify nothing is broken.

For live deployment testing, see demo/README.md for the real-phone walkthrough.
"""

from __future__ import annotations

from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.models import (
    ConsentLog, Dealer, Lead, LeadState, Message, Direction, Vehicle,
)
from tests.conftest import make_auth_cookies


def _make_full_dealer(db_engine, slug="e2e-dealer", token="e2e-token"):
    """Create a dealer with inventory seeded."""
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = TestSession()
    d = Dealer(
        slug=slug,
        name="E2E Motors",
        config={
            "dealer": {"name": "E2E Motors", "timezone": "America/Vancouver", "main_phone": "+160****0000"},
            "hours": {"mon": "09:00-19:00", "tue": "09:00-19:00", "wed": "09:00-19:00",
                      "thu": "09:00-19:00", "fri": "09:00-19:00", "sat": "10:00-17:00"},
            "channels": {
                "web_form_token": token,
                "sms_number": "+177****0222",
                "whatsapp_sender": "+177****0223",
            },
            "sales_team": [
                {"name": "Alex", "phone": "+160****0301", "active": True},
                {"name": "Jordan", "phone": "+160****0302", "active": True},
            ],
            "compliance": {"opt_out_keywords": ["STOP", "ARRET"], "quiet_hours": "21:00-08:00"},
            "routing": {"strategy": "round_robin", "claim_timeout_min": 5},
            "ai": {"persona": "friendly local rep", "goal": "book_appointment"},
            "followups": {"cadence_min": [5, 60, 1440]},
        },
    )
    session.add(d)
    session.commit()
    session.refresh(d)

    # Seed some vehicles
    vehicles = [
        Vehicle(
            dealer_id=d.id, stock_no="SA1001", vin="2HGFC2F50KH500001",
            year=2022, make="Honda", model="Civic", trim="Sport", body="Sedan",
            mileage=24500, price=24900.0, status="available",
        ),
        Vehicle(
            dealer_id=d.id, stock_no="SA1002", vin="1FATP8UH1J5500002",
            year=2021, make="Ford", model="Mustang", trim="GT", body="Coupe",
            mileage=32000, price=35950.0, status="available",
        ),
    ]
    session.add_all(vehicles)
    session.commit()
    session.close()
    return d


def _make_client(db_engine, monkeypatch):
    import app.db as db_module
    TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "_SessionLocal", TestSession)
    monkeypatch.setattr(db_module, "_engine", db_engine)
    monkeypatch.setattr(db_module, "init_db", lambda url=None: None)
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


class TestFullLifecycle:
    """Complete lead lifecycle: webform → auto-reply → assign → claim → engage → opt-out."""

    def test_form_to_auto_reply(self, db_engine, monkeypatch):
        """Step 1: Web form submission -> lead created and the pipeline runs end-to-end
        (NEW -> AUTO_REPLIED -> ASSIGNED) since the speed-to-lead core loop is wired."""
        _make_full_dealer(db_engine)
        client = _make_client(db_engine, monkeypatch)

        resp = client.post("/webhook/form/e2e-token", json={
            "full_name": "Sarah Chen",
            "phone": "(604) 555-1234",
            "email": "sarah@example.com",
            "consent_sms": True,
            "vehicle_stock": "SA1001",
            "vehicle_title": "2022 Honda Civic Sport",
            "message": "Is the Civic still available? Could I see it this week?",
        })

        data = resp.json()
        assert data["status"] == "ok"
        # Pipeline is now wired end-to-end: NEW -> AUTO_REPLIED -> ASSIGNED
        assert data["state"] in ("AUTO_REPLIED", "ASSIGNED")
        assert data["dealer"] == "e2e-dealer"

        # Verify in DB
        TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
        session = TestSession()
        lead = session.get(Lead, data["lead_id"])
        assert lead is not None
        assert lead.name == "Sarah Chen"
        assert lead.phone == "+160****1234"
        assert lead.email == "sarah@example.com"
        assert lead.consent is True
        assert lead.vehicle_ref == "SA1001"
        # The lead should have advanced past AUTO_REPLIED via the wired pipeline
        assert lead.state in (LeadState.AUTO_REPLIED, LeadState.ASSIGNED)
        session.close()

    def test_form_triggers_outbound_message(self, db_engine, monkeypatch):
        """Step 2: Auto-reply should create an outbound Message record."""
        _make_full_dealer(db_engine)
        client = _make_client(db_engine, monkeypatch)

        resp = client.post("/webhook/form/e2e-token", json={
            "full_name": "Message Check",
            "phone": "(604) 555-5555",
            "consent_sms": True,
        })
        lead_id = resp.json()["lead_id"]

        TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
        session = TestSession()
        messages = session.execute(
            select(Message).where(Message.lead_id == lead_id, Message.direction == Direction.OUTBOUND)
        ).scalars().all()
        assert len(messages) >= 1, "Auto-reply should create at least one outbound message"
        session.close()

    def test_round_robin_assignment(self, db_engine, monkeypatch):
        """Step 3: Multiple leads should round-robin through the sales team.
        Pipeline now wires through to ASSIGNED, so the leads should be in ASSIGNED state."""
        _make_full_dealer(db_engine)
        client = _make_client(db_engine, monkeypatch)

        # Submit 3 leads - all should be ingested and advance through the pipeline
        lead_ids = []
        for i in range(3):
            resp = client.post("/webhook/form/e2e-token", json={
                "full_name": f"Round Robin {i}",
                "phone": f"(604) 555-{6000+i}",
                "consent_sms": True,
            })
            data = resp.json()
            assert data["status"] == "ok"
            lead_ids.append(data["lead_id"])

        # All 3 should have unique IDs and be in ASSIGNED (pipeline wires through)
        TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
        session = TestSession()
        assert len(set(lead_ids)) == 3
        for lid in lead_ids:
            lead = session.get(Lead, lid)
            assert lead is not None
            # Wired pipeline goes NEW -> AUTO_REPLIED -> ASSIGNED
            assert lead.state == LeadState.ASSIGNED
            assert lead.assigned_rep in ("Alex", "Jordan")
        session.close()

    def test_whatsapp_claim_flow(self, db_engine, monkeypatch):
        """Step 4: Rep claims lead via WhatsApp '1' reply.
        Pipeline already advances to ASSIGNED via round-robin, so we just verify the claim works."""
        _make_full_dealer(db_engine)
        client = _make_client(db_engine, monkeypatch)

        # Submit lead - the wired pipeline advances it to ASSIGNED via round-robin
        resp = client.post("/webhook/form/e2e-token", json={
            "full_name": "Claim Flow",
            "phone": "(604) 555-7777",
            "consent_sms": True,
        })
        lead_id = resp.json()["lead_id"]

        # Set assigned_rep to Alex (one of the round-robin reps) so the claim webhook
        # finds the right rep when they reply
        TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
        session = TestSession()
        lead = session.get(Lead, lead_id)
        lead.assigned_rep = "Alex"
        session.commit()
        session.close()

        # Claim via WhatsApp
        resp = client.post("/webhook/twilio/whatsapp", data={
            "From": "whatsapp:+160****0301",
            "To": "whatsapp:+177****0223",
            "Body": "1",
        })
        assert "claimed" in resp.text.lower()

        # Verify CLAIMED
        session = TestSession()
        lead = session.get(Lead, lead_id)
        assert lead.state == LeadState.CLAIMED
        session.close()

    def test_whatsapp_pass_flow(self, db_engine, monkeypatch):
        """Step 4b: Rep passes lead via WhatsApp '2' reply.
        Pipeline already advances to ASSIGNED via round-robin."""
        _make_full_dealer(db_engine)
        client = _make_client(db_engine, monkeypatch)

        # Submit lead
        resp = client.post("/webhook/form/e2e-token", json={
            "full_name": "Pass Flow",
            "phone": "(604) 555-7778",
            "consent_sms": True,
        })
        lead_id = resp.json()["lead_id"]

        # Ensure assigned_rep is Alex
        TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
        session = TestSession()
        lead = session.get(Lead, lead_id)
        lead.assigned_rep = "Alex"
        session.commit()
        session.close()

        # Pass via WhatsApp
        resp = client.post("/webhook/twilio/whatsapp", data={
            "From": "whatsapp:+160****0301",
            "To": "whatsapp:+177****0223",
            "Body": "2",
        })
        assert "passed" in resp.text.lower()

    def test_opt_out_full_flow(self, db_engine, monkeypatch):
        """Step 5: STOP keyword → OPTED_OUT state + ConsentLog entry."""
        _make_full_dealer(db_engine)
        client = _make_client(db_engine, monkeypatch)

        # Submit lead — phone normalizes (604) 555-8888 → +160****8888
        resp = client.post("/webhook/form/e2e-token", json={
            "full_name": "Opt Out Test",
            "phone": "(604) 555-8888",
            "consent_sms": True,
        })
        lead_id = resp.json()["lead_id"]

        # Send STOP — From must match the normalized phone
        resp = client.post("/webhook/twilio/sms", data={
            "From": "+160****8888",
            "To": "+177****0222",
            "Body": "STOP",
        })
        assert "unsubscribed" in resp.text.lower()

        # Verify OPTED_OUT
        TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
        session = TestSession()
        lead = session.get(Lead, lead_id)
        assert lead.state == LeadState.OPTED_OUT

        # Verify ConsentLog
        log = session.execute(
            select(ConsentLog).where(
                ConsentLog.phone == "+160****8888",
                ConsentLog.action == "opted_out",
            )
        ).scalars().first()
        assert log is not None
        session.close()

    def test_missed_call_textback(self, db_engine, monkeypatch):
        """Step 6: Missed call → auto SMS text-back mentioning dealer name."""
        _make_full_dealer(db_engine)
        client = _make_client(db_engine, monkeypatch)

        resp = client.post("/webhook/twilio/voice", data={
            "From": "+177****9999",
            "To": "+177****0222",
            "CallStatus": "no-answer",
        })
        assert resp.status_code == 200
        assert "E2E Motors" in resp.text
        assert "+160****0000" in resp.text  # Main phone in the reply

    def test_opt_out_arret_french(self, db_engine, monkeypatch):
        """Step 7: ARRET keyword also triggers opt-out (bilingual compliance)."""
        _make_full_dealer(db_engine)
        client = _make_client(db_engine, monkeypatch)

        # Phone normalizes (604) 555-9990 → +160****9990
        client.post("/webhook/form/e2e-token", json={
            "full_name": "French Opt Out",
            "phone": "(604) 555-9990",
            "consent_sms": True,
        })

        # From must match the normalized phone
        resp = client.post("/webhook/twilio/sms", data={
            "From": "+160****9990",
            "To": "+177****0222",
            "Body": "ARRET",
        })
        assert "unsubscribed" in resp.text.lower()

        TestSession = sessionmaker(bind=db_engine, expire_on_commit=False)
        session = TestSession()
        lead = session.execute(
            select(Lead).where(Lead.phone == "+160****9990")
        ).scalars().first()
        assert lead is not None
        assert lead.state == LeadState.OPTED_OUT
        session.close()

    def test_dashboard_shows_all_leads(self, db_engine, monkeypatch):
        """Step 8: Dashboard renders all submitted leads."""
        _make_full_dealer(db_engine)
        client = _make_client(db_engine, monkeypatch)

        # Submit a few leads
        for i in range(3):
            client.post("/webhook/form/e2e-token", json={
                "full_name": f"Dashboard Lead {i}",
                "phone": f"(604) 555-{4000+i}",
                "consent_sms": True,
            })

        resp = client.get("/dashboard/leads", cookies=make_auth_cookies("e2e-dealer"))
        assert resp.status_code == 200
        for i in range(3):
            assert f"Dashboard Lead {i}" in resp.text

    def test_lead_detail_page(self, db_engine, monkeypatch):
        """Step 9: Individual lead detail page renders with correct data."""
        _make_full_dealer(db_engine)
        client = _make_client(db_engine, monkeypatch)

        resp = client.post("/webhook/form/e2e-token", json={
            "full_name": "Detail Check",
            "phone": "(604) 555-4444",
            "email": "detail@example.com",
            "consent_sms": True,
            "vehicle_stock": "SA1001",
            "message": "Interested in the Civic!",
        })
        lead_id = resp.json()["lead_id"]

        resp = client.get(f"/dashboard/leads/{lead_id}", cookies=make_auth_cookies("e2e-dealer"))
        assert resp.status_code == 200
        assert "Detail Check" in resp.text
        assert "detail@example.com" in resp.text