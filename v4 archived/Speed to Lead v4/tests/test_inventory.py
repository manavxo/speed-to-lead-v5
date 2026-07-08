"""Phase 2 — inventory ladder + grounding (Axis 1).

Tests the feed adapter, field mapping, sync_inventory, and grounding via check_inventory.
"""

from __future__ import annotations

from pathlib import Path

from app.adapters.inventory.discovery import LADDER, discover
from app.adapters.inventory.feed import FeedSource
from app.adapters.inventory.mapping import map_row
from app.models import Dealer, Vehicle
from tools.check_inventory import resolve_vehicle, search
from tools.sync_inventory import sync_inventory


def test_discovery_returns_a_recommendation_shape():
    result = discover("https://sunriseauto.example.ca/inventory")
    assert set(result) == {"kind", "confidence", "scores"}
    assert result["kind"] in {a.kind for a in LADDER}


def test_manual_is_the_universal_floor():
    kinds = [a.kind for a in LADDER]
    assert kinds[-1] == "manual"


def test_feed_fetch_maps_google_vehicle_ads_csv(root):
    src = FeedSource(dealer_slug="demo-auto", url=str(root / "tests/fixtures/inventory_feed.csv"))
    vehicles = src.fetch()
    assert len(vehicles) == 5
    civic = next(v for v in vehicles if v.stock_no == "SA1001")
    assert civic.year == 2019 and civic.make == "Honda" and civic.price == 18900
    assert civic.vin == "2HGFC2F50KH500001"
    assert civic.body == "Sedan"


def test_feed_fetch_with_auto_mapping(root):
    """Auto mapping should resolve Google Vehicle Ads columns without explicit config."""
    src = FeedSource(dealer_slug="demo-auto", url=str(root / "tests/fixtures/inventory_feed.csv"))
    vehicles = src.fetch()
    mustang = next(v for v in vehicles if v.stock_no == "SA1002")
    assert mustang.make == "Ford"
    assert mustang.model == "Mustang"
    assert mustang.trim == "GT"
    assert mustang.mileage == 52000


def test_map_row_known_columns():
    row = {
        "vin": "ABC123",
        "stock": "S001",
        "year": "2022",
        "make": "Toyota",
        "model": "Camry",
        "trim": "LE",
        "body_style": "Sedan",
        "mileage": "15000",
        "price": "25000",
        "state_of_vehicle": "used",
        "vehicle_url": "https://example.com/car",
        "image_url": "https://example.com/img.jpg",
    }
    vr = map_row(row, "auto")
    assert vr.vin == "ABC123"
    assert vr.stock_no == "S001"
    assert vr.year == 2022
    assert vr.price == 25000.0
    assert vr.status == "available"


def test_sync_inventory_upserts_and_marks_sold(db_session):
    """Sync 3 vehicles, then re-sync with only 2 — the missing one should be marked sold."""
    dealer = Dealer(slug="test-dealer", name="Test", config={})
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    # First sync: 3 vehicles
    records = FeedSource(
        dealer_slug="test-dealer",
        url=str(Path(__file__).resolve().parents[0] / "fixtures" / "inventory_feed.csv"),
    ).fetch()
    result = sync_inventory(db_session, dealer, records[:3])
    assert result["upserted"] == 3
    assert result["stale"] is False

    # Check they're in DB
    vehicles = db_session.query(Vehicle).filter(Vehicle.dealer_id == dealer.id).all()
    assert len(vehicles) == 3
    assert all(v.status == "available" for v in vehicles)

    # Second sync: only 2 vehicles (third is gone)
    result2 = sync_inventory(db_session, dealer, records[:2])
    assert result2["marked_sold"] == 1

    vehicles = db_session.query(Vehicle).filter(Vehicle.dealer_id == dealer.id).all()
    sold = [v for v in vehicles if v.status == "sold"]
    assert len(sold) == 1
    assert sold[0].stock_no == "SA1003"


def test_sync_inventory_is_idempotent(db_session):
    """Running the same sync twice should not duplicate vehicles."""
    dealer = Dealer(slug="test-dealer", name="Test", config={})
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    records = FeedSource(
        dealer_slug="test-dealer",
        url=str(Path(__file__).resolve().parents[0] / "fixtures" / "inventory_feed.csv"),
    ).fetch()

    sync_inventory(db_session, dealer, records)
    sync_inventory(db_session, dealer, records)

    vehicles = db_session.query(Vehicle).filter(Vehicle.dealer_id == dealer.id).all()
    assert len(vehicles) == 5


def test_grounding_resolve_vehicle_returns_none_for_unknown(db_session):
    """An unknown vehicle_ref must resolve to None — the AI must refuse/redirect, never invent."""
    dealer = Dealer(slug="test-dealer", name="Test", config={})
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    result = resolve_vehicle(db_session, dealer.id, "DOES-NOT-EXIST")
    assert result is None


def test_grounding_resolve_vehicle_finds_by_stock_no(db_session):
    dealer = Dealer(slug="test-dealer", name="Test", config={})
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    records = FeedSource(
        dealer_slug="test-dealer",
        url=str(Path(__file__).resolve().parents[0] / "fixtures" / "inventory_feed.csv"),
    ).fetch()
    sync_inventory(db_session, dealer, records)

    result = resolve_vehicle(db_session, dealer.id, "SA1001")
    assert result is not None
    assert result.make == "Honda"
    assert result.price == 18900


def test_search_returns_matching_vehicles(db_session):
    dealer = Dealer(slug="test-dealer", name="Test", config={})
    db_session.add(dealer)
    db_session.commit()
    db_session.refresh(dealer)

    records = FeedSource(
        dealer_slug="test-dealer",
        url=str(Path(__file__).resolve().parents[0] / "fixtures" / "inventory_feed.csv"),
    ).fetch()
    sync_inventory(db_session, dealer, records)

    # Search by body style
    suvs = search(db_session, dealer.id, body="SUV")
    assert len(suvs) == 1
    assert suvs[0].model == "RAV4"

    # Search by max price
    cheap = search(db_session, dealer.id, max_price=15000)
    assert all(v.price <= 15000 for v in cheap)

    # Search by keyword
    hondas = search(db_session, dealer.id, query="Honda")
    assert len(hondas) == 1
    assert hondas[0].stock_no == "SA1001"


