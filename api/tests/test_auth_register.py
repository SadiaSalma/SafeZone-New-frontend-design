"""
Tests for Task 7: signing up and one-time codes.

Part 1 needs no database (phone format, password and code hashing).
Part 2 uses the test database and is skipped if the database is not running.
"""
import re

import pytest
from fastapi.testclient import TestClient

from app.db import database_status, get_db
from app.main import app
from app.config import settings
from app.modules.auth.schemas import normalize_phone
from app.notify import code_text, mask_phone
from app.security import code_matches, hash_code, hash_password, verify_password
from app.setup_db import apply_schema

SAFE = {"X-SafeZone": "1"}  # the safety header every change needs


# =============================== Part 1: no database needed ===============================
@pytest.mark.parametrize(
    "typed, saved",
    [
        ("01712345678", "+8801712345678"),
        ("+8801712345678", "+8801712345678"),
        ("8801712345678", "+8801712345678"),
        ("017-1234 5678", "+8801712345678"),
        ("01912345678", "+8801912345678"),
    ],
)
def test_phone_numbers_are_saved_in_one_format(typed, saved):
    assert normalize_phone(typed) == saved


@pytest.mark.parametrize("bad", ["12345", "01212345678", "0171234567", "+1 202 555 0100", "abcdefghijk"])
def test_bad_phone_numbers_are_refused(bad):
    with pytest.raises(ValueError):
        normalize_phone(bad)


def test_password_is_never_stored_as_typed():
    hashed = hash_password("safe-pass-123")
    assert hashed != "safe-pass-123"
    assert hashed.startswith("$argon2")
    assert verify_password("safe-pass-123", hashed)
    assert not verify_password("wrong-pass-123", hashed)


def test_code_hash_only_matches_the_same_code_person_and_purpose():
    saved = hash_code("123456", "+8801712345678", "register")
    assert code_matches("123456", "+8801712345678", "register", saved)
    assert not code_matches("654321", "+8801712345678", "register", saved)  # wrong code
    assert not code_matches("123456", "+8801812345678", "register", saved)  # someone else
    assert not code_matches("123456", "+8801712345678", "reset", saved)  # other purpose


def test_phone_numbers_are_masked_on_screen():
    assert mask_phone("+8801712345678") == "017*****678"


def test_the_sms_says_the_code_and_what_it_is_for():
    text = code_text("123456", "reset")
    assert "123456" in text and "reset your SafeZone password" in text
    assert len(text) <= 160  # fits in one SMS


# =============================== Part 2: with the test database ===============================
DATABASE_UP = database_status()["ok"]  # asked once, not before every test
needs_database = pytest.mark.skipif(
    not DATABASE_UP,
    reason="Database not running. Start it: Terminal -> Run Task -> 'SafeZone: start database'",
)
client = TestClient(app)


@pytest.fixture(scope="module")
def db():
    database = get_db()
    assert database.name == "safezone_test"  # safety: never the real database
    database.client.drop_database(database.name)
    apply_schema(database)
    yield database
    database.client.drop_database(database.name)


@pytest.fixture(autouse=True)
def fresh_limits():
    """Spam limits are per hour, so reset them before each test."""
    if DATABASE_UP:
        get_db()["rate_counters"].delete_many({})


def sign_up(**changes):
    body = {
        "name_en": "Rahim Uddin",
        "name_bn": "রহিম উদ্দিন",
        "phone": "01712345678",
        "password": "safe-pass-123",
    }
    body.update(changes)
    return client.post("/api/v1/auth/register", json=body, headers=SAFE)


