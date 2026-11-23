"""
Tests for Task 30: the admin panel (stats, staff, areas, police stations, GD formats, risk settings, audit log).
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import database_status, get_db
from app.main import app
from app.modules.areas.service import load_area_file
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
    seed_gd_formats(database)
    yield database
    database.client.drop_database(database.name)


_n = iter(range(100, 999))


def person(db, role, password="pass-1234"):
    n = next(_n)
    phone = f"+8801799500{n:03d}"
    uid = db.users.insert_one({"name_en": f"{role.title()} {n}", "phone": phone,
                               "password_hash": hash_password(password), "role": role, "status": "active",
                               "failed_logins": 0, "locked_until": None,
                               "created_at": datetime.now(timezone.utc)}).inserted_id
    browser = TestClient(app)
    assert browser.post("/api/v1/auth/login", json={"phone": phone, "password": password}, headers=SAFE).status_code == 200
    return browser, uid


def test_only_admins_may_open_the_admin_pages(db):
    victim, _ = person(db, "victim")
    verifier, _ = person(db, "verifier")
    for path in ("/api/v1/admin/staff", "/api/v1/admin/areas", "/api/v1/admin/stations", "/api/v1/admin/gd-formats",
                 "/api/v1/admin/settings/risk", "/api/v1/admin/audit-logs"):
        assert TestClient(app).get(path).status_code == 401
        assert victim.get(path).status_code == 403
        assert verifier.get(path).status_code == 403
    # The overview numbers are for all staff
    assert verifier.get("/api/v1/admin/stats").status_code == 200
    assert victim.get("/api/v1/admin/stats").status_code == 403


def test_stats_count_reports_and_alerts(db):
    admin, admin_id = person(db, "admin")
    now = datetime.now(timezone.utc)
    db.reports.delete_many({})
    db.alerts.delete_many({})
    point = {"type": "Point", "coordinates": [90.4, 23.73]}
    base = {"theft_type": "phone_snatching", "occurred_at": now, "location": point,
            "gd": {"type": "GD", "number": "1", "date": now}, "gd_hash": "x", "gd_active": False}
    r1 = db.reports.insert_one({**base, "status": "PENDING_REVIEW", "submitted_at": now - timedelta(minutes=90)}).inserted_id
    r2 = db.reports.insert_one({**base, "status": "ALERTED", "submitted_at": now - timedelta(minutes=50)}).inserted_id
    db.decisions.insert_one({"report_id": r2, "verifier_id": admin_id, "decision": "approve", "created_at": now - timedelta(minutes=30)})
    db.alerts.insert_one({"report_id": r2, "text_en": "x", "text_bn": "x", "center": point, "radius_m": 1000,
                          "queued_at": now, "status": "sent", "phones": 120, "seconds_to_send": 3.5})
    body = admin.get("/api/v1/admin/stats").json()
    assert body["waiting"] == 1 and body["reports"]["total"] == 2
    assert 89 <= body["oldest_waiting_minutes"] <= 91
    assert body["average_review_minutes"] == 20
    assert body["alerts_sent"] == 1 and body["phones_reached"] == 120 and body["average_send_seconds"] == 3.5
    assert len(body["per_day"]) == 14 and body["per_day"][-1]["count"] >= 1
    assert r1


def test_add_and_suspend_staff(db):
    admin, admin_id = person(db, "admin")
    made = admin.post("/api/v1/admin/staff", headers=SAFE, json={
        "name_en": "New Verifier", "phone": "01799600111",
        "password": "strong-pass-123", "role": "verifier"})
    assert made.status_code == 201 and made.json()["role"] == "verifier" and "password_hash" not in made.json()
    # The same phone again -> refused
    again = admin.post("/api/v1/admin/staff", headers=SAFE, json={
        "name_en": "Copy", "phone": "01799600111", "password": "strong-pass-123", "role": "admin"})
    assert again.status_code == 409

    # The new verifier logs in; after the admin suspends them, their session stops working
    worker = TestClient(app)
    assert worker.post("/api/v1/auth/login", json={"phone": "01799600111", "password": "strong-pass-123"}, headers=SAFE).status_code == 200
    assert worker.get("/api/v1/review/queue").status_code == 200
    changed = admin.put(f"/api/v1/admin/staff/{made.json()['id']}", headers=SAFE, json={"status": "suspended"})
    assert changed.json()["status"] == "suspended"
    assert worker.get("/api/v1/review/queue").status_code == 401
    assert db.sessions.count_documents({"user_id": db.users.find_one({"phone": "+8801799600111"})["_id"], "revoked_at": None}) == 0

    # An admin can't suspend themself
    assert admin.put(f"/api/v1/admin/staff/{admin_id}", headers=SAFE, json={"status": "suspended"}).status_code == 409
    assert db.audit_logs.find_one({"action": "staff.change", "after.status": "suspended"})
    names = [s["name_en"] for s in admin.get("/api/v1/admin/staff").json()["staff"]]
    assert "New Verifier" in names


def test_change_an_area_radius_and_name(db):
    admin, _ = person(db, "admin")
    areas = admin.get("/api/v1/admin/areas", params={"type": "thana"}).json()["areas"]
    assert len(areas) == 41 and all(a["alert_radius_m"] == 1000 for a in areas)
    assert admin.put("/api/v1/admin/areas/ramna", headers=SAFE, json={"alert_radius_m": 100}).status_code == 422
    changed = admin.put("/api/v1/admin/areas/ramna", headers=SAFE, json={"alert_radius_m": 1500, "name_bn": "রমনা থানা"})
    assert changed.json()["alert_radius_m"] == 1500 and changed.json()["name_bn"] == "রমনা থানা"
    assert admin.put("/api/v1/admin/areas/atlantis", headers=SAFE, json={"is_active": False}).status_code == 404
    wards = admin.get("/api/v1/admin/areas", params={"type": "ward"}).json()["areas"]
    assert len(wards) == 92 and wards[0]["code"].endswith("01")
    # Loading the area file again keeps the admin's change
    load_area_file(db)
    assert db.areas.find_one({"code": "ramna"})["alert_radius_m"] == 1500
    db.areas.update_one({"code": "ramna"}, {"$set": {"alert_radius_m": 1000, "name_bn": "রমনা"}})


def test_change_a_police_station(db):
    admin, _ = person(db, "admin")
    stations = admin.get("/api/v1/admin/stations").json()["stations"]
    code = stations[0]["code"]
    assert admin.put(f"/api/v1/admin/stations/{code}", headers=SAFE, json={"phone": "call me"}).status_code == 422
    changed = admin.put(f"/api/v1/admin/stations/{code}", headers=SAFE, json={"phone": "01320-040000", "is_active": False})
    assert changed.json()["phone"] == "01320-040000" and changed.json()["is_active"] is False
    # A switched-off station is not offered on the report form
    options = TestClient(app).get("/api/v1/reports/options").json()
    assert code not in [s["code"] for s in options["police_stations"]]
    admin.put(f"/api/v1/admin/stations/{code}", headers=SAFE, json={"is_active": True})


def test_gd_formats_must_be_valid(db):
    admin, _ = person(db, "admin")
    assert len(admin.get("/api/v1/admin/gd-formats").json()["formats"]) == 2
    broken = admin.post("/api/v1/admin/gd-formats", headers=SAFE, json={"regex": "^GD-(\\d+$", "example": "GD-1"})
    assert broken.status_code == 422 and "regex" in broken.json()["error"]["fields"]
    wrong = admin.post("/api/v1/admin/gd-formats", headers=SAFE, json={"regex": "^DMP-\\d{4}$", "example": "DMP-12"})
    assert wrong.status_code == 422 and "example" in wrong.json()["error"]["fields"]
    made = admin.post("/api/v1/admin/gd-formats", headers=SAFE,
                      json={"regex": "^DMP-\\d{4}$", "example": "DMP-1234", "label": "DMP style"})
    assert made.status_code == 201
    off = admin.put(f"/api/v1/admin/gd-formats/{made.json()['id']}", headers=SAFE, json={"is_active": False})
    assert off.json()["is_active"] is False
    assert admin.put("/api/v1/admin/gd-formats/nope", headers=SAFE, json={"is_active": True}).status_code == 404


def test_risk_settings(db):
    admin, _ = person(db, "admin")
    now = admin.get("/api/v1/admin/settings/risk").json()
    assert now["risk_points"]["gd_format"] == 20 and now["risk_levels"] == {"medium_from": 30, "high_from": 60}
    bad = admin.put("/api/v1/admin/settings/risk", headers=SAFE,
                    json={"risk_points": now["risk_points"], "risk_levels": {"medium_from": 70, "high_from": 60}})
    assert bad.status_code == 422
    points = {**now["risk_points"], "gd_copy": 25}
    saved = admin.put("/api/v1/admin/settings/risk", headers=SAFE,
                      json={"risk_points": points, "risk_levels": {"medium_from": 25, "high_from": 55}})
    assert saved.json()["risk_points"]["gd_copy"] == 25 and saved.json()["risk_levels"]["high_from"] == 55
    db.settings.delete_many({})  # back to the defaults for other tests


def test_audit_log_newest_first_without_victim_names(db):
    admin, _ = person(db, "admin")
    victim, victim_id = person(db, "victim")
    db.audit_logs.insert_one({"actor_id": victim_id, "actor_role": "victim", "action": "report.submit", "entity": "reports",
                              "entity_id": None, "after": {}, "created_at": datetime.now(timezone.utc)})
    body = admin.get("/api/v1/admin/audit-logs").json()
    assert body["entries"][0]["action"] == "report.submit"
    assert body["entries"][0]["actor_name"] == ""  # victims are never named in the log view
    times = [e["created_at"] for e in body["entries"]]
    assert times == sorted(times, reverse=True)
    only = admin.get("/api/v1/admin/audit-logs", params={"action": "report."}).json()
    assert only["total"] >= 1 and all(e["action"].startswith("report.") for e in only["entries"])
    assert admin.get("/api/v1/admin/audit-logs", params={"page": 0}).status_code == 422
    assert victim
