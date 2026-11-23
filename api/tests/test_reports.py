"""
Tests for Task 14: sending theft reports, the limits, the "one GD, one active report" rule,
my reports and withdrawing. They use the test database (skipped if it is not running).
"""
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.db import database_status, get_db
from app.main import app
from app.modules.areas.service import load_area_file
from app.modules.reports.service import seed_gd_formats
from app.security import hash_nid, hash_password
from app.setup_db import apply_schema

pytestmark = pytest.mark.skipif(
    not database_status()["ok"],
    reason="Database not running. Start it: Terminal -> Run Task -> 'SafeZone: start database'",
)
SAFE = {"X-SafeZone": "1"}
RAMNA = {"lat": 23.7457, "lng": 90.4047}


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


@pytest.fixture(autouse=True)
def clean(db):
    db.reports.delete_many({})
    db.rate_counters.delete_many({})
    db.login_attempts.delete_many({})


_phones = iter(range(1000, 9999))


def person(db, with_nid=True, role="victim") -> TestClient:
    """A new logged-in person (a TestClient that keeps their log-in cookies)."""
    n = next(_phones)
    phone = f"+880171100{n:04d}"
    user = {"name_en": "Report Tester", "phone": phone, "password_hash": hash_password("pass-1234"),
            "role": role, "status": "active", "failed_logins": 0, "locked_until": None,
            "created_at": datetime.now(timezone.utc)}
    if with_nid:
        user |= {"nid_hash": hash_nid(f"19901234567{n:06d}"), "nid_last4": f"{n:04d}"}
    db.users.insert_one(user)
    browser = TestClient(app)
    assert browser.post("/api/v1/auth/login", json={"phone": phone, "password": "pass-1234"}, headers=SAFE).status_code == 200
    return browser


def report(**changes) -> dict:
    """A good report; pass changes to make it bad."""
    now = datetime.now(timezone(timedelta(hours=6)))
    body = {
        "theft_type": "phone_snatching",
        "occurred_at": (now - timedelta(hours=3)).isoformat(),
        **RAMNA,
        "landmark": "Near the Ramna park gate",
        "description": "Two men on a motorbike took my phone.",
        "stolen_items": "Samsung phone",
        "gd": {"type": "GD", "number": "1234", "date": now.date().isoformat(), "police_station": "ramna-model-ps"},
    }
    gd_changes = changes.pop("gd", {})
    body |= changes
    body["gd"] |= gd_changes
    return body


def send(browser, body):
    return browser.post("/api/v1/reports", json=body, headers=SAFE)


# ---------------------------------------------------------------- happy path
def test_send_a_report(db):
    victim = person(db)
    answer = send(victim, report())
    assert answer.status_code == 201, answer.text
    body = answer.json()
    assert body["status"] == "PENDING_REVIEW"  # R7: no SUBMITTED status
    assert body["thana"]["code"] == "ramna"
    assert body["gd"]["number"] == "1234" and body["gd"]["police_station"]["code"] == "ramna-model-ps"
    assert body["can_withdraw"] is True
    stored = db.reports.find_one()
    assert stored["gd_active"] is True and stored["ward_id"] is not None
    assert db.audit_logs.count_documents({"action": "report.create"}) >= 1


def test_options_for_the_form():
    body = TestClient(app).get("/api/v1/reports/options").json()
    assert len(body["theft_types"]) == 10
    assert {t["code"] for t in body["gd_types"]} == {"GD", "FIR"}
    assert len(body["police_stations"]) >= 30
    assert body["limits"]["per_day"] == 5 and body["gd_examples"]


# ---------------------------------------------------------------- who may report
def test_must_be_logged_in():
    assert send(TestClient(app), report()).status_code == 401


def test_staff_cannot_send_reports(db):
    assert send(person(db, role="verifier"), report()).status_code == 403


def test_nid_needed_before_the_first_report(db):
    answer = send(person(db, with_nid=False), report())
    assert answer.status_code == 403 and answer.json()["error"]["code"] == "nid_required"


# ---------------------------------------------------------------- the limits (FR-10)
def test_old_and_future_thefts_are_refused(db):
    victim = person(db)
    now = datetime.now(timezone.utc)
    old = send(victim, report(occurred_at=(now - timedelta(days=31)).isoformat(),
                              gd={"date": (now - timedelta(days=30)).date().isoformat()}))
    assert old.status_code == 422 and "30 days" in old.json()["error"]["fields"]["occurred_at"]
    future = send(victim, report(occurred_at=(now + timedelta(hours=2)).isoformat()))
    assert future.status_code == 422 and "future" in future.json()["error"]["fields"]["occurred_at"]


def test_gd_date_must_fit_the_theft(db):
    victim = person(db)
    before = send(victim, report(gd={"date": (datetime.now().date() - timedelta(days=5)).isoformat()}))
    assert before.status_code == 422 and "before the theft" in before.json()["error"]["fields"]["gd_date"]
    later = send(victim, report(gd={"date": (datetime.now().date() + timedelta(days=2)).isoformat()}))
    assert later.status_code == 422 and "future" in later.json()["error"]["fields"]["gd_date"]


