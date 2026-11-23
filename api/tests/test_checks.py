"""
Tests for Task 17: the automatic checks and the risk score.
"""
import io
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.db import database_status, get_db
from app.main import app
from app.modules.areas.service import load_area_file
from app.modules.reports.checks import risk_score, run_checks
from app.modules.reports.service import seed_gd_formats
from app.security import hash_nid, hash_password
from app.settings_store import save_setting
from app.setup_db import apply_schema

pytestmark = pytest.mark.skipif(
    not database_status()["ok"],
    reason="Database not running. Start it: Terminal -> Run Task -> 'SafeZone: start database'",
)
SAFE = {"X-SafeZone": "1"}
DHAKA = timezone(timedelta(hours=6))
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
def clean(db, tmp_path, monkeypatch):
    db.reports.delete_many({})
    db.report_photos.delete_many({})
    db.settings.delete_many({})
    db.rate_counters.delete_many({})
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))


_n = iter(range(100, 999))


def victim(db):
    n = next(_n)
    phone = f"+8801733000{n:03d}"
    user_id = db.users.insert_one({
        "name_en": "Check Tester", "phone": phone,
        "password_hash": hash_password("pass-1234"), "role": "victim", "status": "active", "failed_logins": 0,
        "locked_until": None, "created_at": datetime.now(timezone.utc),
        "nid_hash": hash_nid(f"1990111222{n:03d}"), "nid_last4": f"0{n}"}).inserted_id
    browser = TestClient(app)
    browser.post("/api/v1/auth/login", json={"phone": phone, "password": "pass-1234"}, headers=SAFE)
    return browser, user_id


def form(number="1234", station="ramna-model-ps", hours_ago=2, gd_days_after=0, spot=RAMNA, **extra):
    theft = datetime.now(DHAKA) - timedelta(hours=hours_ago)
    gd_day = min((theft + timedelta(days=gd_days_after)).date(), datetime.now(DHAKA).date())
    return {"theft_type": "phone_snatching", "occurred_at": theft.isoformat(), **spot,
            "gd": {"type": "GD", "number": number, "date": gd_day.isoformat(), "police_station": station}, **extra}


def send(browser, body, db):
    answer = browser.post("/api/v1/reports", json=body, headers=SAFE)
    assert answer.status_code == 201, answer.text
    return db.reports.find_one({"_id": ObjectId(answer.json()["id"])})


def by_code(report) -> dict:
    return {c["code"]: c for c in report["checks"]}


def test_a_clean_report_passes_almost_everything(db):
    browser, _ = victim(db)
    report = send(browser, form(), db)
    checks = by_code(report)
    assert set(checks) == {"gd_format", "gd_timing", "place_in_gd_thana", "duplicate", "history", "gd_copy", "ocr_match"}
    assert [c for c in checks.values() if c["result"] != "pass"] == [checks["gd_copy"]]  # only: no GD copy yet
    assert report["risk"]["score"] == 10 and report["risk"]["level"] == "low"
    assert checks["place_in_gd_thana"]["message_bn"]  # every message also in Bangla

    # Adding a GD copy photo re-runs the checks: everything passes, score 0
    image = io.BytesIO()
    Image.new("RGB", (300, 400), "white").save(image, "JPEG")
    browser.post(f"/api/v1/me/reports/{report['_id']}/photos", headers=SAFE, data={"kind": "gd_copy"},
                 files={"file": ("gd.jpg", image.getvalue(), "image/jpeg")})
    again = db.reports.find_one({"_id": report["_id"]})
    assert all(c["result"] == "pass" for c in again["checks"]) and again["risk"]["score"] == 0


def test_strange_gd_number(db):
    report = send(victim(db)[0], form(number="AB/12"), db)
    assert by_code(report)["gd_format"]["result"] == "warning"


def test_gd_filed_late(db):
    report = send(victim(db)[0], form(hours_ago=24 * 20, gd_days_after=20), db)
    timing = by_code(report)["gd_timing"]
    assert timing["result"] == "warning" and timing["days"] >= 19


def test_place_far_from_the_gd_thana(db):
    report = send(victim(db)[0], form(station="uttara-east-ps"), db)  # theft in Ramna, GD in Uttara
    place = by_code(report)["place_in_gd_thana"]
    assert place["result"] == "warning" and place["km"] > 5


def test_nearby_report_at_the_same_time(db):
    first = send(victim(db)[0], form(number="5001"), db)
    second = send(victim(db)[0], form(number="5002", hours_ago=1), db)
    duplicate = by_code(second)["duplicate"]
    assert duplicate["result"] == "warning" and duplicate["report_ids"] == [str(first["_id"])]
    far_later = send(victim(db)[0], form(number="5003", hours_ago=26, gd_days_after=1), db)
    assert by_code(far_later)["duplicate"]["result"] == "pass"  # same place, but a day apart


def test_rejected_history(db):
    browser, user_id = victim(db)
    for number in ("7001", "7002"):
        old = send(browser, form(number=number, spot={"lat": 23.80, "lng": 90.36}, station="mirpur-model-ps"), db)
        db.reports.update_one({"_id": old["_id"]}, {"$set": {"status": "REJECTED", "gd_active": False}})
    report = send(browser, form(number="7003"), db)
    history = by_code(report)["history"]
    assert history["result"] == "warning" and history["count"] == 2
    reason = next(r for r in report["risk"]["reasons"] if r["code"] == "history")
    assert reason["points"] == 30  # 15 points per rejected report, counted up to 2


def test_same_active_gd_fails_and_scores_100(db):
    first = send(victim(db)[0], form(number="8008"), db)
    twin = dict(first, _id=None)  # the same GD again, as if it were a new report
    checks = run_checks(twin, db)
    assert next(c for c in checks if c["code"] == "duplicate")["result"] == "fail"
    assert risk_score(checks)["score"] == 100 and risk_score(checks)["level"] == "high"


def test_admin_points_change_the_score(db):
    save_setting("risk_points", {"gd_copy": 40})
    report = send(victim(db)[0], form(number="9009"), db)
    assert report["risk"]["score"] == 40 and report["risk"]["level"] == "medium"


def test_victim_sees_tips_but_never_the_score(db):
    browser, _ = victim(db)
    answer = browser.post("/api/v1/reports/precheck", headers=SAFE, json=form(station="uttara-east-ps", number="AB/1"))
    assert answer.status_code == 200
    codes = {tip["code"] for tip in answer.json()["tips"]}
    assert codes == {"gd_format", "place_in_gd_thana", "gd_copy"}
    assert "score" not in answer.text and "risk" not in answer.text
    with_copy = browser.post("/api/v1/reports/precheck", headers=SAFE, json=form() | {"has_gd_copy": True}).json()
    assert with_copy["tips"] == []
    # The victim's own report view never contains checks or the risk score
    report = send(browser, form(number="4444"), db)
    mine = browser.get(f"/api/v1/me/reports/{report['_id']}").json()
    assert "checks" not in mine and "risk" not in mine
    assert db.reports.count_documents({}) == 1  # the precheck saved nothing
