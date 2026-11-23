"""
Tests for Task 20: the alert template, the privacy filter, and creating the alert on approval.
"""
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from app.config import settings
from app.db import database_status, get_db
from app.main import app
from app.modules.alerts.privacy import check_text
from app.modules.alerts.text import template
from app.modules.areas.service import load_area_file
from app.modules.reports.service import seed_gd_formats
from app.schema import THEFT_TYPES
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
    yield database
    database.client.drop_database(database.name)


@pytest.fixture(autouse=True)
def clean(db, tmp_path, monkeypatch):
    db.reports.delete_many({})
    db.alerts.delete_many({})
    db.rate_counters.delete_many({})
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))


_n = iter(range(100, 999))


def account(db, role="victim", name="Nila Rahman"):
    n = next(_n)
    phone = f"+8801766000{n:03d}"
    user = {"name_en": name, "name_bn": "নীলা রহমান", "phone": phone,
            "password_hash": hash_password("pass-1234"), "role": role, "status": "active", "failed_logins": 0,
            "locked_until": None, "created_at": datetime.now(timezone.utc)}
    if role == "victim":
        user |= {"nid_hash": hash_nid(f"1990666777{n:03d}"), "nid_last4": f"7{n}"}
    db.users.insert_one(user)
    browser = TestClient(app)
    browser.post("/api/v1/auth/login", json={"phone": phone, "password": "pass-1234"}, headers=SAFE)
    return browser


def new_report(victim, number, theft_type="phone_snatching"):
    theft = datetime.now(DHAKA) - timedelta(hours=1)
    answer = victim.post("/api/v1/reports", headers=SAFE, json={
        "theft_type": theft_type, "occurred_at": theft.isoformat(), "lat": 23.7932, "lng": 90.4144,
        "landmark": "House 12, Road 5", "stolen_items": "Samsung A54",
        "gd": {"type": "GD", "number": number, "date": theft.date().isoformat(), "police_station": "gulshan-ps"}})
    assert answer.status_code == 201, answer.text
    return answer.json()["id"]


# ---------------------------------------------------------------- the privacy filter
@pytest.mark.parametrize("text, code", [
    ("Call 01712345678 for details", "phone"),
    ("Call +880 1712-345678", "phone"),
    ("ফোন ০১৭১২৩৪৫৬৭৮", "phone"),
    ("Write to someone@example.com", "email"),
    ("GD no. 4512 was filed", "gd_number"),
    ("জিডি নং ৪৫১২", "gd_number"),
    ("Near House 12", "house_number"),
    ("Flat 3B was broken into", "house_number"),
    ("বাড়ি ১২ এর সামনে", "house_number"),
    ("Tokai boys did it", "blaming"),
    ("রোহিঙ্গা লোকেরা নিয়েছে", "blaming"),
])
def test_the_filter_catches_private_details(text, code):
    assert code in {p["code"] for p in check_text(text)}


def test_names_and_this_gd_number_are_caught():
    codes = {p["code"] for p in check_text("Nila lost her phone, GD 7788 at night", ["Nila"], "7788")}
    assert {"name", "gd_number"} <= codes


def test_a_normal_warning_is_fine():
    assert check_text("Phone snatching near Gulshan (Ward 19) around 9 PM today. Stay alert.") == []


# ---------------------------------------------------------------- the template
def test_template_uses_only_safe_facts(db):
    victim = account(db)
    report = db.reports.find_one({"_id": ObjectId(new_report(victim, "9001"))})
    texts = template(report)
    assert "Gulshan" in texts["text_en"] and "গুলশান" in texts["text_bn"]
    assert "Phone snatching" in texts["text_en"] and "ফোন ছিনতাইয়ের" in texts["text_bn"]
    for text in texts.values():
        assert "9001" not in text and "House" not in text and "Samsung" not in text and "Nila" not in text
        assert check_text(text, ["Nila", "Rahman"], "9001") == []


def test_template_passes_the_filter_for_every_theft_type(db):
    victim = account(db)
    for i, kind in enumerate(THEFT_TYPES):
        report = db.reports.find_one({"_id": ObjectId(new_report(victim, f"91{i:02d}", kind))}) if i < 5 else None
        if report is None:  # only 5 reports a day per person: build the rest in memory
            report = dict(db.reports.find_one(), theft_type=kind)
        texts = template(report)
        assert check_text(texts["text_en"]) == [] and check_text(texts["text_bn"]) == [], kind