def test_place_must_be_inside_dhaka(db):
    answer = send(person(db), report(lat=22.3569, lng=91.7832))  # Chattogram
    assert answer.status_code == 422 and "location" in answer.json()["error"]["fields"]


def test_unknown_police_station(db):
    answer = send(person(db), report(gd={"police_station": "atlantis-ps"}))
    assert answer.status_code == 422 and "gd_police_station" in answer.json()["error"]["fields"]


def test_at_most_five_reports_a_day(db):
    victim = person(db)
    for number in range(1, 6):
        assert send(victim, report(gd={"number": str(100 + number)})).status_code == 201
    sixth = send(victim, report(gd={"number": "106"}))
    assert sixth.status_code == 429 and sixth.json()["error"]["code"] == "too_many_reports"


# ---------------------------------------------------------------- one GD, one active report (R2)
def test_the_same_gd_cannot_be_reported_twice(db):
    assert send(person(db), report(gd={"number": "5555"})).status_code == 201
    again = send(person(db), report(gd={"number": "০৫৫৫৫"}))  # same GD written in Bangla digits with a 0
    assert again.status_code == 409 and again.json()["error"]["code"] == "gd_already_reported"


def test_same_number_at_another_station_is_a_different_gd(db):
    assert send(person(db), report(gd={"number": "7777"})).status_code == 201
    assert send(person(db), report(gd={"number": "7777", "police_station": "shahbagh-ps"})).status_code == 201


def test_withdrawing_frees_the_gd(db):
    first = person(db)
    sent = send(first, report(gd={"number": "8888"})).json()
    gone = first.post(f"/api/v1/me/reports/{sent['id']}/withdraw", headers=SAFE)
    assert gone.status_code == 200 and gone.json()["status"] == "WITHDRAWN" and gone.json()["can_withdraw"] is False
    assert send(person(db), report(gd={"number": "8888"})).status_code == 201  # the GD is free again


def test_a_decided_report_cannot_be_withdrawn(db):
    victim = person(db)
    sent = send(victim, report(gd={"number": "9999"})).json()
    db.reports.update_one({}, {"$set": {"status": "VERIFIED"}})
    answer = victim.post(f"/api/v1/me/reports/{sent['id']}/withdraw", headers=SAFE)
    assert answer.status_code == 409 and answer.json()["error"]["code"] == "cannot_withdraw"


def test_bad_gd_number(db):
    answer = send(person(db), report(gd={"number": "12#34"}))
    assert answer.status_code == 422 and "number" in answer.json()["error"]["fields"]


# ---------------------------------------------------------------- my reports
def test_my_reports_shows_only_mine(db):
    me, someone = person(db), person(db)
    mine = send(me, report(gd={"number": "4001"})).json()
    theirs = send(someone, report(gd={"number": "4002"})).json()
    listed = me.get("/api/v1/me/reports").json()["reports"]
    assert [r["id"] for r in listed] == [mine["id"]]
    assert me.get(f"/api/v1/me/reports/{mine['id']}").status_code == 200
    assert me.get(f"/api/v1/me/reports/{theirs['id']}").status_code == 404  # never someone else's
    assert me.get("/api/v1/me/reports/not-an-id").status_code == 404


def test_time_without_zone_is_dhaka_time(db):
    victim = person(db)
    local = (datetime.now(timezone(timedelta(hours=6))) - timedelta(hours=1)).replace(tzinfo=None, microsecond=0)
    sent = send(victim, report(occurred_at=local.isoformat())).json()
    stored = db.reports.find_one({"_id": ObjectId(sent["id"])})
    assert stored["occurred_at"] == local.replace(tzinfo=timezone(timedelta(hours=6))).astimezone(timezone.utc)


# ---------------------------------------------------------------- Task 15: GD check while typing
def test_gd_check_says_free_or_taken(db):
    victim = person(db)
    gd = {"type": "GD", "number": "6060", "date": datetime.now().date().isoformat(), "police_station": "ramna-model-ps"}
    check = lambda body: victim.post("/api/v1/reports/gd-check", json=body, headers=SAFE)  # noqa: E731
    assert check(gd).json() == {"free": True, "number": "6060"}
    assert send(person(db), report(gd={"number": "6060"})).status_code == 201
    assert check(gd).json()["free"] is False
    assert check(gd | {"number": "০৬০৬০"}).json()["free"] is False  # Bangla digits, leading 0: same GD
    assert check(gd | {"police_station": "shahbagh-ps"}).json()["free"] is True


def test_gd_check_needs_login_and_a_real_station(db):
    gd = {"type": "GD", "number": "1", "date": "2026-01-01", "police_station": "nowhere-ps"}
    assert TestClient(app).post("/api/v1/reports/gd-check", json=gd, headers=SAFE).status_code == 401
    answer = person(db).post("/api/v1/reports/gd-check", json=gd, headers=SAFE)
    assert answer.status_code == 422 and "gd_police_station" in answer.json()["error"]["fields"]


def test_gd_check_is_rate_limited(db):
    victim = person(db)
    gd = {"type": "GD", "number": "1", "date": "2026-01-01", "police_station": "ramna-model-ps"}
    codes = [victim.post("/api/v1/reports/gd-check", json=gd, headers=SAFE).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429
