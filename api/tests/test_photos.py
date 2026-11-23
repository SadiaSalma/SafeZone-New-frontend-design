"""
Tests for Task 16: report photos (item photos + GD copy).
Photos are written to a temporary folder, never to the real api/storage.
"""
import io
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from PIL import Image

from app import storage
from app.config import settings
from app.db import database_status, get_db
from app.main import app
from app.modules.areas.service import load_area_file
from app.security import hash_nid, hash_password
from app.setup_db import apply_schema

pytestmark = pytest.mark.skipif(
    not database_status()["ok"],
    reason="Database not running. Start it: Terminal -> Run Task -> 'SafeZone: start database'",
)
SAFE = {"X-SafeZone": "1"}


@pytest.fixture(scope="module", autouse=True)
def db():
    database = get_db()
    assert database.name == "safezone_test"
    database.client.drop_database(database.name)
    apply_schema(database)
    load_area_file(database)
    yield database
    database.client.drop_database(database.name)


@pytest.fixture(autouse=True)
def temporary_storage(tmp_path, monkeypatch, db):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))  # photos go to a throw-away folder
    db.rate_counters.delete_many({})


_numbers = iter(range(100, 999))


def victim_with_report(db):
    """A logged-in victim (TestClient) and the id of their new report."""
    n = next(_numbers)
    phone = f"+8801722000{n:03d}"
    db.users.insert_one({"name_en": "Photo Tester", "phone": phone,
                         "password_hash": hash_password("pass-1234"), "role": "victim", "status": "active",
                         "failed_logins": 0, "locked_until": None, "created_at": datetime.now(timezone.utc),
                         "nid_hash": hash_nid(f"1990765432{n:03d}"), "nid_last4": f"0{n}"})
    browser = TestClient(app)
    browser.post("/api/v1/auth/login", json={"phone": phone, "password": "pass-1234"}, headers=SAFE)
    now = datetime.now(timezone(timedelta(hours=6)))
    report = browser.post("/api/v1/reports", headers=SAFE, json={
        "theft_type": "phone_snatching", "occurred_at": (now - timedelta(hours=1)).isoformat(), "lat": 23.7457,
        "lng": 90.4047, "gd": {"type": "GD", "number": str(n), "date": now.date().isoformat(),
                               "police_station": "ramna-model-ps"}})
    assert report.status_code == 201, report.text
    return browser, report.json()["id"]


def photo_bytes(fmt="JPEG", size=(3000, 2000), with_gps=False) -> bytes:
    image = Image.new("RGB", size, (200, 80, 40))
    out = io.BytesIO()
    if with_gps:
        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"  # camera maker
        exif[0x8825] = {1: "N", 2: (23.0, 45.0, 0.0), 3: "E", 4: (90.0, 24.0, 0.0)}  # GPS position
        image.save(out, fmt, exif=exif)
    else:
        image.save(out, fmt)
    return out.getvalue()


def upload(browser, report_id, data: bytes, kind="item", name="photo.jpg"):
    return browser.post(f"/api/v1/me/reports/{report_id}/photos", headers=SAFE,
                        data={"kind": kind}, files={"file": (name, data, "image/jpeg")})


def test_upload_removes_gps_and_shrinks(db):
    browser, report_id = victim_with_report(db)
    original = photo_bytes(with_gps=True)
    assert Image.open(io.BytesIO(original)).getexif()  # the original really has hidden data

    answer = upload(browser, report_id, original)
    assert answer.status_code == 201, answer.text
    photo = answer.json()
    assert photo["kind"] == "item" and max(photo["width"], photo["height"]) == settings.photo_max_side

    stored = storage.path_of(db.report_photos.find_one()["storage_key"]).read_bytes()
    assert not Image.open(io.BytesIO(stored)).getexif()  # no EXIF, no GPS
    # The owner can see it, and the report lists it
    seen = browser.get(photo["url"])
    assert seen.status_code == 200 and seen.headers["content-type"] == "image/jpeg"
    assert browser.get(f"/api/v1/me/reports/{report_id}").json()["photos"][0]["id"] == photo["id"]


def test_png_and_webp_are_accepted(db):
    browser, report_id = victim_with_report(db)
    assert upload(browser, report_id, photo_bytes("PNG", (400, 300)), name="a.png").status_code == 201
    assert upload(browser, report_id, photo_bytes("WEBP", (400, 300)), name="b.webp").status_code == 201


def test_a_fake_image_is_refused(db):
    browser, report_id = victim_with_report(db)
    answer = upload(browser, report_id, b"MZ this is a program, not a photo", name="virus.jpg")
    assert answer.status_code == 415 and answer.json()["error"]["code"] == "not_a_photo"
    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, "GIF")
    assert upload(browser, report_id, gif.getvalue(), name="a.gif").status_code == 415


def test_too_big_is_refused(db, monkeypatch):
    browser, report_id = victim_with_report(db)
    monkeypatch.setattr(settings, "photo_max_mb", 1)
    answer = upload(browser, report_id, b"\xff" * (1024 * 1024 + 10))
    assert answer.status_code == 413 and answer.json()["error"]["code"] == "photo_too_big"


def test_three_items_and_one_gd_copy(db):
    browser, report_id = victim_with_report(db)
    small = photo_bytes(size=(200, 200))
    for _ in range(3):
        assert upload(browser, report_id, small).status_code == 201
    fourth = upload(browser, report_id, small)
    assert fourth.status_code == 409 and fourth.json()["error"]["code"] == "too_many_photos"
    assert upload(browser, report_id, small, kind="gd_copy").status_code == 201
    assert upload(browser, report_id, small, kind="gd_copy").status_code == 409


def test_other_people_cannot_see_or_add(db):
    owner, report_id = victim_with_report(db)
    stranger, _ = victim_with_report(db)
    photo = upload(owner, report_id, photo_bytes(size=(200, 200))).json()
    assert stranger.get(photo["url"]).status_code == 404
    assert upload(stranger, report_id, photo_bytes(size=(200, 200))).status_code == 404
    assert TestClient(app).get(photo["url"]).status_code == 401  # not logged in


def test_closed_reports_take_no_photos(db):
    browser, report_id = victim_with_report(db)
    browser.post(f"/api/v1/me/reports/{report_id}/withdraw", headers=SAFE)
    answer = upload(browser, report_id, photo_bytes(size=(200, 200)))
    assert answer.status_code == 409 and answer.json()["error"]["code"] == "report_closed"


def test_remove_a_photo(db):
    browser, report_id = victim_with_report(db)
    photo = upload(browser, report_id, photo_bytes(size=(200, 200))).json()
    key = db.report_photos.find_one({"_id": ObjectId(photo["id"])})["storage_key"]
    assert browser.delete(photo["url"], headers=SAFE).status_code == 204
    assert browser.get(photo["url"]).status_code == 404
    with pytest.raises(Exception):
        storage.path_of(key)  # the file is gone from the disk too


def test_storage_refuses_climbing_out():
    with pytest.raises(Exception):
        storage.path_of("../../.env")
