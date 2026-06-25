"""Inventory upload feature: manager uploads CSV -> full specs land in Vehicle
table -> check_inventory (what the AI calls) surfaces them.

Covers the enhancement that captures horsepower / fuel_economy / features /
photos, not just engine/transmission/drivetrain.
"""
from __future__ import annotations

import io
import time

from fastapi.testclient import TestClient

from app.main import app


def _manager_cookie(dealer_slug="premier-auto"):
    from app.dashboard import _get_serializer
    token = _get_serializer().dumps(
        {"role": "manager", "rep_name": "Manager", "dealer_slug": dealer_slug, "ts": time.time()}
    )
    return {"session": token}


def _client(tmp_path):
    import app.db as db
    from app.main import _auto_provision_dealers

    db_url = f"sqlite:///{(tmp_path / 'inv.db').as_posix()}"
    db.init_db(db_url)
    db.get_session_factory(db_url)
    _auto_provision_dealers()
    return TestClient(app)


CSV = (
    "stock_no,year,make,model,trim,body,price,mileage,engine,transmission,drivetrain,"
    "horsepower,torque,fuel_economy,exterior_color,interior_color,features,image_url\n"
    "PAG011,2023,Toyota,RAV4,XLE,SUV,34995,15800,2.5L 4-cylinder,8-speed automatic,AWD,"
    "203,184 lb-ft,8.0 L/100km,Magnetic Grey Metallic,Black SofTex,"
    'Toyota Safety Sense 2.5+|Blind Spot Monitor|Power Liftgate,'
    "https://example.com/rav4.jpg\n"
    "PAG013,2023,Hyundai,Tucson,Preferred,SUV,29900,12000,2.5L 4-cylinder,8-speed automatic,AWD,"
    "187,178 lb-ft,8.8 L/100km,Amazon Gray,Black cloth,Apple CarPlay|Heated Seats,\n"
)


def test_manager_upload_csv_lands_full_specs_and_ai_can_find_it(tmp_path):
    client = _client(tmp_path)

    files = {"file": ("inventory.csv", io.BytesIO(CSV.encode("utf-8")), "text/csv")}
    r = client.post("/dashboard/inventory/upload", files=files, cookies=_manager_cookie())
    assert r.status_code == 200, r.text
    assert "2 vehicles uploaded" in r.text, r.text

    # Specs landed in the Vehicle table
    import app.db as db
    from sqlalchemy import select
    from app.models import Vehicle, Dealer

    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        rav4 = session.execute(
            select(Vehicle).where(Vehicle.dealer_id == dealer.id, Vehicle.stock_no == "PAG011")
        ).scalars().first()
        assert rav4 is not None
        assert rav4.raw.get("horsepower") == "203"
        assert rav4.raw.get("fuel_economy") == "8.0 L/100km"
        assert "Power Liftgate" in (rav4.raw.get("features") or [])
        assert rav4.photos == ["https://example.com/rav4.jpg"]

        # check_inventory (the AI's tool) surfaces it
        from tools.check_inventory import search
        hits = search(session, dealer.id, make="Toyota", query="RAV4", limit=5)
        assert any(v.stock_no == "PAG011" for v in hits), "AI inventory search can't find the RAV4"
    finally:
        session.close()


def test_search_matches_multiword_query(tmp_path):
    """The AI often passes a natural phrase ('2023 Toyota RAV4 XLE'); search must
    resolve it to the car even though make/model/trim/year are separate columns."""
    client = _client(tmp_path)
    files = {"file": ("inventory.csv", io.BytesIO(CSV.encode("utf-8")), "text/csv")}
    r = client.post("/dashboard/inventory/upload", files=files, cookies=_manager_cookie())
    assert r.status_code == 200, r.text

    import app.db as db
    from sqlalchemy import select
    from app.models import Dealer
    from tools.check_inventory import search

    session = db.get_session_factory()()
    try:
        dealer = session.execute(select(Dealer).where(Dealer.slug == "premier-auto")).scalars().first()
        for q in ["2023 Toyota RAV4 XLE", "Toyota RAV4 XLE", "RAV4 XLE", "2023 RAV4", "rav4"]:
            hits = search(session, dealer.id, query=q, limit=5)
            assert any(v.stock_no == "PAG011" for v in hits), f"query {q!r} failed to find the RAV4"
        # make + multiword query together (how the AI is prompted to call it)
        hits = search(session, dealer.id, make="Toyota", query="RAV4 XLE", limit=5)
        assert any(v.stock_no == "PAG011" for v in hits), "make+query combo failed"
    finally:
        session.close()


def test_upload_requires_manager_auth(tmp_path):
    client = _client(tmp_path)
    files = {"file": ("inventory.csv", io.BytesIO(CSV.encode("utf-8")), "text/csv")}
    # No cookie -> require_auth raises a 303 redirect to login (don't follow it).
    r = client.post("/dashboard/inventory/upload", files=files, follow_redirects=False)
    assert r.status_code == 303, r.status_code
    assert "/dashboard/login" in r.headers.get("location", "")
