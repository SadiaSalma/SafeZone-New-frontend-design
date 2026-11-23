"""
Tests for Task 6: the database setup (collections, rules and indexes).

They run on the test database (safezone_test) and need the database running.
Each test tries to save something WRONG and checks that MongoDB refuses it.
"""
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from pymongo.errors import DuplicateKeyError, WriteError

from app.db import database_status, get_db
from app.schema import COLLECTIONS
from app.setup_db import apply_schema

pytestmark = pytest.mark.skipif(
    not database_status()["ok"],
    reason="Database not running. Start it: Terminal -> Run Task -> 'SafeZone: start database'",
)

NOW = datetime.now(timezone.utc)


@pytest.fixture(scope="module")
def db():
    """A fresh test database with the full schema applied."""
    database = get_db()
    assert database.name == "safezone_test"  # safety: never the real database
    database.client.drop_database(database.name)
    apply_schema(database)
    yield database
    database.client.drop_database(database.name)


def a_user(**changes):
    """A valid user document; tests change one field to make it wrong."""
    user = {
        "name_en": "Rahim Uddin",
        "phone": "+8801712345678",
        "password_hash": "argon2-hash-here",
        "role": "victim",
        "status": "active",
        "created_at": NOW,
    }
    user.update(changes)
    return user


def a_report(gd_hash="gd-1", gd_active=True):
    return {
        "status": "PENDING_REVIEW",
        "theft_type": "phone_snatching",
        "occurred_at": NOW,
        "submitted_at": NOW,
        "location": {"type": "Point", "coordinates": [90.3667, 23.8069]},  # Mirpur 10 (longitude, latitude)
        "gd": {"type": "GD", "number": "1234", "date": NOW},
        "gd_hash": gd_hash,
        "gd_active": gd_active,
    }


def test_all_collections_exist(db):
    assert set(COLLECTIONS) <= set(db.list_collection_names())


def test_running_setup_again_is_safe(db):
    summary = apply_schema(db)
    assert summary["created"] == []  # nothing new the second time


def test_valid_user_is_accepted(db):
    db.users.insert_one(a_user(phone="+8801700000001"))


def test_unknown_role_is_refused(db):
    with pytest.raises(WriteError):
        db.users.insert_one(a_user(role="boss", phone="+8801700000002"))


def test_wrong_phone_format_is_refused(db):
    with pytest.raises(WriteError):
        db.users.insert_one(a_user(phone="01712345678"))  # missing +880


def test_same_phone_twice_is_refused(db):
    db.users.insert_one(a_user(phone="+8801700000003"))
    with pytest.raises(DuplicateKeyError):
        db.users.insert_one(a_user(phone="+8801700000003"))


def test_an_older_database_loses_its_email_fields(db):
    """Codes used to be emailed. Running the setup again removes the email index and email fields,
    and keeps WHEN the account was confirmed (now phone_verified_at)."""
    confirmed = NOW - timedelta(days=3)
    db.users.create_index("email", unique=True, sparse=True, name="email_unique")
    uid = db.users.insert_one(a_user(phone="+8801700000009", email="old@example.com",
                                     email_verified_at=confirmed)).inserted_id
    apply_schema(db)
    user = db.users.find_one({"_id": uid})
    assert "email" not in user and "email_verified_at" not in user
    assert abs(user["phone_verified_at"].replace(tzinfo=timezone.utc) - confirmed) < timedelta(seconds=1)
    assert "email_unique" not in db.users.index_information()


def test_one_active_report_per_gd(db):
    """Revision R2: the same GD may not be on two ACTIVE reports..."""
    db.reports.insert_one(a_report("gd-x", gd_active=True))
    with pytest.raises(DuplicateKeyError):
        db.reports.insert_one(a_report("gd-x", gd_active=True))


def test_inactive_reports_free_the_gd(db):
    """...but rejected/withdrawn reports (gd_active false) do not block it."""
    db.reports.insert_one(a_report("gd-y", gd_active=False))
    db.reports.insert_one(a_report("gd-y", gd_active=False))
    db.reports.insert_one(a_report("gd-y", gd_active=True))  # the real victim can still report


def test_unknown_report_status_is_refused(db):
    report = a_report("gd-z")
    report["status"] = "SUBMITTED"  # removed by revision R7
    with pytest.raises(WriteError):
        db.reports.insert_one(report)


def test_one_alert_per_report(db):
    """NFR-1 safety net: a report can never get two alerts."""
    alert = {
        "report_id": ObjectId(),
        "text_en": "Phone snatching near Mirpur 10.",
        "text_bn": "মিরপুর ১০-এর কাছে ফোন ছিনতাই।",
        "center": {"type": "Point", "coordinates": [90.3667, 23.8069]},
        "radius_m": 1000,
        "status": "queued",
        "queued_at": NOW,
    }
    db.alerts.insert_one(dict(alert))
    with pytest.raises(DuplicateKeyError):
        db.alerts.insert_one(dict(alert))


def test_map_search_works(db):
    """The 2dsphere index lets us ask 'which reports are within 1 km of this point?'"""
    # ($nearSphere sorts by distance, so it is used with find(), not with count_documents())
    near_mirpur = list(
        db.reports.find(
            {"location": {"$nearSphere": {"$geometry": {"type": "Point", "coordinates": [90.3670, 23.8070]},
                                          "$maxDistance": 1000}}}
        )
    )
    assert len(near_mirpur) >= 1

    # A point in Chattogram (about 200 km away) finds nothing within 1 km
    far_away = list(
        db.reports.find(
            {"location": {"$nearSphere": {"$geometry": {"type": "Point", "coordinates": [91.8317, 22.3569]},
                                          "$maxDistance": 1000}}}
        )
    )
    assert far_away == []


def test_codes_expire_automatically(db):
    """otp_codes has a TTL index: MongoDB deletes codes when expires_at passes."""
    indexes = db.otp_codes.index_information()
    assert indexes["delete_when_expired"]["expireAfterSeconds"] == 0
    db.otp_codes.insert_one({
        "target": "rahim@example.com", "channel": "console", "purpose": "register",
        "code_hash": "x", "attempts": 0, "expires_at": NOW + timedelta(minutes=10),
    })
