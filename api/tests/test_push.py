"""
Tests for Task 23: browser push notifications.
The real push services (Google, Mozilla, Apple) are replaced by a fake that records each message.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pywebpush import WebPushException

from app.config import settings
from app.db import database_status, get_db
from app.main import app
from app.modules.alerts import sender
from app.modules.areas.service import load_area_file
from app.modules.push import service as push
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
KEYS = {"p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM", "auth": "tBHItJI5svbpez7KI4CCXg"}


@pytest.fixture(scope="module", autouse=True)
def db():
    database = get_db()
    assert database.name == "safezone_test"
    database.client.drop_database(database.name)
    apply_schema(database)
    load_area_file(database)
    seed_gd_formats(database)
    build_network(database, phones=300, seed=4)
    yield database
    database.client.drop_database(database.name)


class FakePushService:
    """Stands in for pywebpush.webpush: remembers every message, or pretends a subscription is gone."""

    def __init__(self):
        self.sent: list[dict] = []
        self.gone: set[str] = set()

    def __call__(self, subscription_info, data, vapid_private_key, vapid_claims, ttl):
        if subscription_info["endpoint"] in self.gone:
            response = type("Response", (), {"status_code": 410})()
            raise WebPushException("Gone", response=response)
        self.sent.append({"endpoint": subscription_info["endpoint"], **json.loads(data)})


@pytest.fixture(autouse=True)
def fake_push(db, monkeypatch, tmp_path):
    for name in ("reports", "alerts", "virtual_inbox", "alert_deliveries", "push_subscriptions", "rate_counters"):
        db[name].delete_many({})
    monkeypatch.setattr(settings, "vapid_public_key", "BTestPublicKey")
    monkeypatch.setattr(settings, "vapid_private_key", "test-private-key")
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))
    fake = FakePushService()
    monkeypatch.setattr(push, "webpush", fake)
    return fake


_n = iter(range(100, 999))


def account(db, role="victim"):
    n = next(_n)
    phone = f"+8801799100{n:03d}"
    user = {"name_en": "Push Tester", "phone": phone, "password_hash": hash_password("pass-1234"),
            "role": role, "status": "active", "failed_logins": 0, "locked_until": None, "created_at": datetime.now(timezone.utc)}
    if role == "victim":
        user |= {"nid_hash": hash_nid(f"1990121212{n:03d}"), "nid_last4": f"1{n}"}
    db.users.insert_one(user)
    browser = TestClient(app)
    browser.post("/api/v1/auth/login", json={"phone": phone, "password": "pass-1234"}, headers=SAFE)
    return browser


def follow(browser, endpoint, areas, lang="en"):
    return browser.post("/api/v1/push/subscribe", headers=SAFE,
                        json={"endpoint": endpoint, "keys": KEYS, "areas": areas, "lang": lang})


def send_ramna_alert(db, victim=None):
    victim = victim or account(db)
    staff = account(db, "verifier")
    theft = datetime.now(DHAKA) - timedelta(hours=1)
    report_id = victim.post("/api/v1/reports", headers=SAFE, json={
        "theft_type": "bag_snatching", "occurred_at": theft.isoformat(), "lat": 23.7457, "lng": 90.4047,
        "gd": {"type": "GD", "number": str(next(_n)), "date": theft.date().isoformat(), "police_station": "ramna-model-ps"}}).json()["id"]
    staff.post(f"/api/v1/review/{report_id}/claim", headers=SAFE)
    assert staff.post(f"/api/v1/review/{report_id}/approve", json={}, headers=SAFE).status_code == 200
    sender.run_once()
    return db.alerts.find_one({"report_id": ObjectId(report_id)})


def test_the_public_key():
    assert TestClient(app).get("/api/v1/push/key").json() == {"enabled": True, "public_key": "BTestPublicKey"}


def test_follow_change_and_stop(db):
    browser = TestClient(app)  # a visitor, not logged in
    endpoint = "https://push.example.com/send/abc123"
    answer = follow(browser, endpoint, ["gulshan", "dcc-w19"])
    assert answer.status_code == 200 and {a["code"] for a in answer.json()["areas"]} == {"gulshan", "dcc-w19"}
    follow(browser, endpoint, ["ramna"])  # the same browser again: updated, not doubled
    assert db.push_subscriptions.count_documents({}) == 1
    assert browser.post("/api/v1/push/status", headers=SAFE, json={"endpoint": endpoint}).json()["areas"][0]["code"] == "ramna"
    assert browser.post("/api/v1/push/unsubscribe", headers=SAFE, json={"endpoint": endpoint}).json()["subscribed"] is False
    assert db.push_subscriptions.count_documents({}) == 0


def test_bad_subscriptions_are_refused(db):
    browser = TestClient(app)
    assert follow(browser, "https://push.example.com/1", ["atlantis"]).status_code == 422
    assert follow(browser, "https://push.example.com/2", [f"dcc-w{i:02d}" for i in range(1, 12)]).status_code == 422
    assert follow(browser, "not a web address", ["ramna"]).status_code == 422


def test_followers_of_the_area_get_the_alert(db, fake_push):
    follow(TestClient(app), "https://push.example.com/ramna-en", ["ramna"])
    follow(TestClient(app), "https://push.example.com/ramna-bn", ["ramna"], lang="bn")
    follow(TestClient(app), "https://push.example.com/uttara", ["uttara"])

    alert = send_ramna_alert(db)
    endpoints = {m["endpoint"]: m for m in fake_push.sent}
    assert set(endpoints) == {"https://push.example.com/ramna-en", "https://push.example.com/ramna-bn"}  # not Uttara
    assert endpoints["https://push.example.com/ramna-en"]["body"] == alert["text_en"]
    assert endpoints["https://push.example.com/ramna-bn"]["body"] == alert["text_bn"]  # in Bangla for Bangla readers
    assert endpoints["https://push.example.com/ramna-en"]["url"] == f"/alerts/{alert['_id']}"
    assert alert["push_sent"] == 2 and alert["push_failed"] == 0
    assert db.alert_deliveries.count_documents({"alert_id": alert["_id"], "channel": "web_push"}) == 2


def test_a_dead_subscription_is_removed(db, fake_push):
    follow(TestClient(app), "https://push.example.com/old-phone", ["ramna"])
    fake_push.gone.add("https://push.example.com/old-phone")
    alert = send_ramna_alert(db)
    assert alert["push_failed"] == 1
    assert db.push_subscriptions.count_documents({}) == 0


def test_the_victim_hears_about_their_own_report(db, fake_push):
    victim = account(db)
    follow(victim, "https://push.example.com/victims-phone", [])  # logged in: linked to the account, no areas
    send_ramna_alert(db, victim)
    titles = [m["title"] for m in fake_push.sent if m["endpoint"] == "https://push.example.com/victims-phone"]
    assert "Your SafeZone report was verified" in titles and "Your alert was sent" in titles


def test_push_switched_off_without_keys(db, monkeypatch, fake_push):
    monkeypatch.setattr(settings, "vapid_private_key", "")
    assert TestClient(app).get("/api/v1/push/key").json()["enabled"] is False
    follow(TestClient(app), "https://push.example.com/ramna", ["ramna"])
    alert = send_ramna_alert(db)
    assert fake_push.sent == [] and alert["status"] == "sent"  # the alert still goes to the phones


def test_following_shows_the_areas_latest_real_alert(db, fake_push, monkeypatch):
    browser = account(db)
    # In the tests the background jobs are off, so the 5-second timer is not started at all
    answer = follow(browser, "https://push.example/t1", ["ramna"]).json()
    assert answer["test_alert_in"] is None and answer["first_alert"] is None and fake_push.sent == []

    monkeypatch.setattr(settings, "follow_test_alert_seconds", 0)  # 0 = send it right away
    # No alert in Ramna yet: a short "alerts are on" note
    answer = follow(browser, "https://push.example/t2", ["ramna"]).json()
    assert answer["test_alert_in"] == 0 and fake_push.sent[-1]["tag"] == "alert-on-ramna"
    assert fake_push.sent[-1]["title"] == "Alerts for Ramna are on" and fake_push.sent[-1]["test"] is True

    # A real alert in Ramna: a new follower gets exactly that alert (same text, its own page)
    alert = send_ramna_alert(db)
    fake_push.sent.clear()
    answer = follow(browser, "https://push.example/t3", ["ramna"]).json()
    first = fake_push.sent[-1]
    assert first["title"] == "Bag snatching · Ramna" and first["url"] == f"/alerts/{alert['_id']}"
    assert first["tag"] == f"alert-{alert['_id']}" and first["test"] is False
    assert first["body"].startswith("SafeZone alert: Bag snatching near Ramna")
    assert answer["first_alert"] == {"title": first["title"], "body": first["body"], "url": first["url"], "test": False}

    # Following the same area again: nothing new. Stopping: nothing. A Bangla browser: Bangla
    follow(browser, "https://push.example/t3", ["ramna"])
    follow(browser, "https://push.example/t3", [])
    assert len(fake_push.sent) == 1
    follow(browser, "https://push.example/t4", ["ramna"], lang="bn")
    assert fake_push.sent[-1]["title"] == "ব্যাগ ছিনতাই · রমনা"
