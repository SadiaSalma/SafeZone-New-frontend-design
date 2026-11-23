"""
Tests for Task 26: one area's safety dashboard and the grid hotspots.
Thefts are put straight into the test database as VERIFIED reports, at chosen places and times.
"""
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.db import database_status, get_db
from app.main import app
from app.modules.areas.service import find_area_ids, load_area_file
from app.modules.public.dashboard import hotspots
from app.setup_db import apply_schema

pytestmark = pytest.mark.skipif(
    not database_status()["ok"],
    reason="Database not running. Start it: Terminal -> Run Task -> 'SafeZone: start database'",
)
DHAKA = timezone(timedelta(hours=6))
visitor = TestClient(app)
NOW = datetime.now(timezone.utc)


@pytest.fixture(scope="module", autouse=True)
def db():
    database = get_db()
    assert database.name == "safezone_test"
    database.client.drop_database(database.name)
    apply_schema(database)
    load_area_file(database)
    yield database
    database.client.drop_database(database.name)


@pytest.fixture(autouse=True)
def clean(db):
    db.reports.delete_many({})


_gd = iter(range(1000, 9999))


def theft(db, lat, lng, when, theft_type="phone_snatching", status="ALERTED"):
    """A verified theft whose public point is (lat, lng)."""
    ids = find_area_ids(lat, lng)
    point = {"type": "Point", "coordinates": [lng, lat]}
    db.reports.insert_one({
        "user_id": None, "status": status, "theft_type": theft_type, "occurred_at": when, "submitted_at": when,
        "location": point, "public_location": point, **ids,
        "gd": {"type": "GD", "number": str(next(_gd)), "date": when, "police_station_id": None},
        "gd_hash": str(ObjectId()), "gd_active": True,
    })


def at_dhaka_hour(hour: int, days_ago: int) -> datetime:
    local = (datetime.now(DHAKA) - timedelta(days=days_ago)).replace(hour=hour, minute=20, second=0, microsecond=0)
    return local.astimezone(timezone.utc)


def test_the_grid_finds_hotspots():
    near = [(90.4047, 23.7457), (90.4049, 23.7458), (90.4046, 23.7456)]  # three thefts within ~30 m
    alone = [(90.4300, 23.7700)]
    found = hotspots(near + alone)
    assert len(found) == 1 and found[0]["count"] == 3
    assert abs(found[0]["lat"] - 23.7457) < 0.001
    assert hotspots(alone) == [] and hotspots([]) == []


def test_dashboard_numbers(db):
    for days_ago in (1, 2, 3):
        theft(db, 23.7457, 90.4047, at_dhaka_hour(21, days_ago))  # Ramna, 9 PM
    theft(db, 23.7458, 90.4049, at_dhaka_hour(8, 4), "bag_snatching")  # Ramna, 8 AM
    theft(db, 23.7460, 90.4050, at_dhaka_hour(22, 2), "burglary")  # counted, but never a hotspot dot
    theft(db, 23.8700, 90.3990, at_dhaka_hour(21, 1))  # Uttara: not in Ramna
    theft(db, 23.7457, 90.4047, at_dhaka_hour(21, 1), status="PENDING_REVIEW")  # not verified: ignored

    body = visitor.get("/api/v1/public/areas/ramna/dashboard", params={"days": 30}).json()
    assert body["total"] == 5
    assert body["area"]["code"] == "ramna" and body["area"]["geom"]["type"] in ("Polygon", "MultiPolygon")
    size = db.areas.find_one({"code": "ramna"})["size_km2"]
    assert body["per_km2"] == round(5 / size, 2)
    assert body["vs_city"] > 1  # Ramna has most of the city's thefts in this test
    assert body["by_type"][0] == {"code": "phone_snatching", "name_en": "Phone snatching", "name_bn": "ফোন ছিনতাই", "count": 3}
    assert body["by_hour"][21] == 3 and body["by_hour"][8] == 1 and body["busiest_hour"] == 21
    assert sum(d["count"] for d in body["by_weekday"]) == 5 and body["by_weekday"][0]["day"] == "Sat"
    assert sum(body["weekly"]) == 5 and len(body["weekly"]) == 5
    assert len(body["hotspots"]) == 1 and body["hotspots"][0]["count"] == 4  # the burglary is left out
    assert len(body["latest"]) == 5 and "location" not in str(body["latest"])


def test_wards_have_dashboards_too_and_periods(db):
    theft(db, 23.7457, 90.4047, at_dhaka_hour(12, 40))  # 40 days ago: only in the 90-day view
    ward = find_area_ids(23.7457, 90.4047)["ward_id"]
    code = db.areas.find_one({"_id": ward})["code"]
    assert visitor.get(f"/api/v1/public/areas/{code}/dashboard", params={"days": 30}).json()["total"] == 0
    assert visitor.get(f"/api/v1/public/areas/{code}/dashboard", params={"days": 90}).json()["total"] == 1
    assert visitor.get(f"/api/v1/public/areas/{code}/dashboard", params={"days": 7}).status_code == 422


def test_empty_area_and_unknown_area(db):
    body = visitor.get("/api/v1/public/areas/uttara/dashboard").json()
    assert body["total"] == 0 and body["busiest_hour"] is None and body["hotspots"] == []
    assert visitor.get("/api/v1/public/areas/atlantis/dashboard").status_code == 404
