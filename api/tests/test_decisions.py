"""
Tests for Task 19: approve, reject, ask for information, the victim's answer and the history.
"""
import random
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.config import settings
from app.db import database_status, get_db
from app.main import app
from app.modules.areas.service import load_area_file
from app.modules.reports.checks import km_between
from app.modules.reports.service import seed_gd_formats
from app.modules.review.decisions import move_point
from app.security import hash_nid, hash_password
from app.setup_db import apply_schema
from shapely.geometry import Point

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
    db.decisions.delete_many({})
    db.rate_counters.delete_many({})
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))


_n = iter(range(100, 999))


def account(db, role="victim"):
    n = next(_n)
    phone = f"+8801755000{n:03d}"
    user = {"name_en": f"{role} {n}", "phone": phone,
            "password_hash": hash_password("pass-1234"), "role": role, "status": "active", "failed_logins": 0,
            "locked_until": None, "created_at": datetime.now(timezone.utc)}
    if role == "victim":
        user |= {"nid_hash": hash_nid(f"1990444555{n:03d}"), "nid_last4": f"5{n}"}
    db.users.insert_one(user)
    browser = TestClient(app)
    browser.post("/api/v1/auth/login", json={"phone": phone, "password": "pass-1234"}, headers=SAFE)
    return browser


def new_report(victim, number="1234"):
    theft = datetime.now(DHAKA) - timedelta(hours=2)
    answer = victim.post("/api/v1/reports", headers=SAFE, json={
        "theft_type": "phone_snatching", "occurred_at": theft.isoformat(), "lat": 23.7457, "lng": 90.4047,
        "gd": {"type": "GD", "number": number, "date": theft.date().isoformat(), "police_station": "ramna-model-ps"}})
    assert answer.status_code == 201, answer.text
    return answer.json()["id"]


def decide(verifier, report_id, what, body=None, claim=True):
    if claim:
        assert verifier.post(f"/api/v1/review/{report_id}/claim", headers=SAFE).status_code == 200
    return verifier.post(f"/api/v1/review/{report_id}/{what}", json=body or {}, headers=SAFE)


def test_the_public_pin_moves_100_to_200_metres():
    rng = random.Random(7)
    for _ in range(200):
        lng, lat = move_point(90.4047, 23.7457, rng)
        metres = km_between(Point(90.4047, 23.7457), Point(lng, lat)) * 1000
        assert 99 <= metres <= 201


def test_approve(db, capsys):
    victim, verifier = account(db), account(db, "verifier")
    report_id = new_report(victim)
    answer = decide(verifier, report_id, "approve", {"note": "GD confirmed by phone"})
    assert answer.status_code == 200 and answer.json()["status"] == "VERIFIED"

    stored = db.reports.find_one({"_id": ObjectId(report_id)})
    assert stored["status"] == "VERIFIED" and "claim" not in stored and stored["gd_active"] is True
    exact, public = stored["location"]["coordinates"], stored["public_location"]["coordinates"]
    assert 99 <= km_between(Point(*exact), Point(*public)) * 1000 <= 201  # R8
    assert db.decisions.find_one({"report_id": ObjectId(report_id)})["decision"] == "approve"
    assert "verified" in capsys.readouterr().out  # the victim got a notice
    assert victim.get(f"/api/v1/me/reports/{report_id}").json()["status"] == "VERIFIED"


