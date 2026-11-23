"""
Tests for Task 18: the review queue, claiming a report for 15 minutes, and the review screen.
"""
import io
import threading
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.db import database_status, get_db
from app.errors import AppError
from app.main import app
from app.modules.areas.service import load_area_file
from app.modules.reports.service import seed_gd_formats
from app.modules.review import service as review
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
    db.rate_counters.delete_many({})
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))


_n = iter(range(100, 999))


def account(db, role="victim", name="Tester"):
    n = next(_n)
    phone = f"+8801744000{n:03d}"
    user = {"name_en": name, "phone": phone, "password_hash": hash_password("pass-1234"),
            "role": role, "status": "active", "failed_logins": 0, "locked_until": None,
            "created_at": datetime.now(timezone.utc) - timedelta(days=40)}
    if role == "victim":
        user |= {"nid_hash": hash_nid(f"1990222333{n:03d}"), "nid_last4": f"9{n}"}
    user["_id"] = db.users.insert_one(user).inserted_id
    browser = TestClient(app)
    assert browser.post("/api/v1/auth/login", json={"phone": phone, "password": "pass-1234"}, headers=SAFE).status_code == 200
    return browser, user


def new_report(browser, number, hours_ago=2):
    theft = datetime.now(DHAKA) - timedelta(hours=hours_ago)
    answer = browser.post("/api/v1/reports", headers=SAFE, json={
        "theft_type": "bag_snatching", "occurred_at": theft.isoformat(), "lat": 23.7457, "lng": 90.4047,
        "stolen_items": "Handbag", "gd": {"type": "GD", "number": number, "date": theft.date().isoformat(),
                                          "police_station": "ramna-model-ps"}})
    assert answer.status_code == 201, answer.text
    return answer.json()["id"]


def test_only_staff_see_the_queue(db):
    victim, _ = account(db)
    assert victim.get("/api/v1/review/queue").status_code == 403
    assert TestClient(app).get("/api/v1/review/queue").status_code == 401


def test_queue_is_oldest_first(db):
    victim, _ = account(db)
    first = new_report(victim, "101")
    second = new_report(victim, "102")
    db.reports.update_one({"_id": ObjectId(second)}, {"$set": {"submitted_at": datetime.now(timezone.utc) - timedelta(hours=5)}})
    verifier, _ = account(db, "verifier", "Vera")
    waiting = verifier.get("/api/v1/review/queue").json()["waiting"]
    assert [r["id"] for r in waiting] == [second, first]  # the older one first
    assert waiting[0]["risk"]["level"] in ("low", "medium", "high") and waiting[0]["thana"]["code"] == "ramna"


def test_claim_holds_the_report_for_one_verifier(db):
    victim, _ = account(db)
    report_id = new_report(victim, "201")
    vera, _ = account(db, "verifier", "Vera")
    omar, _ = account(db, "verifier", "Omar")

    mine = vera.post(f"/api/v1/review/{report_id}/claim", headers=SAFE)
    assert mine.status_code == 200 and mine.json()["claim"]["mine"] is True
    taken = omar.post(f"/api/v1/review/{report_id}/claim", headers=SAFE)
    assert taken.status_code == 409 and taken.json()["error"]["code"] == "claimed_by_other"
    assert "Vera" in taken.json()["error"]["message"]
    assert vera.post(f"/api/v1/review/{report_id}/claim", headers=SAFE).status_code == 200  # renewing my own hold

    # Omar's queue shows that Vera holds it
    card = omar.get("/api/v1/review/queue").json()["waiting"][0]
    assert card["claim"]["mine"] is False and card["claim"]["by_name"] == "Vera"

    # After 15 minutes the hold runs out and Omar may take it
    db.reports.update_one({"_id": ObjectId(report_id)}, {"$set": {"claim.until": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    assert omar.post(f"/api/v1/review/{report_id}/claim", headers=SAFE).status_code == 200


def test_release_lets_someone_else_claim(db):
    victim, _ = account(db)
    report_id = new_report(victim, "301")
    vera, _ = account(db, "verifier", "Vera")
    omar, _ = account(db, "verifier", "Omar")
    vera.post(f"/api/v1/review/{report_id}/claim", headers=SAFE)
    vera.post(f"/api/v1/review/{report_id}/release", headers=SAFE)
    assert omar.post(f"/api/v1/review/{report_id}/claim", headers=SAFE).status_code == 200


def test_two_verifiers_at_the_same_moment_only_one_wins(db):
    victim, _ = account(db)
    report_id = new_report(victim, "401")
    people = [account(db, "verifier", f"V{i}")[1] for i in range(8)]
    start = threading.Barrier(len(people))
    results = []

    def try_claim(user):
        start.wait()  # everybody clicks at exactly the same time
        try:
            review.claim(user, report_id)
            results.append("won")
        except AppError as error:
            results.append(error.code)

    threads = [threading.Thread(target=try_claim, args=(p,)) for p in people]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("won") == 1 and results.count("claimed_by_other") == len(people) - 1


def test_closed_reports_cannot_be_claimed(db):
    victim, _ = account(db)
    report_id = new_report(victim, "501")
    victim.post(f"/api/v1/me/reports/{report_id}/withdraw", headers=SAFE)
    vera, _ = account(db, "verifier")
    answer = vera.post(f"/api/v1/review/{report_id}/claim", headers=SAFE)
    assert answer.status_code == 409 and answer.json()["error"]["code"] == "not_reviewable"
    assert vera.post(f"/api/v1/review/{ObjectId()}/claim", headers=SAFE).status_code == 404


def test_review_screen_has_everything_but_no_personal_details(db):
    victim, victim_user = account(db, name="Secret Name")
    report_id = new_report(victim, "601")
    image = io.BytesIO()
    Image.new("RGB", (300, 200), "red").save(image, "JPEG")
    victim.post(f"/api/v1/me/reports/{report_id}/photos", headers=SAFE, data={"kind": "gd_copy"},
                files={"file": ("gd.jpg", image.getvalue(), "image/jpeg")})

    admin, _ = account(db, "admin")
    screen = admin.get(f"/api/v1/review/{report_id}")
    assert screen.status_code == 200
    body = screen.json()
    assert {c["code"] for c in body["checks"]} >= {"gd_format", "duplicate", "gd_copy"}
    assert "score" in body["risk"] and body["gd"]["police_station"]["code"] == "ramna-model-ps"
    assert body["reporter"]["account_days"] >= 40 and body["reporter"]["nid_added"] is True
    assert "Secret Name" not in screen.text and victim_user["phone"] not in screen.text  # R8
    # Staff can open the photo; the victim can't use the staff address
    photo_url = body["photos"][0]["url"]
    assert admin.get(photo_url).status_code == 200
    assert victim.get(photo_url).status_code == 403


def test_renewing_my_hold_is_not_a_new_history_line(db):
    victim, _ = account(db)
    report_id = new_report(victim, "701")
    vera, _ = account(db, "verifier")
    for _ in range(3):
        vera.post(f"/api/v1/review/{report_id}/claim", headers=SAFE)
    assert db.audit_logs.count_documents({"action": "report.claim", "entity_id": ObjectId(report_id)}) == 1
