"""
Tests for the NID number (format check + one account per NID, stored scrambled).

Part 1 needs no database. Part 2 uses the test database.
"""
import re

import pytest
from fastapi.testclient import TestClient

from app.db import database_status, get_db
from app.main import app
from app.modules.users.schemas import clean_nid
from app.security import hash_nid
from app.setup_db import apply_schema

SAFE = {"X-SafeZone": "1"}


# =============================== Part 1: formats ===============================
@pytest.mark.parametrize(
    "typed, saved",
    [
        ("1234567890", "1234567890"),  # 10 digits (smart card)
        ("1234 567 890", "1234567890"),  # spaces are fine
        ("1234567890123", "1234567890123"),  # 13 digits (old)
        ("19901234567890123", "19901234567890123"),  # 17 digits starting with birth year 1990
    ],
)
def test_valid_nid_formats(typed, saved):
    assert clean_nid(typed) == saved


@pytest.mark.parametrize("bad", ["12345", "123456789012", "12345678901234", "abcdefghij", "18001234567890123"])
def test_invalid_nid_formats(bad):
    with pytest.raises(ValueError):
        clean_nid(bad)


def test_nid_scramble_is_stable_and_hides_the_number():
    assert hash_nid("1234567890") == hash_nid("1234567890")  # same NID -> same scramble (finds duplicates)
    assert hash_nid("1234567890") != hash_nid("1234567891")
    assert "1234567890" not in hash_nid("1234567890")


# =============================== Part 2: with the test database ===============================
DATABASE_UP = database_status()["ok"]  # asked once, not before every test
needs_database = pytest.mark.skipif(
    not DATABASE_UP,
    reason="Database not running. Start it: Terminal -> Run Task -> 'SafeZone: start database'",
)


@pytest.fixture(scope="module")
def db():
    database = get_db()
    assert database.name == "safezone_test"
    database.client.drop_database(database.name)
    apply_schema(database)
    yield database
    database.client.drop_database(database.name)


@pytest.fixture(autouse=True)
def fresh_limits():
    if DATABASE_UP:
        get_db()["rate_counters"].delete_many({})


def logged_in_client(capsys, phone):
    """Sign up + confirm the code -> a client that is logged in."""
    client = TestClient(app)
    capsys.readouterr()
    client.post("/api/v1/auth/register", headers=SAFE,
                json={"name_en": "Nila Akter", "phone": phone, "password": "safe-pass-123"})
    code = re.search(r"code: (\d{6})", capsys.readouterr().out).group(1)
    assert client.post("/api/v1/auth/verify-otp", json={"phone": phone, "code": code}, headers=SAFE).status_code == 200
    return client


@needs_database
def test_new_accounts_have_no_nid_yet(db, capsys):
    client = logged_in_client(capsys, "01511110001")
    me = client.get("/api/v1/me").json()
    assert me["nid_added"] is False and me["nid_last4"] is None


@needs_database
def test_add_nid_stores_only_a_scrambled_copy(db, capsys):
    client = logged_in_client(capsys, "01511110002")
    response = client.post("/api/v1/me/nid", json={"nid": "1234 567 890"}, headers=SAFE)
    assert response.status_code == 200
    assert response.json()["nid_added"] is True
    assert response.json()["nid_last4"] == "7890"

    user = db.users.find_one({"phone": "+8801511110002"})
    assert user["nid_hash"] == hash_nid("1234567890")
    assert "1234567890" not in str(user)  # the full number is nowhere in the database


@needs_database
def test_one_nid_one_account(db, capsys):
    first = logged_in_client(capsys, "01511110003")
    second = logged_in_client(capsys, "01511110004")
    assert first.post("/api/v1/me/nid", json={"nid": "5555555555"}, headers=SAFE).status_code == 200
    taken = second.post("/api/v1/me/nid", json={"nid": "5555555555"}, headers=SAFE)
    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "nid_in_use"


@needs_database
def test_nid_cannot_be_changed_by_the_user(db, capsys):
    client = logged_in_client(capsys, "01511110005")
    assert client.post("/api/v1/me/nid", json={"nid": "1111111111"}, headers=SAFE).status_code == 200
    again = client.post("/api/v1/me/nid", json={"nid": "2222222222"}, headers=SAFE)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "nid_already_added"


@needs_database
def test_bad_nid_format_is_explained(db, capsys):
    client = logged_in_client(capsys, "01511110006")
    response = client.post("/api/v1/me/nid", json={"nid": "12345"}, headers=SAFE)
    assert response.status_code == 422
    assert response.json()["error"]["fields"]["nid"] == "Enter your NID number: 10, 13 or 17 digits."


@needs_database
def test_must_be_logged_in_to_add_nid(db):
    response = TestClient(app).post("/api/v1/me/nid", json={"nid": "1234567890"}, headers=SAFE)
    assert response.status_code == 401
