"""
service.py (ocr) - Task 29: GD scans (FR-9, design doc 5.2, Design Revisions R8 + R10).

  1. new_scan()   the victim uploads a photo of the GD copy. It is cleaned like every photo (EXIF/GPS removed),
                  saved, and a gd_scans row is made with status "processing". The reading runs in the
                  background (2 workers at most, R10), so the upload answers at once.
  2. run_scan()   OpenCV + Tesseract read the photo (reader.py), the parser picks the fields (parser.py).
                  Status becomes "done" (with the fields) or "failed" (with a short reason). Over 30 s = failed.
  3. get_scan()   the website asks every second until the status is not "processing" any more.
  4. attach()     when the report is sent, the scan is linked to it and its photo becomes the report's GD copy.
  5. purge()      R8: scans nobody used are deleted after 24 hours; used ones 30 days after the decision.

Only the fields are kept (GD type, number, date, police station, theft type) - never the raw text,
so no name or address read from the GD is stored anywhere (R8).
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from bson.errors import InvalidId

from app import storage
from app.audit import write_audit
from app.config import settings
from app.db import get_db
from app.errors import AppError
from app.modules.ocr import reader
from app.modules.ocr.parser import parse
from app.modules.reports.photos import clean_image
from app.modules.reports.schemas import THEFT_LABELS
from app.ratelimit import check_limit

_pool: ThreadPoolExecutor | None = None
_pool_lock = threading.Lock()

MESSAGES = {
    "unavailable": ("Reading photos is not available right now. Please type the GD details.",
                    "এখন ছবি পড়া যাচ্ছে না। জিডির তথ্যগুলো লিখে দিন।"),
    "timeout": ("Reading the photo took too long. Please type the GD details.",
                "ছবি পড়তে বেশি সময় লাগছে। জিডির তথ্যগুলো লিখে দিন।"),
    "nothing": ("We couldn't read the GD details from this photo. Please type them.",
                "এই ছবি থেকে জিডির তথ্য পড়া যায়নি। তথ্যগুলো লিখে দিন।"),
    "error": ("Something went wrong while reading the photo. Please type the GD details.",
              "ছবি পড়তে সমস্যা হয়েছে। জিডির তথ্যগুলো লিখে দিন।"),
}


def _executor() -> ThreadPoolExecutor:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ThreadPoolExecutor(max_workers=settings.ocr_workers, thread_name_prefix="safezone-ocr")
        return _pool


def _oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise AppError(404, "scan_not_found", "This GD scan does not exist.")


def public_scan(scan: dict) -> dict:
    message = MESSAGES.get(scan.get("error", ""), ("", ""))
    return {
        "id": str(scan["_id"]),
        "status": scan["status"],
        "fields": scan.get("fields", {}),
        "unsure": scan.get("unsure", []),
        "confidence": scan.get("confidence", 0),
        "seconds": scan.get("seconds", 0),
        "message": message[0], "message_bn": message[1],
        "photo_url": f"/api/v1/gd-scans/{scan['_id']}/photo",
    }


# ---------------------------------------------------------------- 1. upload
def new_scan(user: dict, raw: bytes, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    check_limit(f"gd-scan:{user['_id']}", settings.scans_per_hour, 3600)
    jpeg, width, height = clean_image(raw, max_side=settings.scan_max_side)
    key = storage.save(jpeg, "jpg")
    scan = {"user_id": user["_id"], "report_id": None, "status": "processing", "storage_key": key,
            "raw_text": "",  # R8: never kept - only the fields below
            "fields": {}, "unsure": [], "confidence": 0, "seconds": 0, "width": width, "height": height,
            "created_at": now, "delete_after": now + timedelta(hours=settings.scan_keep_hours)}
    scan["_id"] = get_db().gd_scans.insert_one(scan).inserted_id
    write_audit("gd_scan.create", "gd_scans", entity_id=scan["_id"], actor_id=user["_id"], actor_role=user["role"])
    if settings.background_jobs:
        _executor().submit(run_scan, scan["_id"])
    else:  # tests: read it right away, so the answer is already "done"
        run_scan(scan["_id"])
        scan = get_db().gd_scans.find_one({"_id": scan["_id"]})
    return public_scan(scan)


# ---------------------------------------------------------------- 2. reading (in a worker thread)
def run_scan(scan_id: ObjectId) -> None:
    db = get_db()
    scan = db.gd_scans.find_one({"_id": scan_id, "status": "processing"})
    if not scan:
        return
    started = time.perf_counter()
    result: dict = {}
    try:
        reading = reader.read(storage.path_of(scan["storage_key"]).read_bytes())
        formats = [f["regex"] for f in db.gd_formats.find({"is_active": True})]
        stations = list(db.police_stations.find({"is_active": True}, {"code": 1, "name_en": 1, "name_bn": 1}))
        parsed = parse(reading.lines, formats, stations, settings.ocr_min_confidence, reread=reading.reread_digits)
        seconds = round(time.perf_counter() - started, 2)
        if seconds > settings.ocr_timeout_seconds:
            result = {"status": "failed", "error": "timeout"}
        else:
            result = {"status": "done" if parsed["fields"] else "failed", "fields": parsed["fields"],
                      "unsure": parsed["unsure"], "confidence": parsed["confidence"],
                      **({} if parsed["fields"] else {"error": "nothing"})}
    except reader.OcrUnavailable:
        result = {"status": "failed", "error": "unavailable"}
    except RuntimeError as error:  # pytesseract's timeout
        result = {"status": "failed", "error": "timeout" if "timeout" in str(error).lower() else "error"}
    except Exception as error:  # noqa: BLE001 - a broken photo must never break the report form
        print(f"[ocr] {type(error).__name__}: {error}", flush=True)
        result = {"status": "failed", "error": "error"}
    result["seconds"] = round(time.perf_counter() - started, 2)
    db.gd_scans.update_one({"_id": scan_id}, {"$set": result})


# ---------------------------------------------------------------- 3. the result
def _mine(user: dict, scan_id: str) -> dict:
    scan = get_db().gd_scans.find_one({"_id": _oid(scan_id), "user_id": user["_id"]})  # only MY scans
    if not scan:
        raise AppError(404, "scan_not_found", "This GD scan does not exist.")
    return scan


def get_scan(user: dict, scan_id: str) -> dict:
    return public_scan(_mine(user, scan_id))


def photo_file(user: dict, scan_id: str):
    return storage.path_of(_mine(user, scan_id)["storage_key"])


# ---------------------------------------------------------------- 4. part of a report
def check_attachable(user: dict, scan_id: str | None) -> dict | None:
    """Called while the report is checked: the scan must be mine, finished and not used by another report."""
    if not scan_id:
        return None
    scan = _mine(user, scan_id)
    if scan["status"] == "processing":
        raise AppError(409, "scan_not_ready", "We are still reading your GD photo. Wait a moment and send again.")
    if scan.get("report_id"):
        raise AppError(409, "scan_used", "This GD photo is already part of another report.")
    return scan


def attach(scan: dict, report_id: ObjectId, user: dict) -> None:
    """Link the scan to the new report and give the report its GD copy photo (unless it has one)."""
    db = get_db()
    db.gd_scans.update_one({"_id": scan["_id"]}, {"$set": {"report_id": report_id, "delete_after": None}})
    if not db.report_photos.find_one({"report_id": report_id, "kind": "gd_copy"}):
        key = storage.save(storage.path_of(scan["storage_key"]).read_bytes(), "jpg")
        db.report_photos.insert_one({"user_id": user["_id"], "report_id": report_id, "kind": "gd_copy", "storage_key": key,
                                     "size_bytes": storage.path_of(key).stat().st_size, "width": scan.get("width", 0),
                                     "height": scan.get("height", 0), "created_at": datetime.now(timezone.utc)})


def schedule_delete(report_id: ObjectId, decided_at: datetime, session=None) -> None:
    """R8: after a decision, the GD scan is kept 30 more days (for questions), then deleted."""
    get_db().gd_scans.update_many({"report_id": report_id},
                                  {"$set": {"delete_after": decided_at + timedelta(days=settings.scan_keep_days_after_decision)}},
                                  session=session)


def for_review(report: dict) -> dict | None:
    """The verifier's view: what OCR read, next to what the victim typed (only the fields OCR filled - R10)."""
    if not report.get("gd_scan_id"):
        return None
    db = get_db()
    scan = db.gd_scans.find_one({"_id": report["gd_scan_id"]})
    if not scan:
        return {"status": "deleted", "fields": {}, "compare": []}
    return {"status": scan["status"], "confidence": scan.get("confidence", 0), "seconds": scan.get("seconds", 0),
            "fields": scan.get("fields", {}), "compare": compare(report, scan)}