@needs_database
def test_sign_up_creates_a_waiting_account_and_prints_a_code(db, capsys):
    response = sign_up()
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending_verify"
    assert body["code_sent_to"] == "017*****678"
    assert body["demo_code"] is None  # only shown in demo_screen mode

    user = db.users.find_one({"phone": "+8801712345678"})  # saved in one format
    assert "email" not in user
    assert user["role"] == "victim" and user["status"] == "pending_verify"
    assert user["password_hash"].startswith("$argon2")  # never the real password

    # The SMS was printed in the backend window (console channel) ...
    printed = capsys.readouterr().out
    assert "[SafeZone SMS] to 017*****678" in printed
    code = re.search(r"code: (\d{6})", printed).group(1)
    # ... and only its scrambled version is saved, for this mobile number
    saved = db.otp_codes.find_one({"target": "+8801712345678", "purpose": "register"})
    assert saved["code_hash"] != code and saved["channel"] == "console"
    assert code_matches(code, "+8801712345678", "register", saved["code_hash"])

    # The audit log names the changed fields, but holds no personal values (R8)
    entry = db.audit_logs.find_one({"action": "user.register", "entity_id": user["_id"]})
    assert "Rahim" not in str(entry) and "+8801712345678" not in str(entry)


@needs_database
def test_same_phone_cannot_sign_up_twice(db):
    first = sign_up(phone="01811111111")
    assert first.status_code == 201
    again = sign_up(phone="+880 1811-111111")  # the same number, typed differently
    assert again.status_code == 409
    error = again.json()["error"]
    assert error["code"] == "already_registered"
    assert set(error["fields"]) == {"phone"}


@needs_database
def test_demo_screen_shows_the_code_on_the_website(db, capsys, monkeypatch):
    monkeypatch.setattr(settings, "otp_channel", "demo_screen")
    body = sign_up(phone="01855555555").json()
    assert re.fullmatch(r"\d{6}", body["demo_code"])  # the website shows it in a "Demo SMS" box
    assert f"code: {body['demo_code']}" in capsys.readouterr().out  # and the backend window too
    assert body["channel"] == "demo_screen"


@needs_database
def test_codes_are_never_shown_on_a_real_server(db, monkeypatch):
    monkeypatch.setattr(settings, "otp_channel", "demo_screen")
    monkeypatch.setattr(settings, "app_env", "production")
    response = sign_up(phone="01866666666")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "otp_channel_not_allowed"


@needs_database
def test_real_sms_needs_the_sms_settings(db, monkeypatch):
    monkeypatch.setattr(settings, "otp_channel", "sms")
    monkeypatch.setattr(settings, "sms_api_key", "")
    response = sign_up(phone="01877777777")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "sms_not_configured"


@needs_database
def test_bad_input_names_the_wrong_fields(db):
    response = sign_up(phone="12345", password="short")
    assert response.status_code == 422
    fields = response.json()["error"]["fields"]
    assert fields["phone"] == "Enter a Bangladeshi mobile number like 01712345678."
    assert {"phone", "password"} <= set(fields)


@needs_database
def test_password_needs_a_letter_and_a_number(db):
    response = sign_up(phone="01822222222", password="onlyletters")
    assert response.status_code == 422
    assert response.json()["error"]["fields"]["password"] == "Use at least one letter and one number."


@needs_database
def test_sign_up_needs_the_safety_header(db):
    response = client.post("/api/v1/auth/register", json={"name_en": "X"})  # no X-SafeZone header
    assert response.status_code == 403


@needs_database
def test_at_most_three_codes_per_hour(db):
    assert sign_up(phone="01733333333").status_code == 201  # code 1
    resend = lambda: client.post("/api/v1/auth/resend-otp", json={"phone": "01733333333"}, headers=SAFE)
    assert resend().status_code == 200  # code 2
    assert resend().status_code == 200  # code 3
    fourth = resend()
    assert fourth.status_code == 429
    assert fourth.json()["error"]["code"] == "too_many_requests"
    # Only the newest code is kept; older unused ones were replaced
    assert db.otp_codes.count_documents({"target": "+8801733333333", "used_at": None}) == 1


@needs_database
def test_resend_does_not_reveal_who_has_an_account(db):
    unknown = client.post("/api/v1/auth/resend-otp", json={"phone": "01999999999"}, headers=SAFE)
    assert unknown.status_code == 200
    assert unknown.json()["message"] == "If an account is waiting for a code, we have sent a new one."


@needs_database
def test_too_many_sign_ups_from_one_device(db):
    for i in range(5):
        assert sign_up(phone=f"0164444444{i}").status_code == 201
    sixth = sign_up(phone="01644444449")
    assert sixth.status_code == 429
