"""Inventory sync: full-sync, status column, manual mark-sold/relist, AI exclusion."""

from __future__ import annotations

import io
import time

from fastapi.testclient import TestClient
from app.main import app


def _manager_cookie(dealer_slug="premier-auto"):
    from app.dashboard import _get_serializer
    return {"session": _get_serializer().dumps(
        {"role": "manager", "rep_name": "Manager", "dealer_slug": dealer_slug, "ts": time.time()})}


def _client(tmp_path):
    import app.db as db
    from app.main import _auto_provision_dealers
    url = f"sqlite:///{(tmp_path / 'inv.db').as_posix()}"
    db.init_db(url)
    db.get_session_factory(url)
    _auto_provision_dealers()
    return TestClient(app)


def _upload(client, csv, full_sync=False):
    data = {"full_sync": "on"} if full_sync else {}
    return client.post("/dashboard/inventory/upload",
        files={"file": ("inv.csv", io.BytesIO(csv.encode()), "text/csv")},
        data=data, cookies=_manager_cookie())


HDR = "stock_no,year,make,model,trim,body,price,mileage\n"


def _row(stock, mk, md):
    return f"{stock},2023,{mk},{md},XLE,SUV,30000,10000\n"


def test_merge_mode_keeps_absent_cars(tmp_path):
    """Upload [A,B,C], then [B,D] — all four should be available."""
    client = _client(tmp_path)
    r = _upload(client, HDR + _row("A", "Toyota", "Camry") + _row("B", "Honda", "Civic") + _row("C", "Ford", "Focus"))
    assert r.status_code == 200
    r = _upload(client, HDR + _row("B", "Honda", "Civic") + _row("D", "Nissan", "Altima"))
    assert r.status_code == 200

    import app.db as db
    from sqlalchemy import select
    from app.models import Vehicle, Dealer
    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        for stock in ("A", "B", "C", "D"):
            v = session.execute(
                select(Vehicle).where(Vehicle.dealer_id == dealer.id, Vehicle.stock_no == stock)
            ).scalars().first()
            assert v is not None, f"{stock} not found"
            assert v.status == "available", f"{stock} status should be available, got {v.status}"
        from tools.check_inventory import search
        hits = search(session, dealer.id, query="Camry", limit=10)
        assert any(v.stock_no == "A" for v in hits), "Camry (stock A) should be in AI search"
    finally:
        session.close()


def test_full_sync_removes_absent_cars(tmp_path):
    """Upload [A,B,C], then [A,B] with full_sync → C should be removed."""
    client = _client(tmp_path)
    r = _upload(client, HDR + _row("A", "Toyota", "Camry") + _row("B", "Honda", "Civic") + _row("C", "Ford", "Focus"))
    assert r.status_code == 200
    r = _upload(client, HDR + _row("A", "Toyota", "Camry") + _row("B", "Honda", "Civic"), full_sync=True)
    assert r.status_code == 200

    import app.db as db
    from sqlalchemy import select
    from app.models import Vehicle, Dealer
    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        v = session.execute(
            select(Vehicle).where(Vehicle.dealer_id == dealer.id, Vehicle.stock_no == "C")
        ).scalars().first()
        assert v is not None
        assert v.status == "removed", f"C should be removed, got {v.status}"
        from tools.check_inventory import search
        hits = search(session, dealer.id, query="Focus", limit=10)
        assert not any(v.stock_no == "C" for v in hits), "Focus (stock C) should NOT be in AI search"
    finally:
        session.close()


def test_full_sync_scopes_to_current_dealer(tmp_path):
    """Full sync for premier-auto must not affect another dealer's vehicles."""
    client = _client(tmp_path)

    import app.db as db
    from sqlalchemy import select
    from app.models import Vehicle, Dealer

    r = _upload(client, HDR + _row("X1", "Toyota", "Camry"))
    assert r.status_code == 200

    session = db.get_session_factory()()
    try:
        other_dealer = Dealer(
            slug="other-dealer", name="Other Motors",
            sms_number="+17788889999",
        )
        session.add(other_dealer)
        session.flush()
        other_vehicle = Vehicle(
            dealer_id=other_dealer.id, stock_no="OTHER1", year=2023, make="Tesla", model="Model 3",
            price=40000, mileage=5000, status="available",
        )
        session.add(other_vehicle)
        session.commit()
        other_id = other_vehicle.id
    finally:
        session.close()

    r = _upload(client, HDR + _row("X1", "Toyota", "Camry"), full_sync=True)
    assert r.status_code == 200

    session = db.get_session_factory()()
    try:
        other_vehicle = session.get(Vehicle, other_id)
        assert other_vehicle is not None
        assert other_vehicle.status == "available", "Other dealer's vehicle should still be available"
    finally:
        session.close()


