"""Phase 2: Telegram free-text router tests.

All Telegram sends and LLM calls are mocked — never real.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _make_manager_session() -> str:
    from app.dashboard import _get_serializer
    return _get_serializer().dumps({
        "role": "manager",
        "rep_name": "",
        "dealer_slug": "premier-auto",
        "ts": 0,
    })


@pytest.fixture
def client(tmp_path):
    """TestClient backed by SQLite with premier-auto provisioned."""
    import app.db as db
    from app.main import _auto_provision_dealers, app

    db_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    db.init_db(db_url)
    db.get_session_factory(db_url)
    _auto_provision_dealers()

    try:
        yield TestClient(app)
    finally:
        db._engine = None
        db._SessionLocal = None


@pytest.fixture(autouse=True)
def _clear_confirmation_cache():
    """Clear the module-level confirmation cache before each test to avoid pollution."""
    from app.telegram_free_text import _CONFIRMATION_CACHE
    _CONFIRMATION_CACHE.clear()
    yield


def _mock_llm_classification(intent: str, params: dict | None = None):
    """Return a mock OpenAI response that classifies as the given intent."""
    result = {"intent": intent, "params": params or {}}
    import json
    mock_message = MagicMock()
    mock_message.content = json.dumps(result)
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


# ── Availability confirmation cycle ─────────────────────────────────────────

@patch("app.transports.telegram.TelegramTransport.send")
def test_availability_message_asks_confirmation(mock_send, client):
    """Availability message → confirmation reply sent, nothing written to config yet."""
    import app.db as db
    from app.models import Dealer
    from sqlalchemy import select

    mock_client = _mock_llm_classification("availability", {
        "date": "2026-07-10",
        "start": "14:00",
        "end": "16:00",
        "note": "dentist",
    })
    with patch("app.telegram_free_text.classify_message") as mock_classify:
        mock_classify.return_value = {"intent": "availability", "params": {
            "date": "2026-07-10", "start": "14:00", "end": "16:00", "note": "dentist",
        }}

        payload = {
            "message": {
                "text": "not free 2-4 Friday",
                "from": {"username": "Helly"},
                "chat": {"id": "8990699115"},
            }
        }
        response = client.post("/webhook/telegram", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is True
        assert data.get("action") == "availability_pending"

    # Verify confirmation text was sent back
    mock_send.assert_called_once()
    call_args = mock_send.call_args
    assert call_args[1]["to"] == "8990699115"
    assert "Confirm?" in call_args[1]["body"]

    # Verify nothing was written to config yet
    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        helly = next(r for r in (dealer.config or {}).get("sales_team", []) if r.get("name") == "Helly")
        assert "unavailable_windows" not in helly or helly["unavailable_windows"] == [], \
            "Availability should NOT be committed before confirmation"
    finally:
        session.close()


@patch("app.transports.telegram.TelegramTransport.send")
def test_availability_confirm_writes_window(mock_send, client):
    """Confirmation reply after availability → window now present in dealer.config."""
    import app.db as db
    from app.models import Dealer
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified
    import json as _json

    # First, send the availability message and capture the pending state
    with patch("app.telegram_free_text.classify_message") as mock_classify:
        mock_classify.return_value = {"intent": "availability", "params": {
            "date": "2026-07-10", "start": "14:00", "end": "16:00", "note": "",
        }}
        payload = {
            "message": {
                "text": "not free 2-4 Friday",
                "from": {"username": "Helly"},
                "chat": {"id": "8990699115"},
            }
        }
        client.post("/webhook/telegram", json=payload)

    # Clear the mock call tracking
    mock_send.reset_mock()

    # Now send a confirmation
    payload_confirm = {
        "message": {
            "text": "yes",
            "from": {"username": "Helly"},
            "chat": {"id": "8990699115"},
        }
    }
    response = client.post("/webhook/telegram", json=payload_confirm)
    assert response.status_code == 200
    data = response.json()
    assert data.get("action") == "availability_confirmed"

    # Verify the window is now in config
    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        helly = next(r for r in (dealer.config or {}).get("sales_team", []) if r.get("name") == "Helly")
        windows = helly.get("unavailable_windows", [])
        assert len(windows) == 1
        assert windows[0]["date"] == "2026-07-10"
        assert windows[0]["start"] == "14:00"
    finally:
        session.close()


@patch("app.transports.telegram.TelegramTransport.send")
def test_availability_deny_cancels(mock_send, client):
    """Non-confirmation reply after availability prompt cancels the pending window."""
    import app.db as db
    from app.models import Dealer
    from sqlalchemy import select

    with patch("app.telegram_free_text.classify_message") as mock_classify:
        mock_classify.return_value = {"intent": "availability", "params": {
            "date": "2026-07-10", "start": "14:00", "end": "16:00", "note": "",
        }}
        payload = {
            "message": {
                "text": "not free 2-4 Friday",
                "from": {"username": "Helly"},
                "chat": {"id": "8990699115"},
            }
        }
        client.post("/webhook/telegram", json=payload)

    mock_send.reset_mock()

    # Send "no" instead of confirming
    payload_deny = {
        "message": {
            "text": "never mind",
            "from": {"username": "Helly"},
            "chat": {"id": "8990699115"},
        }
    }
    response = client.post("/webhook/telegram", json=payload_deny)
    assert response.status_code == 200
    data = response.json()
    assert data.get("action") == "availability_cancelled"

    # Verify no window was written
    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        helly = next(r for r in (dealer.config or {}).get("sales_team", []) if r.get("name") == "Helly")
        assert "unavailable_windows" not in helly or helly["unavailable_windows"] == []
    finally:
        session.close()


# ── New lead ─────────────────────────────────────────────────────────────────

@patch("app.transports.telegram.TelegramTransport.send")
def test_new_lead_creates_lead(mock_send, client):
    """New-lead message → a Lead row is created with correct name/phone/vehicle_ref."""
    import app.db as db
    from app.models import Lead
    from sqlalchemy import select

    with patch("app.telegram_free_text.classify_message") as mock_classify:
        mock_classify.return_value = {"intent": "new_lead", "params": {
            "name": "John Doe",
            "phone": "604-555-1234",
            "vehicle_ref": "Civic",
        }}

        payload = {
            "message": {
                "text": "new lead, John Doe, wants a Civic, 604-555-1234",
                "from": {"username": "Helly"},
                "chat": {"id": "8990699115"},
            }
        }
        response = client.post("/webhook/telegram", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is True

    # Verify a Lead was created
    session = db.get_session_factory()()
    try:
        lead = session.execute(
            select(Lead).where(Lead.name == "John Doe")
        ).scalars().first()
        assert lead is not None, "Lead should have been created"
        assert lead.phone == "604-555-1234"
        assert lead.vehicle_ref == "Civic"
        # Should be assigned to the rep who submitted
        assert lead.assigned_rep == "Helly"
    finally:
        session.close()

    # Should have sent a confirmation reply
    mock_send.assert_called_once()
    call_args = mock_send.call_args
    assert "John Doe" in call_args[1]["body"]
    assert "Civic" in call_args[1]["body"]


# ── Garbage/unrelated messages ──────────────────────────────────────────────

@patch("app.transports.telegram.TelegramTransport.send")
def test_garbage_message_no_action(mock_send, client):
    """Garbage/unrelated message → no lead, no availability change, help reply only."""
    import app.db as db
    from app.models import Lead
    from sqlalchemy import select

    initial_count = session_count(db, Lead)

    with patch("app.telegram_free_text.classify_message") as mock_classify:
        mock_classify.return_value = {"intent": "unknown", "params": {}}

        payload = {
            "message": {
                "text": "what's the weather like?",
                "from": {"username": "Helly"},
                "chat": {"id": "8990699115"},
            }
        }
        response = client.post("/webhook/telegram", json=payload)
        assert response.status_code == 200

    # No new lead
    assert session_count(db, Lead) == initial_count

    # Help reply sent
    mock_send.assert_called_once()
    call_args = mock_send.call_args
    assert "didn't understand" in call_args[1]["body"].lower() or "can" in call_args[1]["body"].lower()


def session_count(db, model):
    """Count rows in a table."""
    from sqlalchemy import select, func
    session = db.get_session_factory()()
    try:
        return session.execute(select(func.count()).select_from(model)).scalar()
    finally:
        session.close()


# ── Unrecognized chat_id ────────────────────────────────────────────────────

@patch("app.transports.telegram.TelegramTransport.send")
def test_unrecognized_chat_id_ignored(mock_send, client):
    """Message from unknown chat_id → not processed, ignored/logged."""
    import app.db as db
    from app.models import Lead
    from sqlalchemy import select

    initial_count = session_count(db, Lead)

    # Use a chat_id that doesn't match any rep
    payload = {
        "message": {
            "text": "new lead, John Doe, wants a Civic",
            "from": {"username": "stranger"},
            "chat": {"id": "999999999"},
        }
    }
    response = client.post("/webhook/telegram", json=payload)
    assert response.status_code == 200
    data = response.json()
    # Should fall through to "unknown" since no rep matched
    assert data.get("action") == "unknown"

    # No new lead created
    assert session_count(db, Lead) == initial_count


# ── No-show reply ───────────────────────────────────────────────────────────

@patch("app.transports.telegram.TelegramTransport.send")
def test_no_show_reply_no_active_nudge(mock_send, client):
    """No-show reply without an active nudge → guidance message."""
    with patch("app.telegram_free_text.classify_message") as mock_classify:
        mock_classify.return_value = {"intent": "no_show_reply", "params": {"status": "showed"}}

        payload = {
            "message": {
                "text": "he showed",
                "from": {"username": "Helly"},
                "chat": {"id": "8990699115"},
            }
        }
        response = client.post("/webhook/telegram", json=payload)
        assert response.status_code == 200

    # Should say no appointments need confirmation
    mock_send.assert_called_once()
    call_args = mock_send.call_args
    assert "don't see" in call_args[1]["body"].lower() or "any" in call_args[1]["body"].lower()
