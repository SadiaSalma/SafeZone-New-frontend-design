"""
Tests for Task 11: "forgot password" and creating staff accounts.
They use the test database and are skipped if the database is not running.
"""
import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import database_status, get_db
from app.deps import REFRESH_COOKIE
from app.errors import AppError
from app.main import app
from app.modules.users.service import create_staff_user
from app.security import hash_password
from app.setup_db import apply_schema

pytestmark = pytest.mark.skipif(
    not database_status()["ok"],
    reason="Database not running. Start it: Terminal -> Run Task -> 'SafeZone: start database'",
)
SAFE = {"X-SafeZone": "1"}


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


def make_user(db, phone, password="old-pass-123", status="active"):
    db.users.insert_one({
        "name_en": "Reset Tester", "phone": phone, "password_hash": hash_password(password),
        "role": "victim", "status": status, "failed_logins": 0, "locked_until": None,
        "created_at": datetime.now(timezone.utc),
    })


def ask_for_code(client, capsys, phone):
    """Step 1 of forgot password; returns the printed code (or None if none was sent)."""
    capsys.readouterr()
    response = client.post("/api/v1/auth/password-reset/request", json={"phone": phone}, headers=SAFE)
    assert response.status_code == 200
    found = re.search(r"code: (\d{6})", capsys.readouterr().out)
    return found.group(1) if found else None


def log_in(client, phone, password):
    return client.post("/api/v1/auth/login", json={"phone": phone, "password": password}, headers=SAFE)


def test_full_reset_journey(db, capsys):
    make_user(db, "+8801611000001")
    old_device = TestClient(app)
    assert log_in(old_device, "+8801611000001", "old-pass-123").status_code == 200

    client = TestClient(app)
    code = ask_for_code(client, capsys, "+8801611000001")
    assert code is not None

    done = client.post("/api/v1/auth/password-reset/confirm", headers=SAFE,
                       json={"phone": "+8801611000001", "code": code, "new_password": "new-pass-456"})
    assert done.status_code == 200
    assert "[SafeZone SMS]" in capsys.readouterr().out  # the owner is told

    assert log_in(TestClient(app), "+8801611000001", "old-pass-123").status_code == 401  # old password: no
    assert log_in(TestClient(app), "+8801611000001", "new-pass-456").status_code == 200  # new password: yes
    # The device that was logged in BEFORE the reset is logged out everywhere
    assert old_device.post("/api/v1/auth/refresh", headers=SAFE).status_code == 401


def test_same_answer_whether_or_not_the_number_has_an_account(db, capsys):
    make_user(db, "+8801611000002")
    client = TestClient(app)
    real = client.post("/api/v1/auth/password-reset/request", json={"phone": "+8801611000002"}, headers=SAFE)
    fake = client.post("/api/v1/auth/password-reset/request", json={"phone": "01999999999"}, headers=SAFE)
    assert real.status_code == fake.status_code == 200
    assert real.json() == fake.json()


def test_unconfirmed_accounts_get_no_reset_code(db, capsys):
    make_user(db, "+8801611000003", status="pending_verify")
    assert ask_for_code(TestClient(app), capsys, "+8801611000003") is None


def test_wrong_code_and_weak_password_are_refused(db, capsys):
    make_user(db, "+8801611000004")
    client = TestClient(app)
    code = ask_for_code(client, capsys, "+8801611000004")

    wrong = client.post("/api/v1/auth/password-reset/confirm", headers=SAFE,
                        json={"phone": "+8801611000004", "code": "000000" if code != "000000" else "111111",
                              "new_password": "new-pass-456"})
    assert wrong.status_code == 400 and wrong.json()["error"]["code"] == "wrong_code"

    weak = client.post("/api/v1/auth/password-reset/confirm", headers=SAFE,
                       json={"phone": "+8801611000004", "code": code, "new_password": "onlyletters"})
    assert weak.status_code == 422
    assert weak.json()["error"]["fields"]["new_password"] == "Use at least one letter and one number."


def test_a_reset_code_cannot_be_used_twice(db, capsys):
    make_user(db, "+8801611000005")
    client = TestClient(app)
    code = ask_for_code(client, capsys, "+8801611000005")
    body = {"phone": "+8801611000005", "code": code, "new_password": "new-pass-456"}
    assert client.post("/api/v1/auth/password-reset/confirm", json=body, headers=SAFE).status_code == 200
    again = client.post("/api/v1/auth/password-reset/confirm", json=body, headers=SAFE)
    assert again.status_code == 400 and again.json()["error"]["code"] == "code_invalid"


def test_reset_lifts_the_account_lock(db, capsys):
    make_user(db, "+8801611000006")
    db.users.update_one({"phone": "+8801611000006"},
                        {"$set": {"locked_until": datetime(2099, 1, 1, tzinfo=timezone.utc)}})
    client = TestClient(app)
    code = ask_for_code(client, capsys, "+8801611000006")
    client.post("/api/v1/auth/password-reset/confirm", headers=SAFE,
                json={"phone": "+8801611000006", "code": code, "new_password": "new-pass-456"})
    assert log_in(TestClient(app), "+8801611000006", "new-pass-456").status_code == 200


# ------------------------------------------------------------------ create_admin (staff accounts)
def test_create_admin_makes_an_active_admin_who_can_log_in(db):
    user = create_staff_user("Admin One", "01822000001", "admin-pass-1", "admin")
    assert user["role"] == "admin" and user["status"] == "active"
    response = log_in(TestClient(app), "01822000001", "admin-pass-1")
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "admin"


def test_create_verifier(db):
    assert create_staff_user("Verifier One", "01822000002", "verify-pass-1",
                             "verifier")["role"] == "verifier"


def test_create_staff_refuses_bad_details(db):
    with pytest.raises(AppError) as bad:
        create_staff_user("Admin Two", "12345", "short", "admin")
    assert set(bad.value.fields) >= {"phone", "password"}

    with pytest.raises(AppError) as role:
        create_staff_user("Boss", "01822000003", "boss-pass-1", "boss")
    assert role.value.code == "invalid_role"

    create_staff_user("Admin Three", "01822000004", "admin-pass-3")
    with pytest.raises(AppError) as twice:
        create_staff_user("Admin Three", "01822000004", "admin-pass-3")
    assert twice.value.code == "already_registered"


def test_refresh_cookie_name_unchanged():
    assert REFRESH_COOKIE == "sz_refresh"  # the website relies on this name