def compare(report: dict, scan: dict) -> list[dict]:
    """Each field OCR filled: what OCR read, what the form says, and whether they agree."""
    db = get_db()
    station = db.police_stations.find_one({"_id": report["gd"].get("police_station_id")}, {"code": 1}) or {}
    gd_date = report["gd"]["date"].astimezone(timezone(timedelta(hours=6))).date().isoformat()
    form = {"gd_type": report["gd"]["type"], "gd_number": report["gd"]["number"], "gd_date": gd_date,
            "police_station": station.get("code"), "theft_type": report["theft_type"]}
    stations = {s["code"]: s for s in db.police_stations.find(
        {"code": {"$in": [form["police_station"], scan.get("fields", {}).get("police_station", {}).get("value")]}},
        {"code": 1, "name_en": 1, "name_bn": 1})}

    def shown(name: str, value) -> dict:
        """A readable version of a value in English and Bangla (names instead of codes)."""
        if name == "police_station" and value in stations:
            return {"en": stations[value]["name_en"], "bn": stations[value].get("name_bn") or stations[value]["name_en"]}
        if name == "theft_type" and value in THEFT_LABELS:
            return {"en": THEFT_LABELS[value][0], "bn": THEFT_LABELS[value][1]}
        return {"en": value, "bn": value}

    rows = []
    for name, field in scan.get("fields", {}).items():
        rows.append({"field": name, "ocr": field["value"], "form": form.get(name), "confidence": field["confidence"],
                     "same": field["value"] == form.get(name),
                     "ocr_text": shown(name, field["value"]), "form_text": shown(name, form.get(name))})
    return rows


# ---------------------------------------------------------------- 5. clean-up (R8)
def purge(now: datetime | None = None) -> int:
    """Delete scans whose time is up (photo + row). Also ends scans stuck in "processing" (e.g. after a restart)."""
    now = now or datetime.now(timezone.utc)
    db = get_db()
    db.gd_scans.update_many({"status": "processing", "created_at": {"$lt": now - timedelta(minutes=5)}},
                            {"$set": {"status": "failed", "error": "timeout"}})
    gone = 0
    for scan in db.gd_scans.find({"delete_after": {"$ne": None, "$lt": now}}, {"storage_key": 1}):
        storage.delete(scan["storage_key"])
        db.gd_scans.delete_one({"_id": scan["_id"]})
        gone += 1
    return gone


def delete_for_user(user_id: ObjectId) -> int:
    """Delete my data (Task 31) / demo clean-up: every scan of this person, files included."""
    db = get_db()
    scans = list(db.gd_scans.find({"user_id": user_id}, {"storage_key": 1}))
    for scan in scans:
        storage.delete(scan["storage_key"])
    db.gd_scans.delete_many({"_id": {"$in": [s["_id"] for s in scans]}})
    return len(scans)