# ---------------------------------------------------------------- the review endpoints
def test_preview_and_check(db):
    report_id = new_report(account(db), "9200")
    staff = account(db, "verifier", "Vera")
    preview = staff.get(f"/api/v1/review/{report_id}/alert-preview").json()
    assert preview["radius_m"] == 1000 and preview["problems"] == {"en": [], "bn": []}
    bad = staff.post(f"/api/v1/review/{report_id}/alert-check", headers=SAFE,
                     json={"text_en": "Nila Rahman (01712345678) lost her phone", "text_bn": preview["text_bn"]}).json()
    assert bad["ok"] is False and {"name", "phone"} <= {p["code"] for p in bad["problems"]["en"]}


def test_a_ward_can_have_its_own_radius(db):
    report_id = new_report(account(db), "9300")
    ward_id = db.reports.find_one({"_id": ObjectId(report_id)})["ward_id"]
    db.areas.update_one({"_id": ward_id}, {"$set": {"alert_radius_m": 1500}})
    staff = account(db, "verifier")
    assert staff.get(f"/api/v1/review/{report_id}/alert-preview").json()["radius_m"] == 1500
    db.areas.update_one({"_id": ward_id}, {"$set": {"alert_radius_m": 1000}})


# ---------------------------------------------------------------- approval creates the alert
def approve(staff, report_id, body=None):
    staff.post(f"/api/v1/review/{report_id}/claim", headers=SAFE)
    return staff.post(f"/api/v1/review/{report_id}/approve", json=body or {}, headers=SAFE)


def test_approve_creates_one_queued_alert(db):
    report_id = new_report(account(db), "9400")
    answer = approve(account(db, "verifier"), report_id)
    assert answer.status_code == 200
    alert = db.alerts.find_one({"report_id": ObjectId(report_id)})
    assert alert["status"] == "queued" and alert["radius_m"] == 1000 and alert["text_en"].startswith("SafeZone alert:")
    assert db.reports.find_one({"_id": ObjectId(report_id)})["alert_text"]["source"] == "template"
    with pytest.raises(DuplicateKeyError):  # NFR-1: a second alert for the same report is impossible
        db.alerts.insert_one(dict(alert, _id=ObjectId()))


def test_an_unsafe_edited_text_blocks_approval(db):
    report_id = new_report(account(db), "9500")
    staff = account(db, "verifier")
    answer = approve(staff, report_id, {"text_en": "Phone stolen from House 12. Call 01712345678.", "text_bn": "সতর্ক থাকুন।"})
    assert answer.status_code == 422 and answer.json()["error"]["code"] == "alert_privacy"
    assert "House" in answer.json()["error"]["fields"]["text_en"] or "house" in answer.json()["error"]["fields"]["text_en"].lower()
    assert db.reports.find_one({"_id": ObjectId(report_id)})["status"] == "PENDING_REVIEW"
    assert db.alerts.count_documents({}) == 0  # nothing was sent


def test_a_safe_edited_text_is_used(db):
    report_id = new_report(account(db), "9600")
    body = {"text_en": "SafeZone alert: phone snatching near Gulshan 2 circle this morning. Stay alert.",
            "text_bn": "সেফজোন সতর্কবার্তা: আজ সকালে গুলশান ২ গোলচত্বরে ফোন ছিনতাই হয়েছে। সতর্ক থাকুন।"}
    assert approve(account(db, "verifier"), report_id, body).status_code == 200
    alert = db.alerts.find_one({"report_id": ObjectId(report_id)})
    assert alert["text_en"] == body["text_en"] and alert["text_bn"] == body["text_bn"]
    assert db.reports.find_one({"_id": ObjectId(report_id)})["alert_text"]["source"] == "edited"


def test_a_name_that_is_also_a_place_does_not_block_the_template(db):
    # Found in a live test: a victim whose name is also a word of the template (here "Gulshan", the area)
    # could never be approved, because the filter saw "her name" in "...near Gulshan...".
    report_id = new_report(account(db, name="Gulshan Akter"), "9700")
    staff = account(db, "verifier")
    assert approve(staff, report_id).status_code == 200  # the template is fine
    # ...but her other name part is still caught when a verifier types it
    other = new_report(account(db, name="Gulshan Akter"), "9701")
    answer = approve(staff, other, {"text_en": "Phone snatched from Akter near Gulshan.", "text_bn": "সতর্ক থাকুন।"})
    assert answer.status_code == 422 and "name" in answer.json()["error"]["fields"]["text_en"]
