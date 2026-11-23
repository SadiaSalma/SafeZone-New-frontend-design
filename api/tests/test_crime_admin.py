"""
Tests for Task 27: crime categories and monthly crime figures (admins only).
"""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import database_status, get_db
from app.main import app
from app.modules.areas.service import load_area_file
from app.modules.crime.admin import seed_categories
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
    yield database
    database.client.drop_database(database.name)


@pytest.fixture(autouse=True)
def clean(db):
    db.crime_stats.delete_many({})


_n = iter(range(100, 999))


def person(db, role):
    n = next(_n)
    phone = f"+8801799400{n:03d}"
    db.users.insert_one({"name_en": f"{role} {n}", "phone": phone,
                         "password_hash": hash_password("pass-1234"), "role": role, "status": "active", "failed_logins": 0,
                         "locked_until": None, "created_at": datetime.now(timezone.utc)})
    browser = TestClient(app)
    browser.post("/api/v1/auth/login", json={"phone": phone, "password": "pass-1234"}, headers=SAFE)
    return browser


def ids(db, area_code, category_key):
    return str(db.areas.find_one({"code": area_code})["_id"]), str(db.crime_categories.find_one({"key": category_key})["_id"])


def test_the_nine_starting_categories(db):
    cats = person(db, "admin").get("/api/v1/admin/crime-categories").json()["categories"]
    assert [c["key"] for c in cats][:4] == ["murder", "rape", "kidnapping", "robbery"]
    assert {c["key"]: c["weight"] for c in cats}["snatching"] == 4 and len(cats) == 9
    assert seed_categories(db) == 0  # running again adds nothing


def test_only_admins(db):
    assert person(db, "verifier").get("/api/v1/admin/crime-categories").status_code == 403
    assert TestClient(app).get("/api/v1/admin/crime-stats", params={"month": "2026-10"}).status_code == 401


def test_change_and_add_categories(db):
    admin = person(db, "admin")
    other_id = db.crime_categories.find_one({"key": "other"})["_id"]
    changed = admin.put(f"/api/v1/admin/crime-categories/{other_id}", headers=SAFE, json={"weight": 1.5})
    assert changed.status_code == 200 and changed.json()["weight"] == 1.5
    added = admin.post("/api/v1/admin/crime-categories", headers=SAFE,
                       json={"key": "fraud", "name_en": "Fraud", "name_bn": "প্রতারণা", "weight": 2})
    assert added.status_code == 201 and added.json()["order"] == 9
    again = admin.post("/api/v1/admin/crime-categories", headers=SAFE, json={"key": "fraud", "name_en": "Fraud 2", "weight": 2})
    assert again.status_code == 409
    assert admin.post("/api/v1/admin/crime-categories", headers=SAFE, json={"key": "Bad Key!", "name_en": "x x", "weight": 1}).status_code == 422
    db.crime_categories.delete_one({"key": "fraud"})
    db.crime_categories.update_one({"key": "other"}, {"$set": {"weight": 1}})


def test_enter_figures_with_a_source(db):
    admin = person(db, "admin")
    ramna, robbery = ids(db, "ramna", "robbery")
    _, snatching = ids(db, "ramna", "snatching")
    body = {"month": "2026-10", "source": "DMP crime statistics, October 2026",
            "changes": [{"area_id": ramna, "category_id": robbery, "count": 4},
                        {"area_id": ramna, "category_id": snatching, "count": 11}]}
    assert admin.put("/api/v1/admin/crime-stats", headers=SAFE, json=body).json() == {"saved": 2, "removed": 0}

    table = admin.get("/api/v1/admin/crime-stats", params={"month": "2026-10", "level": "thana"}).json()
    assert len(table["rows"]) == 41 and len(table["categories"]) == 9
    row = next(r for r in table["rows"] if r["code"] == "ramna")
    assert row["cells"] == {robbery: 4, snatching: 11}
    assert table["sources"] == ["DMP crime statistics, October 2026"]

    # Change one, delete one: one audit line per change, with from -> to
    body = {"month": "2026-10", "source": "DMP corrected figures",
            "changes": [{"area_id": ramna, "category_id": robbery, "count": 5},
                        {"area_id": ramna, "category_id": snatching, "count": None}]}
    assert admin.put("/api/v1/admin/crime-stats", headers=SAFE, json=body).json() == {"saved": 1, "removed": 1}
    last = db.audit_logs.find({"action": "crime_stat.update"}).sort("created_at", -1).limit(2)
    assert {(a["after"]["from"], a["after"]["to"]) for a in last} == {(4, 5), (11, None)}
    assert db.crime_stats.count_documents({}) == 1


def test_bad_figures_are_refused(db):
    admin = person(db, "admin")
    ramna, robbery = ids(db, "ramna", "robbery")
    cell = {"area_id": ramna, "category_id": robbery, "count": 3}
    no_source = admin.put("/api/v1/admin/crime-stats", headers=SAFE, json={"month": "2026-10", "source": "", "changes": [cell]})
    assert no_source.status_code == 422 and "source" in no_source.json()["error"]["fields"]
    negative = admin.put("/api/v1/admin/crime-stats", headers=SAFE,
                         json={"month": "2026-10", "source": "DMP", "changes": [cell | {"count": -2}]})
    assert negative.status_code == 422
    future = admin.put("/api/v1/admin/crime-stats", headers=SAFE, json={"month": "2099-01", "source": "DMP", "changes": [cell]})
    assert future.status_code == 422 and "month" in future.json()["error"]["fields"]
    bad_month = admin.get("/api/v1/admin/crime-stats", params={"month": "October"})
    assert bad_month.status_code == 422


def test_wards_table(db):
    table = person(db, "admin").get("/api/v1/admin/crime-stats", params={"month": "2026-10", "level": "ward"}).json()
    assert len(table["rows"]) == 92 and table["rows"][0]["name_en"] == "Ward 1"
