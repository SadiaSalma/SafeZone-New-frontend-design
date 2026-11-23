"""
Tests for Task 9: staying logged in (refresh), logging out, the password-guessing
locks, and staff-only doors (roles). They use the test database.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.db import database_status, get_db
from app.deps import ACCESS_COOKIE, REFRESH_COOKIE, require_roles
from app.errors import register_error_handlers
from app.main import app
from app.modules.auth import routes as auth_routes
from app.modules.auth import service as auth_service
from app.security import hash_password
from app.setup_db import apply_schema

pytestmark = pytest.mark.skipif(
    not database_status()["ok"],
    reason="Database not running. Start it: Terminal -> Run Task -> 'SafeZone: start database'",
)
SAFE = {"X-SafeZone": "1"}
PASSWORD = "safe-pass-123"


@pytest.fixture(scope="module")
def db():
    database = get_db()
    assert database.name == "safezone_test"
    database.client.drop_database(database.name)
    apply_schema(database)
    yield database
    database.client.drop_database(database.name)


@pytest.fixture(autouse=True)
def clean_counters(db):
    db.rate_counters.delete_many({})
    db.login_attempts.delete_many({})


def make_user(db, phone, role="victim"):
    """Put a ready, active account straight into the database (quicker than signing up)."""
    db.users.insert_one({
        "name_en": "Test Person", "phone": phone,
        "password_hash": hash_password(PASSWORD), "role": role, "status": "active",
        "failed_logins": 0, "locked_until": None, "created_at": datetime.now(timezone.utc),
    })


def log_in(client, phone, password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"phone": phone, "password": password}, headers=SAFE)


# ------------------------------------------------------------------ refresh + logout
def test_refresh_gives_a_new_pair_of_tickets(db):
    make_user(db, "+8801911000001")
    client = TestClient(app)
    log_in(client, "+8801911000001")
    old_refresh = client.cookies[REFRESH_COOKIE]

    response = client.post("/api/v1/auth/refresh", headers=SAFE)
    assert response.status_code == 200
    assert client.cookies[REFRESH_COOKIE] != old_refresh  # a brand-new long ticket
    assert client.get("/api/v1/me").status_code == 200


def test_reused_ticket_logs_the_account_out_everywhere(db, monkeypatch):
    """If a used long ticket comes back, it was probably stolen -> cancel every session."""
    monkeypatch.setattr(auth_service, "REUSE_GRACE_SECONDS", -1)  # no grace time in this test
    make_user(db, "+8801911000002")
    client = TestClient(app)
    log_in(client, "+8801911000002")
    stolen = client.cookies[REFRESH_COOKIE]
    client.post("/api/v1/auth/refresh", headers=SAFE)  # the real owner refreshes (ticket used up)

    thief = TestClient(app, cookies={REFRESH_COOKIE: stolen})
    assert thief.post("/api/v1/auth/refresh", headers=SAFE).status_code == 401
    # The owner's newest ticket was cancelled too: they must log in again
    assert client.post("/api/v1/auth/refresh", headers=SAFE).status_code == 401
    user = db.users.find_one({"phone": "+8801911000002"})
    assert db.sessions.count_documents({"user_id": user["_id"], "revoked_at": None}) == 0


def test_refresh_without_a_ticket_is_refused(db):
    assert TestClient(app).post("/api/v1/auth/refresh", headers=SAFE).status_code == 401


def test_logout_removes_cookies_and_cancels_the_ticket(db):
    make_user(db, "+8801911000003")
    client = TestClient(app)
    log_in(client, "+8801911000003")
    ticket = client.cookies[REFRESH_COOKIE]

    assert client.post("/api/v1/auth/logout", headers=SAFE).status_code == 200
    assert ACCESS_COOKIE not in client.cookies and REFRESH_COOKIE not in client.cookies
    assert client.get("/api/v1/me").status_code == 401
    # The cancelled ticket cannot be used again
    again = TestClient(app, cookies={REFRESH_COOKIE: ticket})
    assert again.post("/api/v1/auth/refresh", headers=SAFE).status_code == 401


# ------------------------------------------------------------------ password-guessing locks
def test_ten_wrong_passwords_lock_that_device_only(db, monkeypatch):
    make_user(db, "+8801911000004")
    monkeypatch.setattr(auth_routes, "client_ip", lambda request: "10.0.0.1")  # the attacker's device
    attacker = TestClient(app)
    for _ in range(10):
        assert log_in(attacker, "+8801911000004", "wrong-pass-1").status_code == 401

    # Even the right password is refused from that device now
    locked = log_in(attacker, "+8801911000004")
    assert locked.status_code == 429
    assert locked.json()["error"]["code"] == "too_many_wrong_logins"

    # The real owner on another device can still log in
    monkeypatch.setattr(auth_routes, "client_ip", lambda request: "10.0.0.2")
    assert log_in(TestClient(app), "+8801911000004").status_code == 200


def test_device_lock_ends_after_15_minutes(db, monkeypatch):
    make_user(db, "+8801911000005")
    monkeypatch.setattr(auth_routes, "client_ip", lambda request: "10.0.0.3")
    client = TestClient(app)
    for _ in range(10):
        log_in(client, "+8801911000005", "wrong-pass-1")
    assert log_in(client, "+8801911000005").status_code == 429

    # Pretend 16 minutes have passed: move the wrong tries into the past
    db.login_attempts.update_many({"phone": "+8801911000005"}, {"$set": {"at": datetime.now(timezone.utc) - timedelta(minutes=16)}})
    assert log_in(client, "+8801911000005").status_code == 200


def test_correct_password_resets_the_count(db, monkeypatch):
    make_user(db, "+8801911000006")
    monkeypatch.setattr(auth_routes, "client_ip", lambda request: "10.0.0.4")
    client = TestClient(app)
    for _ in range(9):
        log_in(client, "+8801911000006", "wrong-pass-1")
    assert log_in(client, "+8801911000006").status_code == 200  # count goes back to 0
    for _ in range(9):
        log_in(client, "+8801911000006", "wrong-pass-1")
    assert log_in(client, "+8801911000006").status_code == 200  # still not locked


def test_attack_from_many_devices_locks_the_whole_account(db, monkeypatch, capsys):
    monkeypatch.setattr(settings, "account_lock_after", 5)  # small number to keep the test quick
    make_user(db, "+8801911000007")
    for i in range(5):
        monkeypatch.setattr(auth_routes, "client_ip", lambda request, i=i: f"10.1.0.{i}")
        log_in(TestClient(app), "+8801911000007", "wrong-pass-1")

    monkeypatch.setattr(auth_routes, "client_ip", lambda request: "10.9.9.9")  # even the owner's device
    response = log_in(TestClient(app), "+8801911000007")
    assert response.status_code == 423
    assert response.json()["error"]["code"] == "account_locked"
    assert "[SafeZone SMS]" in capsys.readouterr().out  # the owner was told


def test_too_many_logins_from_one_device_per_minute(db):
    client = TestClient(app)
    for i in range(20):  # 20 different unknown phones, so no single phone gets locked
        assert log_in(client, f"+88019120000{i:02d}", "wrong-pass-1").status_code == 401
    assert log_in(client, "+8801912000099", "wrong-pass-1").status_code == 429


# ------------------------------------------------------------------ staff-only doors
practice = FastAPI()
register_error_handlers(practice)


@practice.get("/staff-only")
def staff_only(user: dict = Depends(require_roles("verifier", "admin"))):
    return {"hello": user["role"]}


def test_only_staff_may_pass_a_staff_door(db):
    make_user(db, "+8801911000008", role="victim")
    make_user(db, "+8801911000009", role="verifier")

    victim = TestClient(app)
    log_in(victim, "+8801911000008")
    verifier = TestClient(app)
    log_in(verifier, "+8801911000009")

    door = lambda client: TestClient(practice, cookies={ACCESS_COOKIE: client.cookies[ACCESS_COOKIE]}).get("/staff-only")
    assert TestClient(practice).get("/staff-only").status_code == 401  # nobody logged in
    assert door(victim).status_code == 403  # logged in, wrong role
    assert door(verifier).json() == {"hello": "verifier"}  # staff may pass


# ------------------------------------------------------------------ "Remember me" (Task 10)
def test_remember_me_off_gives_cookies_that_end_with_the_browser(db):
    make_user(db, "+8801911000010")
    client = TestClient(app)
    response = client.post("/api/v1/auth/login", headers=SAFE,
                           json={"phone": "+8801911000010", "password": PASSWORD, "remember": False})
    assert response.status_code == 200
    cookies = " ".join(response.headers.get_list("set-cookie")).lower()
    assert "max-age" not in cookies and "expires" not in cookies  # session cookies

    # Renewing the tickets keeps them as session cookies
    renewed = client.post("/api/v1/auth/refresh", headers=SAFE)
    assert "max-age" not in " ".join(renewed.headers.get_list("set-cookie")).lower()


def test_remember_me_on_keeps_you_logged_in_for_7_days(db):
    make_user(db, "+8801911000011")
    response = TestClient(app).post("/api/v1/auth/login", headers=SAFE,
                                    json={"phone": "+8801911000011", "password": PASSWORD, "remember": True})
    assert "max-age=604800" in " ".join(response.headers.get_list("set-cookie")).lower()  # 7 days
