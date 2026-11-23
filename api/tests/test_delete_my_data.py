"""
Tests for Task 31: "Delete my data" (FR-4, R8) - password, then a code by SMS, then everything personal goes.
"""
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import storage
from app.db import database_status, get_db
from app.main import app
from app.modules.areas.service import load_area_file
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
    yield database
    database.client.drop_database(database.name)


@pytest.fixture(autouse=True)
def clean(db):
    db.rate_counters.delete_many({})


_n = iter(range(100, 999))


def person(db, role="victim"):
    n = next(_n)
    phone = f"+8801799700{n:03d}"
    uid = db.users.insert_one({
        "name_en": "Nila Rahman", "phone": phone, "password_hash": hash_password("pass-1234"),
        "role": role, "status": "active", "failed_logins": 0, "locked_until": None, "created_at": datetime.now(timezone.utc),
        "nid_hash": f"hash-{n}", "nid_last4": "1234"}).inserted_id
    browser = TestClient(app)
    assert browser.post("/api/v1/auth/login", json={"phone": phone, "password": "pass-1234"}, headers=SAFE).status_code == 200
    return browser, uid, phone


def report(db, uid, status, public=None):
    now = datetime.now(timezone.utc)
    return db.reports.insert_one({
        "user_id": uid, "status": status, "theft_type": "phone_snatching", "occurred_at": now - timedelta(hours=2),
        "submitted_at": now, "location": {"type": "Point", "coordinates": [90.4001, 23.7301]},
        "public_location": public, "landmark": "Near my house, road 5", "description": "My red phone was taken",
        "stolen_items": "Samsung A54", "info_answer": "It was at 9 pm",
        "gd": {"type": "GD", "number": "1234", "date": now}, "gd_hash": f"h-{status}-{uid}",
        "gd_active": status not in ("WITHDRAWN", "REJECTED")}).inserted_id


def get_code(browser, capsys, password="pass-1234"):
    capsys.readouterr()
    answer = browser.post("/api/v1/me/delete/request", json={"password": password}, headers=SAFE)
    found = re.search(r"code: (\d{6})", capsys.readouterr().out)
    return answer, (found.group(1) if found else None)


def test_the_summary_shows_what_will_change(db):
    browser, uid, _ = person(db)
    report(db, uid, "PENDING_REVIEW")
    report(db, uid, "ALERTED", public={"type": "Point", "coordinates": [90.401, 23.731]})
    body = browser.get("/api/v1/me/delete").json()
    assert body["reports"] == 2 and body["waiting"] == 1 and body["nid_added"] is True
    assert body["phone_masked"].startswith("01") and "*" in body["phone_masked"]


def test_wrong_password_sends_no_code(db, capsys):
    browser, _, _ = person(db)
    answer, code = get_code(browser, capsys, password="wrong-pass")
    assert answer.status_code == 400 and code is None
    assert "password" in answer.json()["error"]["fields"]


def test_full_delete(db, capsys):
    browser, uid, phone = person(db)
    waiting = report(db, uid, "PENDING_REVIEW")
    public = {"type": "Point", "coordinates": [90.4012, 23.7311]}
    alerted = report(db, uid, "ALERTED", public=public)
    key = storage.save(b"fake-jpeg-bytes")
    db.report_photos.insert_one({"report_id": waiting, "storage_key": key, "size_bytes": 15, "kind": "item",
                                 "created_at": datetime.now(timezone.utc)})
    db.push_subscriptions.insert_one({"endpoint": "https://push.example/abc", "keys": {"p256dh": "x", "auth": "y"},
                                      "area_ids": [], "user_id": uid, "created_at": datetime.now(timezone.utc)})

    answer, code = get_code(browser, capsys)
    assert answer.status_code == 200 and code
    # A wrong code first: nothing happens
    wrong = browser.post("/api/v1/me/delete/confirm", json={"code": "000000" if code != "000000" else "111111"}, headers=SAFE)
    assert wrong.status_code == 400 and db.users.find_one({"_id": uid})["status"] == "active"

    done = browser.post("/api/v1/me/delete/confirm", json={"code": code}, headers=SAFE)
    assert done.status_code == 200 and done.json()["reports"] == 2 and done.json()["photos"] == 1

    user = db.users.find_one({"_id": uid})
    assert user["status"] == "deleted" and user["name_en"] == "Deleted user"
    assert user["phone"].startswith("deleted:") and "email" not in user
    assert "nid_hash" not in user and "nid_last4" not in user

    w = db.reports.find_one({"_id": waiting})
    assert w["status"] == "WITHDRAWN" and w["gd_active"] is False and w["user_id"] is None
    a = db.reports.find_one({"_id": alerted})
    assert a["status"] == "ALERTED" and a["location"] == public  # the exact place is gone
    for r in (w, a):
        assert r["description"] == "" and r["stolen_items"] == "" and r["landmark"] == "" and "info_answer" not in r
        assert r["anonymized_at"] is not None
    assert w["location"]["coordinates"] != [90.4001, 23.7301]  # moved 100-200 m

    assert db.report_photos.count_documents({"report_id": waiting}) == 0
    assert not (storage.folder() / key).exists()  # the file is gone from the disk
    assert db.push_subscriptions.count_documents({"user_id": uid}) == 0
    assert db.sessions.count_documents({"user_id": uid}) == 0
    assert db.audit_logs.find_one({"action": "user.delete", "entity_id": uid})

    # Logged out, can't log in again, and the phone can be used for a new account
    assert browser.get("/api/v1/me").status_code == 401
    assert TestClient(app).post("/api/v1/auth/login", json={"phone": phone, "password": "pass-1234"}, headers=SAFE).status_code == 401
    assert db.users.count_documents({"phone": phone}) == 0


def test_staff_cant_delete_themselves_here(db, capsys):
    browser, _, _ = person(db, role="verifier")
    answer, code = get_code(browser, capsys)
    assert answer.status_code == 403 and code is None


def test_needs_log_in_and_a_six_digit_code(db):
    assert TestClient(app).get("/api/v1/me/delete").status_code == 401
    browser, _, _ = person(db)
    assert browser.post("/api/v1/me/delete/confirm", json={"code": "12ab"}, headers=SAFE).status_code == 422
    # No code was asked for -> refused
    assert browser.post("/api/v1/me/delete/confirm", json={"code": "123456"}, headers=SAFE).status_code == 400