def test_status_column_marks_sold(tmp_path):
    """Upload CSV with status column — sold row should be excluded from AI."""
    client = _client(tmp_path)
    csv = "stock_no,year,make,model,status,price,mileage\n" \
          "S1,2023,Toyota,Camry,sold,30000,10000\n" \
          "S2,2023,Honda,Civic,,25000,8000\n"
    r = _upload(client, csv)
    assert r.status_code == 200

    import app.db as db
    from sqlalchemy import select
    from app.models import Vehicle, Dealer
    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        v1 = session.execute(
            select(Vehicle).where(Vehicle.dealer_id == dealer.id, Vehicle.stock_no == "S1")
        ).scalars().first()
        assert v1 is not None
        assert v1.status == "sold", f"S1 should be sold, got {v1.status}"
        v2 = session.execute(
            select(Vehicle).where(Vehicle.dealer_id == dealer.id, Vehicle.stock_no == "S2")
        ).scalars().first()
        assert v2 is not None
        assert v2.status == "available", f"S2 should be available, got {v2.status}"
        from tools.check_inventory import search
        hits = search(session, dealer.id, query="Toyota", limit=10)
        assert not any(v.stock_no == "S1" for v in hits), "Sold car should not be in AI search"
    finally:
        session.close()


def test_manual_mark_sold_and_relist(tmp_path):
    """Upload [A], mark sold, then relist."""
    client = _client(tmp_path)
    r = _upload(client, HDR + _row("A", "Toyota", "Camry"))
    assert r.status_code == 200

    r = client.post("/dashboard/inventory/A/status", data={"status": "sold"}, cookies=_manager_cookie())
    assert r.status_code == 200

    import app.db as db
    from sqlalchemy import select
    from app.models import Vehicle, Dealer
    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        v = session.execute(
            select(Vehicle).where(Vehicle.dealer_id == dealer.id, Vehicle.stock_no == "A")
        ).scalars().first()
        assert v is not None
        assert v.status == "sold", f"A should be sold, got {v.status}"
        from tools.check_inventory import search
        hits = search(session, dealer.id, query="Camry", limit=10)
        assert not any(v.stock_no == "A" for v in hits), "Sold car should not be in AI search"
    finally:
        session.close()

    r = client.post("/dashboard/inventory/A/status", data={"status": "available"}, cookies=_manager_cookie())
    assert r.status_code == 200

    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        from tools.check_inventory import search
        hits = search(session, dealer.id, query="Camry", limit=10)
        assert any(v.stock_no == "A" for v in hits), "Relisted car should be back in AI search"
    finally:
        session.close()


def test_check_inventory_excludes_sold_and_removed(tmp_path):
    """Directly insert sold/removed vehicles — search must not return them."""
    import app.db as db
    from sqlalchemy import select
    from app.models import Vehicle, Dealer

    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        for tag, st in [("SOLD1", "sold"), ("REM1", "removed"), ("AVAIL1", "available")]:
            v = Vehicle(
                dealer_id=dealer.id, stock_no=tag, year=2023, make="Test", model=tag,
                price=10000, mileage=1000, status=st,
            )
            session.add(v)
        session.commit()

        from tools.check_inventory import search
        for q in ["SOLD1", "REM1", "Test SOLD1", "Test REM1"]:
            hits = search(session, dealer.id, query=q, limit=10)
            assert not any(v.stock_no == "SOLD1" for v in hits), f"SOLD1 should be excluded from query {q!r}"
            assert not any(v.stock_no == "REM1" for v in hits), f"REM1 should be excluded from query {q!r}"
        hits = search(session, dealer.id, query="AVAIL1", limit=10)
        assert any(v.stock_no == "AVAIL1" for v in hits), "Available car should be in AI search"
    finally:
        session.close()


def test_status_endpoint_requires_manager(tmp_path):
    """Non-manager must get 401/403 and vehicle status must not change."""
    client = _client(tmp_path)
    # Upload a vehicle first
    from app.dashboard import _get_serializer
    r = _upload(client, HDR + _row("SEC1", "Toyota", "Camry"))
    assert r.status_code == 200

    # No cookie → 303 redirect
    r = client.post("/dashboard/inventory/SEC1/status", data={"status": "sold"}, follow_redirects=False)
    assert r.status_code == 303

    # Rep cookie → 403
    rep_cookie = {"session": _get_serializer().dumps(
        {"role": "rep", "rep_name": "Bob", "dealer_slug": "premier-auto", "ts": time.time()})}
    r = client.post("/dashboard/inventory/SEC1/status", data={"status": "sold"}, cookies=rep_cookie)
    assert r.status_code == 403

    import app.db as db
    from sqlalchemy import select
    from app.models import Vehicle, Dealer
    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        v = session.execute(
            select(Vehicle).where(Vehicle.dealer_id == dealer.id, Vehicle.stock_no == "SEC1")
        ).scalars().first()
        assert v is not None
        assert v.status == "available", "Status should NOT have changed"
    finally:
        session.close()


def test_reupload_no_duplicate_stock(tmp_path):
    """Upload [A] twice — exactly one Vehicle row with stock_no A."""
    client = _client(tmp_path)
    r = _upload(client, HDR + _row("A", "Toyota", "Camry"))
    assert r.status_code == 200
    r = _upload(client, HDR + _row("A", "Toyota", "Camry"))
    assert r.status_code == 200

    import app.db as db
    from sqlalchemy import select, func
    from app.models import Vehicle, Dealer
    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        count = session.execute(
            select(func.count(Vehicle.id)).where(
                Vehicle.dealer_id == dealer.id, Vehicle.stock_no == "A"
            )
        ).scalar()
        assert count == 1, f"Expected 1 row for stock A, got {count}"
    finally:
        session.close()
