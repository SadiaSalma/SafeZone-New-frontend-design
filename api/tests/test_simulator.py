"""
Tests for Task 24: looking inside the simulation, and the admin's test phone.
"""
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.config import settings
from app.db import database_status, get_db
from app.main import app
from app.modules.alerts import sender
from app.modules.areas.service import load_area_file
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
RAMNA = (23.7457, 90.4047)
UTTARA = (23.8700, 90.3990)


@pytest.fixture(scope="module", autouse=True)
def db():
    database = get_db()
    assert database.name == "safezone_test"
    database.client.drop_database(database.name)
    apply_schema(database)
    load_area_file(database)
    seed_gd_formats(database)
    build_network(database, phones=1200, seed=5)
    yield database
    database.client.drop_database(database.name)


@pytest.fixture(autouse=True)
def clean(db, tmp_path, monkeypatch):
    for name in ("reports", "alerts", "virtual_inbox", "alert_deliveries", "rate_counters"):
        db[name].delete_many({})
    db.virtual_phones.delete_many({"is_test": True})
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))


_n = iter(range(100, 999))


def account(db, role="victim"):
    n = next(_n)
    phone = f"+8801799200{n:03d}"
    user = {"name_en": f"Sim {role}", "phone": phone, "password_hash": hash_password("pass-1234"),
            "role": role, "status": "active", "failed_logins": 0, "locked_until": None, "created_at": datetime.now(timezone.utc)}
    if role == "victim":
        user |= {"nid_hash": hash_nid(f"1990343434{n:03d}"), "nid_last4": f"3{n}"}
    db.users.insert_one(user)
    browser = TestClient(app)
    browser.post("/api/v1/auth/login", json={"phone": phone, "password": "pass-1234"}, headers=SAFE)
    return browser


def send_alert(db, at=RAMNA) -> dict:
    victim, staff = account(db), account(db, "verifier")
    theft = datetime.now(DHAKA) - timedelta(hours=1)
    report_id = victim.post("/api/v1/reports", headers=SAFE, json={
        "theft_type": "pickpocket", "occurred_at": theft.isoformat(), "lat": at[0], "lng": at[1],
        "gd": {"type": "GD", "number": str(next(_n)), "date": theft.date().isoformat(), "police_station": "ramna-model-ps"}}).json()["id"]
    staff.post(f"/api/v1/review/{report_id}/claim", headers=SAFE)
    assert staff.post(f"/api/v1/review/{report_id}/approve", json={}, headers=SAFE).status_code == 200
    sender.run_once()
    return db.alerts.find_one({"report_id": ObjectId(report_id)})


def test_alert_view_and_red_phones(db):
    alert = send_alert(db)
    staff = account(db, "verifier")
    view = staff.get(f"/api/v1/admin/simulator/alerts/{alert['_id']}").json()
    assert view["radius_m"] == 1000 and view["phones"] == alert["phones"] and len(view["tower_ids"]) == alert["towers"]

    box = {"south": 23.70, "west": 90.36, "north": 23.79, "east": 90.45, "alert_id": str(alert["_id"])}
    phones = staff.get("/api/v1/admin/simulator/phones", params=box).json()["phones"]
    red = [p for p in phones if p["received"]]
    assert red and len(red) < len(phones)  # some phones got it, others (outside) didn't
    assert len(red) == db.virtual_inbox.count_documents({"alert_id": alert["_id"], "phone_id": {"$in": [ObjectId(p["id"]) for p in phones]}})


def test_one_phones_inbox(db):
    alert = send_alert(db)
    phone_id = db.virtual_inbox.find_one({"alert_id": alert["_id"]})["phone_id"]
    inbox = account(db, "verifier").get(f"/api/v1/admin/simulator/phones/{phone_id}/inbox").json()
    assert inbox["tower"].startswith("T-") and inbox["messages"][0]["text_en"] == alert["text_en"]
    assert account(db).get(f"/api/v1/admin/simulator/phones/{phone_id}/inbox").status_code == 403  # victims can't look


def test_test_mode_received_and_not_reached(db):
    admin = account(db, "admin")
    placed = admin.post("/api/v1/admin/simulator/test-phone", headers=SAFE, json={"lat": RAMNA[0], "lng": RAMNA[1], "label": "My phone"})
    assert placed.status_code == 200 and placed.json()["phone"]["tower"].startswith("T-")

    near = send_alert(db, RAMNA)  # right next to the test phone
    far = send_alert(db, UTTARA)  # 14 km away
    report = {a["id"]: a for a in admin.get("/api/v1/admin/simulator/test-phone").json()["alerts"]}
    assert report[str(near["_id"])]["received"] is True
    assert report[str(far["_id"])]["received"] is False and report[str(far["_id"])]["reason"] == "tower_outside"

    # Moving the phone keeps ONE test phone per admin
    admin.post("/api/v1/admin/simulator/test-phone", headers=SAFE, json={"lat": UTTARA[0], "lng": UTTARA[1]})
    assert db.virtual_phones.count_documents({"is_test": True}) == 1
    assert admin.delete("/api/v1/admin/simulator/test-phone", headers=SAFE).json()["phone"] is None
    assert db.virtual_phones.count_documents({"is_test": True}) == 0


def test_test_phone_rules(db):
    admin, verifier = account(db, "admin"), account(db, "verifier")
    assert verifier.post("/api/v1/admin/simulator/test-phone", headers=SAFE, json={"lat": RAMNA[0], "lng": RAMNA[1]}).status_code == 403
    outside = admin.post("/api/v1/admin/simulator/test-phone", headers=SAFE, json={"lat": 22.3569, "lng": 91.7832})  # Chattogram
    assert outside.status_code == 422 and "location" in outside.json()["error"]["fields"]
    # An alert sent BEFORE the phone was placed is explained, not counted as a failure
    old = send_alert(db, RAMNA)
    admin.post("/api/v1/admin/simulator/test-phone", headers=SAFE, json={"lat": RAMNA[0], "lng": RAMNA[1]})
    status = {a["id"]: a for a in admin.get("/api/v1/admin/simulator/test-phone").json()["alerts"]}
    assert status[str(old["_id"])]["reason"] == "before_phone"
