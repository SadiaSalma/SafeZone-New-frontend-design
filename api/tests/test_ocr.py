"""
Tests for Task 29: reading a photo of the GD copy (FR-9, Design Revisions R8 + R10).

Part 1 tests the parser on made-up lines of words (no Tesseract needed).
Part 2 uploads real-looking sample GD copies (tests/fixtures/gd, all names made up) and is skipped
when Tesseract is not installed.
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import database_status, get_db
from app.main import app
from app.modules.areas.service import load_area_file
from app.modules.ocr import reader
from app.modules.ocr.parser import parse
from app.modules.ocr.service import purge
from app.modules.reports.service import seed_gd_formats
from app.security import hash_nid, hash_password
from app.setup_db import apply_schema

FIXTURES = Path(__file__).parent / "fixtures" / "gd"
SAFE = {"X-SafeZone": "1"}
FORMATS = [r"^\d{1,6}$", r"^GD-\d{1,6}$"]
STATIONS = [
    {"code": "ramna-model-ps", "name_en": "Ramna Model Police Station", "name_bn": "রমনা মডেল থানা"},
    {"code": "shahbagh-ps", "name_en": "Shahbagh Police Station", "name_bn": "শাহবাগ থানা"},
    {"code": "gulshan-ps", "name_en": "Gulshan Police Station", "name_bn": "গুলশান থানা"},
    {"code": "uttara-east-ps", "name_en": "Uttara East Police Station", "name_bn": "উত্তরা পূর্ব থানা"},
]
TODAY = date(2026, 11, 20)


def lines(*rows: str, conf: float = 95) -> list[list[tuple[str, float]]]:
    """'word word' rows -> Tesseract-like lines; a word ending in '@40' gets confidence 40."""
    out = []
    for row in rows:
        words = []
        for w in row.split():
            text, _, c = w.partition("@")
            words.append((text, float(c) if c else conf))
        out.append(words)
    return out


def read_fields(*rows: str, **kw) -> dict:
    return parse(lines(*rows), FORMATS, STATIONS, today=TODAY, **kw)


# ---------------------------------------------------------------- part 1: the parser
def test_bangla_gd_with_bangla_digits():
    result = read_fields("রমনা মডেল থানা, ঢাকা", "সাধারণ ডায়েরী", "জিডি নং- ৮৫৪ তারিখ- ১৮/১১/২০২৬ খ্রিঃ",
                         "বিষয়: মোবাইল ফোন ছিনতাই প্রসঙ্গে।",
                         "আমি নাসরিন আক্তার, গত ১৮/১১/২০২৬ তারিখ রাতে শাহবাগ মোড় এলাকায় ...")
    f = {k: v["value"] for k, v in result["fields"].items()}
    assert f == {"gd_type": "GD", "gd_number": "854", "gd_date": "2026-11-18",
                 "police_station": "ramna-model-ps",  # the labelled line wins over the PLACE "শাহবাগ" in the text
                 "theft_type": "phone_snatching"}


def test_english_online_gd_and_fir():
    f = read_fields("GD Number 1157", "GD Date 15/11/2026", "Police Station Gulshan Police Station, Dhaka",
                    "Subject Bag snatched near Gulshan 1 circle")["fields"]
    assert (f["gd_number"]["value"], f["gd_date"]["value"], f["police_station"]["value"], f["theft_type"]["value"]) == \
        ("1157", "2026-11-15", "gulshan-ps", "bag_snatching")
    fir = read_fields("মামলা নং- ২৭ তারিখ- ০৯/১১/২০২৬", "বিষয়: মোটরসাইকেল চুরি।")["fields"]
    assert fir["gd_type"]["value"] == "FIR" and fir["gd_number"]["value"] == "27" and fir["theft_type"]["value"] == "motorbike_theft"


def test_unsure_fields_stay_empty():
    # R10: Tesseract was only 40% sure of the number -> left empty for the victim, never guessed
    result = read_fields("জিডি নং- ৮৫৪@40 তারিখ- ১৮/১১/২০২৬")
    assert "gd_number" not in result["fields"] and "gd_number" in result["unsure"]
    assert result["fields"]["gd_date"]["value"] == "2026-11-18"
    # A sure number behind an unsure label is not trusted either (the label might be a misreading)
    assert "gd_number" not in read_fields("GD@45 83 3391")["fields"]


def test_a_number_that_fits_no_gd_format_is_thrown_away():
    assert "gd_number" not in read_fields("GD No: 12345678")["fields"]  # 8 digits: no known format
    assert read_fields("GD No: 12345678")["unsure"] == []  # thrown away, not even "unsure"


def test_impossible_dates_are_ignored():
    assert "gd_date" not in read_fields("তারিখ- ৩১/০২/২০২৬")["fields"]  # 31 February
    assert "gd_date" not in read_fields("Date: 01/01/2030")["fields"]  # in the future
    assert read_fields("Date: 5-11-26")["fields"]["gd_date"]["value"] == "2026-11-05"  # short year


def test_ocr_slips_in_station_names():
    # "থানা" misread as "ধানা", and "Uttara East" split oddly - still found, a little less sure
    f = read_fields("উত্তরা পূর্ব ধানা, ঢাকা")["fields"]
    assert f["police_station"]["value"] == "uttara-east-ps"
    f = read_fields("Police Station: Gu1shan")["fields"]
    assert f["police_station"]["value"] == "gulshan-ps" and f["police_station"]["confidence"] < 95


def test_second_look_at_a_misread_number():
    # The label is there but the number came out as letters -> the reader looks at that spot again
    rows = [[("জিডি", 90, (10, 10, 60, 30)), ("নং-", 90, (80, 10, 40, 30)), ("ves", 95, (130, 10, 60, 30)),
             ("তারিখ-", 90, (300, 10, 70, 30))]]
    asked = []

    def reread(box):
        asked.append(box)
        return "854", 88.0

    f = parse(rows, FORMATS, STATIONS, today=TODAY, reread=reread)["fields"]
    assert f["gd_number"]["value"] == "854" and f["gd_number"].get("second_look")
    x, _, w, _ = asked[0]
    assert x >= 120 and x + w <= 300  # only the spot between "নং-" and "তারিখ"


def test_no_names_are_kept():
    result = read_fields("জিডি নং- ৮৫৪", "আমি নিম্ন স্বাক্ষরকারী নাসরিন আক্তার, পিতা- আব্দুল করিম")
    assert set(result["fields"]) <= {"gd_type", "gd_number", "gd_date", "police_station", "theft_type"}
    assert "নাসরিন" not in str(result)


# ---------------------------------------------------------------- part 2: real photos through the API
needs_db = pytest.mark.skipif(not database_status()["ok"], reason="Database not running")
needs_tesseract = pytest.mark.skipif(not reader.available(), reason="Tesseract is not installed")


@pytest.fixture(scope="module")
def db():
    database = get_db()
    assert database.name == "safezone_test"
    database.client.drop_database(database.name)
    apply_schema(database)
    load_area_file(database)
    seed_gd_formats(database)
    yield database
    database.client.drop_database(database.name)


_n = iter(range(100, 999))


def victim(db, role="victim") -> TestClient:
    n = next(_n)
    phone = f"+8801799800{n:03d}"
    db.users.insert_one({"name_en": "OCR Tester", "phone": phone,
                         "password_hash": hash_password("pass-1234"), "role": role, "status": "active", "failed_logins": 0,
                         "locked_until": None, "created_at": datetime.now(timezone.utc),
                         "nid_hash": hash_nid(f"19901234567{n:06d}"), "nid_last4": f"{n:04d}"})
    browser = TestClient(app)
    assert browser.post("/api/v1/auth/login", json={"phone": phone, "password": "pass-1234"}, headers=SAFE).status_code == 200
    return browser


def upload(browser, name: str):
    with open(FIXTURES / name, "rb") as photo:
        return browser.post("/api/v1/gd-scans", files={"file": (name, photo, "image/jpeg")}, headers=SAFE)


def recent(value: str) -> bool:
    return date.today().year - 2026 <= 2  # the sample GDs are dated Nov 2026; older dates are refused on purpose


@needs_db
@needs_tesseract
def test_upload_and_read_a_bangla_gd(db):
    browser = victim(db)
    answer = upload(browser, "gd_bangla.jpg")
    assert answer.status_code == 202
    scan = answer.json()
    assert scan["status"] == "done"  # tests read right away (no background worker)
    f = {k: v["value"] for k, v in scan["fields"].items()}
    assert f["gd_number"] == "854" and f["police_station"] == "ramna-model-ps" and f["gd_type"] == "GD"
    assert f["theft_type"] == "phone_snatching"
    if recent(f.get("gd_date", "")):
        assert f["gd_date"] == "2026-11-18"
    assert scan["seconds"] < 30
    # The result again, and the photo - only for its owner
    assert browser.get(f"/api/v1/gd-scans/{scan['id']}").json()["fields"] == scan["fields"]
    assert browser.get(scan["photo_url"]).headers["content-type"] == "image/jpeg"
    assert victim(db).get(f"/api/v1/gd-scans/{scan['id']}").status_code == 404
    # R8: the raw text (with the victim's name) is never stored
    stored = db.gd_scans.find_one({"user_id": db.users.find_one({"name_en": "OCR Tester"})["_id"]})
    assert stored["raw_text"] == "" and "নাসরিন" not in str(stored)


@needs_db
@needs_tesseract
def test_a_phone_photo_and_an_english_gd(db):
    browser = victim(db)
    photo = upload(browser, "gd_bangla_photo.jpg").json()  # tilted, shadowed, noisy, smaller
    assert photo["status"] == "done" and photo["fields"]["police_station"]["value"] == "ramna-model-ps"
    english = upload(browser, "gd_online_english.jpg").json()
    assert english["fields"]["gd_number"]["value"] == "1157" and english["fields"]["police_station"]["value"] == "gulshan-ps"


@needs_db
def test_only_victims_and_only_photos(db):
    staff = victim(db, role="verifier")
    assert staff.post("/api/v1/gd-scans", files={"file": ("a.jpg", b"x", "image/jpeg")}, headers=SAFE).status_code == 403
    browser = victim(db)
    bad = browser.post("/api/v1/gd-scans", files={"file": ("gd.txt", b"not a photo", "text/plain")}, headers=SAFE)
    assert bad.status_code == 415
    assert browser.get("/api/v1/gd-scans/nope").status_code == 404


@needs_db
@needs_tesseract
def test_a_scan_becomes_part_of_the_report(db):
    browser = victim(db)
    scan = upload(browser, "gd_bangla.jpg").json()
    now = datetime.now(timezone(timedelta(hours=6)))
    body = {"theft_type": "phone_snatching", "occurred_at": (now - timedelta(hours=3)).isoformat(), "lat": 23.7385, "lng": 90.3960,
            "gd": {"type": "GD", "number": "854", "date": now.date().isoformat(), "police_station": "ramna-model-ps"},
            "gd_scan_id": scan["id"]}
    sent = browser.post("/api/v1/reports", json=body, headers=SAFE)
    assert sent.status_code == 201, sent.text
    report = db.reports.find_one({"_id": __import__("bson").ObjectId(sent.json()["id"])})
    assert str(report["gd_scan_id"]) == scan["id"]
    # The scan's photo became the GD copy -> the "GD copy" check passes
    assert db.report_photos.count_documents({"report_id": report["_id"], "kind": "gd_copy"}) == 1
    checks = {c["code"]: c for c in report["checks"]}
    assert checks["gd_copy"]["result"] == "pass"
    # Number and station agree with the photo; the GD date in the form (today) differs from the photo (18 Nov)
    if recent("") and now.date() != date(2026, 11, 18):
        assert checks["ocr_match"]["result"] == "warning" and checks["ocr_match"]["fields"] == ["gd_date"]
        assert any(r["code"] == "ocr_match" and r["points"] == 15 for r in report["risk"]["reasons"])
    # A scan can be used once, and is no longer deleted after 24 hours
    again = browser.post("/api/v1/reports", json={**body, "gd": {**body["gd"], "number": "855"}}, headers=SAFE)
    assert again.status_code == 409 and again.json()["error"]["code"] == "scan_used"
    assert db.gd_scans.find_one({"_id": report["gd_scan_id"]})["delete_after"] is None


@needs_db
def test_old_unused_scans_are_deleted(db):
    from app import storage
    key = storage.save(b"old photo")
    old = db.gd_scans.insert_one({"user_id": None, "report_id": None, "status": "done", "storage_key": key, "raw_text": "",
                                  "fields": {}, "created_at": datetime.now(timezone.utc) - timedelta(days=2),
                                  "delete_after": datetime.now(timezone.utc) - timedelta(hours=1)}).inserted_id
    stuck = db.gd_scans.insert_one({"user_id": None, "report_id": None, "status": "processing", "storage_key": "x/none.jpg",
                                    "created_at": datetime.now(timezone.utc) - timedelta(hours=1), "delete_after": None}).inserted_id
    assert purge() >= 1
    assert db.gd_scans.find_one({"_id": old}) is None and not (storage.folder() / key).exists()
    assert db.gd_scans.find_one({"_id": stuck})["status"] == "failed"  # a scan stuck after a restart ends as "failed"


@needs_db
def test_warnings_use_the_admins_points(db):
    # Bug fixed with Task 29: the "duplicate" check used 10 points instead of the admin's "nearby_duplicate" (20)
    from app.modules.reports.checks import risk_score
    warn = {"result": "warning", "message": "x", "message_bn": "x"}
    assert risk_score([{"code": "duplicate", **warn}])["score"] == 20
    assert risk_score([{"code": "ocr_match", **warn}])["score"] == 15
