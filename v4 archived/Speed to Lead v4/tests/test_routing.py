"""Phase 4 — round-robin rotation. Runs today against engine.router.next_rep."""

from __future__ import annotations

from types import SimpleNamespace

from app.engine.router import next_rep


def _dealer(pointer=0):
    return SimpleNamespace(round_robin_pointer=pointer)


def test_rotates_evenly_across_active_reps():
    dealer = _dealer()
    team = [
        {"name": "Mike", "phone": "+1", "active": True},
        {"name": "Dana", "phone": "+2", "active": True},
    ]
    picks = [next_rep(dealer, team)["name"] for _ in range(4)]
    assert picks == ["Mike", "Dana", "Mike", "Dana"]


def test_skips_inactive_reps():
    dealer = _dealer()
    team = [
        {"name": "Mike", "phone": "+1", "active": True},
        {"name": "Priya", "phone": "+3", "active": False},
        {"name": "Dana", "phone": "+2", "active": True},
    ]
    picks = {next_rep(dealer, team)["name"] for _ in range(6)}
    assert picks == {"Mike", "Dana"}
    assert "Priya" not in picks


def test_empty_team_returns_none():
    assert next_rep(_dealer(), []) is None
    assert next_rep(_dealer(), [{"name": "X", "phone": "+1", "active": False}]) is None
