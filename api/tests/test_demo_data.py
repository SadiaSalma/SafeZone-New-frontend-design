"""
Tests for Task 32: the demo data is clearly flagged, does not double, and is removed completely.
"""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import database_status, get_db
from app.demo import DEMO_SOURCE, add, remove
from app.main import app
from app.modules.areas.service import load_area_file
from app.modules.crime.admin import seed_categories
from app.modules.reports.service import seed_gd_formats
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
    seed_categories(database)
    seed_gd_formats(database)
    yield database
    database.client.drop_database(database.name)


def test_add_makes_flagged_demo_data(db):
    counts = add(reports=12)
    assert counts["reports"] >= 10 and counts["waiting"] == 2 and counts["accounts"] == 4
    assert db.reports.count_documents({"is_demo": True}) == counts["reports"] + 2
    assert db.reports.count_documents({"is_demo": {"$ne": True}}) == 0
    assert all(a["text_en"].startswith("[DEMO]") for a in db.alerts.find())
    assert all(r["description"] == "Demo report - not a real theft." for r in db.reports.find())
    assert db.crime_stats.count_documents({"source": {"$ne": DEMO_SOURCE}}) == 0
    # The waiting reports have their automatic checks done, ready for the verifier
    assert all(r.get("risk") for r in db.reports.find({"status": "PENDING_REVIEW"}))

    # The public pages see it
    alerts = TestClient(app).get("/api/v1/public/alerts").json()
    assert len(alerts["alerts"]) == counts["reports"]

    # The demo verifier can log in
    browser = TestClient(app)
    assert browser.post("/api/v1/auth/login", json={"phone": "01799000333", "password": "verify-pass-123"},
                        headers=SAFE).status_code == 200


def test_add_twice_does_not_double(db):
    first = add(reports=12)
    add(reports=12)
    assert db.reports.count_documents({}) == first["reports"] + 2
    assert db.users.count_documents({"is_demo": True}) == 4


def test_remove_takes_only_demo_data(db):
    add(reports=12)
    real = db.users.insert_one({"name_en": "Real Person", "phone": "+8801711000001",
                                "password_hash": hash_password("pass-1234"), "role": "victim", "status": "active",
                                "failed_logins": 0, "locked_until": None, "created_at": datetime.now(timezone.utc)}).inserted_id
    thana = db.areas.find_one({"code": "ramna"})
    cat = db.crime_categories.find_one({"key": "robbery"})
    db.crime_stats.insert_one({"area_id": thana["_id"], "category_id": cat["_id"], "month": datetime(2020, 1, 1, tzinfo=timezone.utc),
                               "count": 3, "source": "DMP monthly statistics"})
    counts = remove()
    assert counts["accounts"] == 4 and counts["reports"] >= 12
    assert db.reports.count_documents({}) == 0 and db.alerts.count_documents({}) == 0 and db.decisions.count_documents({}) == 0
    assert db.users.find_one({"_id": real}) is not None
    assert db.crime_stats.count_documents({}) == 1  # the admin's real figure stays


def test_practice_reports_are_labelled_and_survive_a_second_add(db):
    add(reports=12)
    victim = db.users.find_one({"phone": "+8801799000222"})
    practice = dict(db.reports.find_one({"demo_seed": True}))
    practice.pop("_id")
    practice.update({"user_id": victim["_id"], "is_demo": False, "demo_seed": False, "gd_hash": "practice-1"})
    pid = db.reports.insert_one(practice).inserted_id
    add(reports=12)
    assert db.reports.find_one({"_id": pid})["is_demo"] is True  # labelled, and not deleted by the second add
    remove()
    assert db.reports.find_one({"_id": pid}) is None  # the full remove takes it too
