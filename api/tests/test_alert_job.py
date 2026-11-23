"""
Tests for Task 22: the alert job (leased, retried, safe to repeat).
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


@pytest.fixture(scope="module", autouse=True)
def db():
    database = get_db()
    assert database.name == "safezone_test"
    database.client.drop_database(database.name)
    apply_schema(database)
    load_area_file(database)
    seed_gd_formats(database)
    build_network(database, phones=1500, seed=3)
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
    phone = f"+8801788000{n:03d}"
    user = {"name_en": "Job Tester", "phone": phone, "password_hash": hash_password("pass-1234"),
            "role": role, "status": "active", "failed_logins": 0, "locked_until": None, "created_at": datetime.now(timezone.utc)}
    if role == "victim":
        user |= {"nid_hash": hash_nid(f"1990888999{n:03d}"), "nid_last4": f"8{n}"}
    db.users.insert_one(user)
    browser = TestClient(app)
    browser.post("/api/v1/auth/login", json={"phone": phone, "password": "pass-1234"}, headers=SAFE)
    return browser


def approved_report(db, number="1234") -> tuple[TestClient, str]:
    victim, staff = account(db), account(db, "verifier")
    theft = datetime.now(DHAKA) - timedelta(hours=1)
    report_id = victim.post("/api/v1/reports", headers=SAFE, json={
        "theft_type": "phone_snatching", "occurred_at": theft.isoformat(), "lat": 23.7457, "lng": 90.4047,
        "gd": {"type": "GD", "number": number, "date": theft.date().isoformat(), "police_station": "ramna-model-ps"}}).json()["id"]
    staff.post(f"/api/v1/review/{report_id}/claim", headers=SAFE)
    assert staff.post(f"/api/v1/review/{report_id}/approve", json={}, headers=SAFE).status_code == 200
    return victim, report_id


def test_the_job_sends_to_every_phone_on_the_covering_towers(db, capsys):
    victim, report_id = approved_report(db)
    assert sender.run_once() == 1
    alert = db.alerts.find_one({"report_id": ObjectId(report_id)})
    assert alert["status"] == "sent" and alert["phones"] > 0 and alert["towers"] > 0 and alert["seconds_to_send"] >= 0

    # Exactly the phones on the towers whose range touches the alert circle
    towers = sender.towers_for(alert)
    expected = db.virtual_phones.count_documents({"tower_id": {"$in": [t["_id"] for t in towers]}})
    assert alert["phones"] == expected == db.virtual_inbox.count_documents({"alert_id": alert["_id"]})
    assert db.alert_deliveries.count_documents({"alert_id": alert["_id"]}) == len(towers)
    # A phone far away (Uttara) got nothing
    far = db.virtual_phones.find_one({"location": {"$nearSphere": {"$geometry": {"type": "Point", "coordinates": [90.40, 23.87]}}}})
    assert db.virtual_inbox.count_documents({"phone_id": far["_id"]}) == 0

    assert db.reports.find_one({"_id": ObjectId(report_id)})["status"] == "ALERTED"
    assert "warned" in capsys.readouterr().out  # the victim was told
    mine = victim.get(f"/api/v1/me/reports/{report_id}").json()
    assert mine["status"] == "ALERTED" and mine["alert"]["phones"] == alert["phones"]


def test_running_again_never_gives_a_phone_two_copies(db):
    _, report_id = approved_report(db, "2001")
    sender.run_once()
    alert = db.alerts.find_one({"report_id": ObjectId(report_id)})
    first = db.virtual_inbox.count_documents({"alert_id": alert["_id"]})
    db.alerts.update_one({"_id": alert["_id"]}, {"$set": {"status": "queued"}})  # pretend it must be sent again
    sender.run_once()
    assert db.virtual_inbox.count_documents({"alert_id": alert["_id"]}) == first
    assert db.alert_deliveries.count_documents({"alert_id": alert["_id"]}) == db.alerts.find_one({"_id": alert["_id"]})["towers"]


def test_an_expired_lease_is_picked_up_again(db):
    _, report_id = approved_report(db, "3001")
    alert = db.alerts.find_one({"report_id": ObjectId(report_id)})
    # A worker took it and then crashed: "sending", with a lease that has run out
    db.alerts.update_one({"_id": alert["_id"]}, {"$set": {"status": "sending", "attempts": 1,
                                                         "lease_until": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    assert sender.run_once() == 1
    assert db.alerts.find_one({"_id": alert["_id"]})["status"] == "sent"


def test_a_running_lease_is_left_alone(db):
    _, report_id = approved_report(db, "3501")
    db.alerts.update_one({"report_id": ObjectId(report_id)},
                         {"$set": {"status": "sending", "lease_until": datetime.now(timezone.utc) + timedelta(seconds=30)}})
    assert sender.run_once() == 0  # another worker is busy with it


def test_failures_are_retried_then_marked_failed_and_an_admin_can_resend(db, monkeypatch):
    _, report_id = approved_report(db, "4001")

    def broken(alert):
        raise RuntimeError("tower database not answering")

    monkeypatch.setattr(sender, "deliver", broken)
    for attempt in range(1, sender.MAX_ATTEMPTS + 1):
        sender.run_once()
        alert = db.alerts.find_one({"report_id": ObjectId(report_id)})
        assert alert["attempts"] == attempt  # one attempt per run: it waits before trying again
        if alert["status"] == "queued":
            assert sender.run_once() == 0  # still pausing
            db.alerts.update_one({"_id": alert["_id"]}, {"$set": {"lease_until": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    assert alert["status"] == "failed" and "not answering" in alert["last_error"]
    assert db.reports.find_one({"_id": ObjectId(report_id)})["status"] == "ALERT_FAILED"

    monkeypatch.undo()
    monkeypatch.setattr(settings, "storage_dir", "storage")
    verifier, admin = account(db, "verifier"), account(db, "admin")
    assert verifier.post(f"/api/v1/admin/alerts/{alert['_id']}/resend", headers=SAFE).status_code == 403
    assert admin.post(f"/api/v1/admin/alerts/{alert['_id']}/resend", headers=SAFE).status_code == 200
    assert db.reports.find_one({"_id": ObjectId(report_id)})["status"] == "VERIFIED"
    sender.run_once()
    assert db.alerts.find_one({"_id": alert["_id"]})["status"] == "sent"
    assert db.reports.find_one({"_id": ObjectId(report_id)})["status"] == "ALERTED"
    assert admin.post(f"/api/v1/admin/alerts/{alert['_id']}/resend", headers=SAFE).status_code == 409  # not failed now


def test_staff_alert_list(db):
    _, report_id = approved_report(db, "5001")
    sender.run_once()
    listed = account(db, "verifier").get("/api/v1/admin/alerts").json()["alerts"]
    assert listed[0]["report_id"] == report_id and listed[0]["status"] == "sent" and listed[0]["phones"] > 0
    assert account(db).get("/api/v1/admin/alerts").status_code == 403  # victims can't
