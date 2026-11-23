"""
Tests for Task 25: the public map and alerts - especially the privacy rules (FR-21, R8).
"""
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from shapely.geometry import Point, shape

from app.config import settings
from app.db import database_status, get_db
from app.main import app
from app.modules.alerts import sender
from app.modules.areas.service import load_area_file
from app.modules.reports.checks import km_between
from app.modules.reports.service import seed_gd_formats
from app.modules.simulator.network import build_network
from app.security import hash_nid, hash_password
from app.setup_db import apply_schema

pytestmark = pytest.mark.skipif(
    not database_status()["ok"],
    reason="Database not running. Start it: Terminal -> Run Task -> 'SafeZone: start database'",
)
SAFE = {"X-SafeZone": "1"}
DHAKA = timezone(timedelta(hours=6))
visitor = TestClient(app)  # nobody logged in


@pytest.fixture(scope="module", autouse=True)
def db():
    database = get_db()
    assert database.name == "safezone_test"
    database.client.drop_database(database.name)
    apply_schema(database)
    load_area_file(database)
    seed_gd_formats(database)
    build_network(database, phones=300, seed=6)
    yield database
    database.client.drop_database(database.name)


@pytest.fixture(autouse=True)
def clean(db, tmp_path, monkeypatch):
    for name in ("reports", "alerts", "virtual_inbox", "alert_deliveries", "rate_counters"):
        db[name].delete_many({})
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))


_n = iter(range(100, 999))


def account(db, role="victim"):
    n = next(_n)
    phone = f"+8801799300{n:03d}"
    user = {"name_en": "Private Person", "phone": phone, "password_hash": hash_password("pass-1234"),
            "role": role, "status": "active", "failed_logins": 0, "locked_until": None, "created_at": datetime.now(timezone.utc)}
    if role == "victim":
        user |= {"nid_hash": hash_nid(f"1990565656{n:03d}"), "nid_last4": f"5{n}"}
    db.users.insert_one(user)
    browser = TestClient(app)
    browser.post("/api/v1/auth/login", json={"phone": phone, "password": "pass-1234"}, headers=SAFE)
    return browser


def report(db, theft_type="phone_snatching", hours_ago=2, approve=True, spot=(23.7457, 90.4047)):
    victim = account(db)
    theft = datetime.now(DHAKA) - timedelta(hours=hours_ago)
    report_id = victim.post("/api/v1/reports", headers=SAFE, json={
        "theft_type": theft_type, "occurred_at": theft.isoformat(), "lat": spot[0], "lng": spot[1],
        "landmark": "Secret landmark", "description": "Secret story", "stolen_items": "Secret items",
        "gd": {"type": "GD", "number": str(next(_n)), "date": theft.date().isoformat(), "police_station": "ramna-model-ps"}}).json()["id"]
    if approve:
        staff = account(db, "verifier")
        staff.post(f"/api/v1/review/{report_id}/claim", headers=SAFE)
        assert staff.post(f"/api/v1/review/{report_id}/approve", json={}, headers=SAFE).status_code == 200
        sender.run_once()
    return report_id


def test_only_verified_thefts_and_only_the_moved_point(db):
    shown = report(db)
    hidden = report(db, approve=False)  # still waiting for review
    answer = visitor.get("/api/v1/public/incidents", params={"days": 30})
    assert answer.status_code == 200
    body = answer.json()
    assert [p["id"] for p in body["points"]] == [shown]
    assert hidden not in answer.text

    point = body["points"][0]
    exact = db.reports.find_one({"_id": ObjectId(shown)})["location"]["coordinates"]
    metres = km_between(Point(*exact), Point(point["lng"], point["lat"])) * 1000
    assert 99 <= metres <= 201  # R8: never the exact place
    for secret in ("Secret landmark", "Secret story", "Secret items", "Private Person"):
        assert secret not in answer.text
    assert point["occurred_hour"].endswith("00:00+00:00") or ":00:00" in point["occurred_hour"]  # rounded to the hour


def test_burglaries_are_only_counted_per_thana(db):
    report(db, theft_type="burglary")
    body = visitor.get("/api/v1/public/incidents", params={"days": 30}).json()
    assert body["points"] == []  # no dot that could point at a home
    bubble = body["area_counts"][0]
    assert bubble["count"] == 1 and bubble["thana"]["code"] == "ramna"
    ramna = shape(db.areas.find_one({"code": "ramna"})["geom"])
    assert ramna.contains(Point(bubble["lng"], bubble["lat"]))  # drawn in the middle of the thana


def test_period_and_type_filters(db):
    report(db, "phone_snatching", hours_ago=2)
    report(db, "bag_snatching", hours_ago=24 * 10)
    assert len(visitor.get("/api/v1/public/incidents", params={"days": 7}).json()["points"]) == 1
    assert len(visitor.get("/api/v1/public/incidents", params={"days": 30}).json()["points"]) == 2
    only_bags = visitor.get("/api/v1/public/incidents", params={"days": 30, "type": "bag_snatching"}).json()
    assert [p["theft_type"] for p in only_bags["points"]] == ["bag_snatching"]
    assert visitor.get("/api/v1/public/incidents", params={"days": 12}).status_code == 422


def test_public_alerts_never_show_the_exact_place(db):
    report_id = report(db)
    alerts = visitor.get("/api/v1/public/alerts").json()["alerts"]
    assert len(alerts) == 1 and alerts[0]["text_en"].startswith("SafeZone alert:")
    one = visitor.get(f"/api/v1/public/alerts/{alerts[0]['id']}").json()
    exact = db.reports.find_one({"_id": ObjectId(report_id)})["location"]["coordinates"]
    assert (one["point"]["lng"], one["point"]["lat"]) != tuple(exact)
    assert km_between(Point(*exact), Point(one["point"]["lng"], one["point"]["lat"])) * 1000 >= 99
    assert visitor.get(f"/api/v1/public/alerts/{ObjectId()}").status_code == 404
    assert visitor.get("/api/v1/public/alerts/nonsense").status_code == 404


def test_a_burglary_alert_has_no_point(db):
    report(db, theft_type="burglary")
    alert = visitor.get("/api/v1/public/alerts").json()["alerts"][0]
    assert alert["theft_type"] == "burglary" and alert["point"] is None and alert["thana"]["code"] == "ramna"