def test_deciding_needs_the_claim(db):
    victim, vera, omar = account(db), account(db, "verifier"), account(db, "verifier")
    report_id = new_report(victim)
    no_claim = decide(vera, report_id, "approve", claim=False)
    assert no_claim.status_code == 409 and no_claim.json()["error"]["code"] == "claim_required"
    vera.post(f"/api/v1/review/{report_id}/claim", headers=SAFE)
    stolen = omar.post(f"/api/v1/review/{report_id}/approve", json={}, headers=SAFE)  # Omar doesn't hold it
    assert stolen.status_code == 409
    # Vera's 15 minutes run out -> she must open it again
    db.reports.update_one({"_id": ObjectId(report_id)}, {"$set": {"claim.until": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    late = vera.post(f"/api/v1/review/{report_id}/approve", json={}, headers=SAFE)
    assert late.status_code == 409 and late.json()["error"]["code"] == "claim_required"


def test_a_failed_check_blocks_approval(db):
    victim, verifier = account(db), account(db, "verifier")
    report_id = new_report(victim, "4545")
    # Pretend ANOTHER report holds the same GD actively (only possible through a data error) -> "duplicate" fails
    twin = db.reports.find_one({"_id": ObjectId(report_id)})
    twin.pop("_id")
    db.reports.update_one({"_id": ObjectId(report_id)}, {"$set": {"gd_active": False}})
    db.reports.insert_one(twin | {"status": "VERIFIED"})
    answer = decide(verifier, report_id, "approve")
    assert answer.status_code == 409 and answer.json()["error"]["code"] == "check_failed"
    assert db.reports.find_one({"_id": ObjectId(report_id)})["status"] == "PENDING_REVIEW"


def test_reject_needs_a_reason_and_frees_the_gd(db):
    victim, verifier = account(db), account(db, "verifier")
    report_id = new_report(victim, "6060")
    no_words = decide(verifier, report_id, "reject", {"reason_code": "other"})
    assert no_words.status_code == 422 and "reason" in no_words.json()["error"]["fields"]
    answer = decide(verifier, report_id, "reject", {"reason_code": "gd_not_found"})
    assert answer.status_code == 200 and answer.json()["status"] == "REJECTED"
    mine = victim.get(f"/api/v1/me/reports/{report_id}").json()
    assert mine["status"] == "REJECTED" and "could not confirm the GD" in mine["reject_reason"]
    assert new_report(account(db), "6060")  # the GD is free again (R2)


def test_ask_info_then_the_victim_answers(db):
    victim, verifier = account(db), account(db, "verifier")
    report_id = new_report(victim, "7070")
    too_short = decide(verifier, report_id, "ask-info", {"question": "GD?"})
    assert too_short.status_code == 422
    asked = decide(verifier, report_id, "ask-info", {"question": "Please check the GD number. Ramna has no GD 7070 today."})
    assert asked.status_code == 200 and asked.json()["status"] == "NEEDS_INFO"
    mine = victim.get(f"/api/v1/me/reports/{report_id}").json()
    assert mine["info_request"].startswith("Please check") and mine["needs_info_until"]

    # The verifier can't approve it now: it waits for the victim
    assert decide(verifier, report_id, "approve", claim=False).status_code == 409

    answer = victim.put(f"/api/v1/me/reports/{report_id}", headers=SAFE, json={
        "answer": "Sorry, it was GD 7071.",
        "gd": {"type": "GD", "number": "7071", "date": datetime.now(DHAKA).date().isoformat(), "police_station": "ramna-model-ps"}})
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["status"] == "PENDING_REVIEW" and body["gd"]["number"] == "7071" and body["info_answer"] == "Sorry, it was GD 7071."
    assert victim.put(f"/api/v1/me/reports/{report_id}", headers=SAFE, json={"answer": "again"}).status_code == 409

    # Back in the queue, with the whole story in the history
    screen = verifier.get(f"/api/v1/review/{report_id}").json()
    actions = [step["action"] for step in screen["timeline"]]
    assert actions[0] == "report.create" and "report.ask_info" in actions and actions[-1] == "report.answer"
    assert all("name" not in step for step in screen["timeline"])
    assert screen["reject_reasons"][0]["code"] == "gd_not_found"


def test_victims_cannot_decide(db):
    victim = account(db)
    report_id = new_report(victim)
    assert victim.post(f"/api/v1/review/{report_id}/approve", json={}, headers=SAFE).status_code == 403


def test_decisions_are_kept(db):
    victim, verifier = account(db), account(db, "verifier")
    report_id = new_report(victim, "8080")
    decide(verifier, report_id, "ask-info", {"question": "Can you add a photo of the GD copy please?"})
    victim.put(f"/api/v1/me/reports/{report_id}", headers=SAFE, json={"answer": "I don't have it with me now."})
    decide(verifier, report_id, "approve")
    kinds = [d["decision"] for d in db.decisions.find({"report_id": ObjectId(report_id)}).sort("created_at", 1)]
    assert kinds == ["ask_info", "approve"]
