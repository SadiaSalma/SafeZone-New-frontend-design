"""
Tests for Task 21: the simulated towers and virtual phones.
A small network (400 phones) keeps the tests quick.
"""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import shape

from app.config import settings
from app.db import database_status, get_db
from app.main import app
from app.modules.areas.service import find_area_ids, load_area_file
from app.modules.simulator.network import build_network
from app.security import hash_password
from app.setup_db import apply_schema

pytestmark = pytest.mark.skipif(
    not database_status()["ok"],
    reason="Database not running. Start it: Terminal -> Run Task -> 'SafeZone: start database'",
)
SAFE = {"X-SafeZone": "1"}


@pytest.fixture(scope="module", autouse=True)
def db():
    database = get_db()
    assert database.name == "safezone_test"
    database.client.drop_database(database.name)
    apply_schema(database)
    load_area_file(database)
    build_network(database, phones=400, seed=1)
    yield database
    database.client.drop_database(database.name)


def staff_browser(db, role="verifier"):
    phone = "+8801777000111" if role == "verifier" else "+8801777000112"
    if not db.users.find_one({"phone": phone}):
        db.users.insert_one({"name_en": "Sim Staff", "phone": phone,
                             "password_hash": hash_password("pass-1234"), "role": role, "status": "active",
                             "failed_logins": 0, "locked_until": None, "created_at": datetime.now(timezone.utc)})
    browser = TestClient(app)
    browser.post("/api/v1/auth/login", json={"phone": phone, "password": "pass-1234"}, headers=SAFE)
    return browser


def test_the_network_is_built(db):
    assert db.cell_towers.count_documents({}) > 300
    assert db.virtual_phones.count_documents({"is_test": False}) == 400
    assert db.cell_towers.find_one()["range_m"] == settings.tower_range_m


def test_every_phone_is_inside_dhaka(db):
    for phone in db.virtual_phones.find().limit(100):
        lng, lat = phone["location"]["coordinates"]
        assert find_area_ids(lat, lng)["thana_id"] is not None


def test_every_phone_uses_its_nearest_tower(db):
    for phone in db.virtual_phones.find().limit(40):
        closest = db.cell_towers.find_one({"location": {"$nearSphere": {"$geometry": phone["location"]}}})
        assert phone["tower_id"] == closest["_id"]


def test_every_thana_is_covered_by_a_tower(db):
    for thana in db.areas.find({"type": "thana"}):
        middle = shape(thana["geom"]).representative_point()
        point = {"type": "Point", "coordinates": [middle.x, middle.y]}
        reach = db.cell_towers.find_one({"location": {"$nearSphere": {"$geometry": point, "$maxDistance": settings.tower_range_m}}})
        assert reach is not None, thana["name_en"]


def test_same_seed_same_network_and_test_phones_survive(db):
    first = [p["location"]["coordinates"] for p in db.virtual_phones.find({"is_test": False}).sort("_id", 1).limit(5)]
    test_phone_id = db.virtual_phones.insert_one({
        "location": {"type": "Point", "coordinates": [90.4047, 23.7457]}, "tower_id": db.cell_towers.find_one()["_id"],
        "is_test": True, "owner_id": None, "label": "Admin test phone"}).inserted_id

    build_network(db, phones=400, seed=1)
    again = [p["location"]["coordinates"] for p in db.virtual_phones.find({"is_test": False}).sort("_id", 1).limit(5)]
    assert again == first  # repeatable for demos and tests
    kept = db.virtual_phones.find_one({"_id": test_phone_id})
    assert kept is not None  # the admin's test phone was kept...
    assert db.cell_towers.find_one({"_id": kept["tower_id"]}) is not None  # ...and joined to a NEW tower
    db.virtual_phones.delete_one({"_id": test_phone_id})

    build_network(db, phones=400, seed=2)
    other = [p["location"]["coordinates"] for p in db.virtual_phones.find({"is_test": False}).sort("_id", 1).limit(5)]
    assert other != first
    build_network(db, phones=400, seed=1)


def test_staff_only(db):
    assert TestClient(app).get("/api/v1/admin/simulator/network").status_code == 401


def test_network_summary_and_phones_in_view(db):
    staff = staff_browser(db)
    summary = staff.get("/api/v1/admin/simulator/network").json()
    assert summary["phones"] == 400 and len(summary["towers"]) == db.cell_towers.count_documents({})
    assert sum(t["phones"] for t in summary["towers"]) == 400
    view = staff.get("/api/v1/admin/simulator/phones",
                     params={"south": 23.73, "west": 90.38, "north": 23.76, "east": 90.42}).json()
    assert view["phones"] and all(23.73 <= p["lat"] <= 23.76 and 90.38 <= p["lng"] <= 90.42 for p in view["phones"])
