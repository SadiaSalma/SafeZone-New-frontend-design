"""
Tests for Task 8: confirming the code, logging in, and "who am I?" (/me).

They use the test database and are skipped if the database is not running.
Each test makes its own TestClient, so log-in cookies never leak between tests.
"""
import re

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import database_status, get_db
from app.deps import ACCESS_COOKIE, REFRESH_COOKIE
from app.main import app
from app.security import create_access_token, hash_token
from app.setup_db import apply_schema

pytestmark = pytest.mark.skipif(
    not database_status()["ok"],
    reason="Database not running. Start it: Terminal -> Run Task -> 'SafeZone: start database'",
)
SAFE = {"X-SafeZone": "1"}


@pytest.fixture(scope="module")
def db():
    database = get_db()
    assert database.name == "safezone_test"  # safety: never the real database
    database.client.drop_database(database.name)
    apply_schema(database)
    yield database
    database.client.drop_database(database.name)


@pytest.fixture(autouse=True)
def fresh_limits(db):
    db["rate_counters"].delete_many({})


def sign_up(client, capsys, phone, password="safe-pass-123"):
    """Sign up and return the 6-digit code that was printed in the backend window."""
    capsys.readouterr()  # forget older output
    body = {"name_en": "Karim Ahmed", "phone": phone, "password": password}
    assert client.post("/api/v1/auth/register", json=body, headers=SAFE).status_code == 201
    return re.search(r"code: (\d{6})", capsys.readouterr().out).group(1)


def confirm(client, phone, code):
    return client.post("/api/v1/auth/verify-otp", json={"phone": phone, "code": code}, headers=SAFE)


def wrong(code: str) -> str:
    """A code that is surely different from `code`."""
    return "000000" if code != "000000" else "111111"


def test_full_journey_sign_up_confirm_then_who_am_i(db, capsys):
    client = TestClient(app)
    code = sign_up(client, capsys, "01711110001")

    # Not logged in yet
    assert client.get("/api/v1/me").status_code == 401

    # A wrong code first
    bad = confirm(client, "01711110001", wrong(code))
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "wrong_code"
    assert "4 tries left" in bad.json()["error"]["message"]

    # The right code: account confirmed and logged in
    good = confirm(client, "01711110001", code)
    assert good.status_code == 200
    assert good.json()["user"]["status"] == "active"
    assert ACCESS_COOKIE in client.cookies and REFRESH_COOKIE in client.cookies

    me = client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["phone"] == "+8801711110001"
    assert "email" not in me.json()  # accounts have no email: codes go to the phone
    assert "password_hash" not in me.json()  # the hash never leaves the backend


def test_log_in_with_phone_and_password(db, capsys):
    setup = TestClient(app)
    code = sign_up(setup, capsys, "01711110002")
    confirm(setup, "01711110002", code)

    client = TestClient(app)  # a fresh browser
    response = client.post("/api/v1/auth/login", json={"phone": "+880 1711-110002", "password": "safe-pass-123"},
                           headers=SAFE)
    assert response.status_code == 200
    assert response.json()["user"]["phone"] == "+8801711110002"
    assert client.get("/api/v1/me").status_code == 200


def test_wrong_password_and_unknown_phone_look_the_same(db, capsys):
    setup = TestClient(app)
    confirm(setup, "01711110003", sign_up(setup, capsys, "01711110003"))

    client = TestClient(app)
    wrong_password = client.post("/api/v1/auth/login", json={"phone": "01711110003", "password": "nope-123"},
                                 headers=SAFE)
    unknown_phone = client.post("/api/v1/auth/login", json={"phone": "01799990000", "password": "nope-123"},
                                headers=SAFE)
    assert wrong_password.status_code == unknown_phone.status_code == 401
    assert wrong_password.json() == unknown_phone.json()  # identical answers (R9)


def test_unconfirmed_account_cannot_log_in(db, capsys):
    client = TestClient(app)
    sign_up(client, capsys, "01711110004")
    response = client.post("/api/v1/auth/login", json={"phone": "01711110004", "password": "safe-pass-123"},
                           headers=SAFE)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_not_verified"


def test_five_wrong_tries_end_the_code(db, capsys):
    client = TestClient(app)
    code = sign_up(client, capsys, "01711110005")
    for _ in range(5):
        confirm(client, "01711110005", wrong(code))
    # Even the right code no longer works: a new one is needed
    late = confirm(client, "01711110005", code)
    assert late.status_code == 400
    assert late.json()["error"]["code"] == "code_invalid"


def test_confirming_twice_is_refused(db, capsys):
    client = TestClient(app)
    code = sign_up(client, capsys, "01711110006")
    assert confirm(client, "01711110006", code).status_code == 200
    again = confirm(client, "01711110006", code)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "already_verified"


def test_cookies_are_safe_and_only_a_hash_is_saved(db, capsys):
    client = TestClient(app)
    response = confirm(client, "01711110007", sign_up(client, capsys, "01711110007"))
    set_cookie = " ".join(response.headers.get_list("set-cookie")).lower()
    assert "httponly" in set_cookie  # JavaScript cannot read the tickets
    assert "samesite=lax" in set_cookie

    refresh = client.cookies[REFRESH_COOKIE]
    saved = db.sessions.find_one({"token_hash": hash_token(refresh)})
    assert saved is not None  # the session exists ...
    assert db.sessions.find_one({"token_hash": refresh}) is None  # ... but not the ticket itself


def test_fake_or_expired_tickets_are_refused(db, capsys, monkeypatch):
    client = TestClient(app)
    confirm(client, "01711110008", sign_up(client, capsys, "01711110008"))
    user = db.users.find_one({"phone": "+8801711110008"})

    tampered = TestClient(app, cookies={ACCESS_COOKIE: client.cookies[ACCESS_COOKIE] + "x"})
    assert tampered.get("/api/v1/me").status_code == 401

    monkeypatch.setattr(settings, "access_minutes", -1)  # make a ticket that is already expired
    expired = TestClient(app, cookies={ACCESS_COOKIE: create_access_token(str(user["_id"]), "victim")})
    assert expired.get("/api/v1/me").status_code == 401


def test_suspended_user_is_logged_out_at_once(db, capsys):
    client = TestClient(app)
    confirm(client, "01711110009", sign_up(client, capsys, "01711110009"))
    assert client.get("/api/v1/me").status_code == 200
    db.users.update_one({"phone": "+8801711110009"}, {"$set": {"status": "suspended"}})
    assert client.get("/api/v1/me").status_code == 401
