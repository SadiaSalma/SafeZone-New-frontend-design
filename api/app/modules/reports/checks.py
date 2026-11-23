"""
checks.py (reports) - Task 17: the automatic checks and the risk score (FR-12, FR-13, design doc 5.3).

Every check answers "pass", "warning" or "fail" with a plain message (English + Bangla):

  gd_format          the GD number matches a known format (gd_formats collection)
  gd_timing          the GD was filed within N days of the theft (setting: gd_max_days_after_theft)
  place_in_gd_thana  the theft place is inside the thana of the GD's police station (else: how far outside)
  duplicate          FAIL if the same GD is on another active report;
                     WARNING if another report is within 300 m and 2 hours
  history            the reporter's rejected reports in the last 90 days
  gd_copy            a photo of the GD copy was added
  ocr_match          Task 29: what OCR read from the GD photo agrees with the form
                     (only the fields OCR actually filled are compared - Design Revisions R10)

The risk score adds the admin's points for each warning (settings_store "risk_points"),
is capped at 100, and gets a level: low / medium / high. A failed check makes the score 100.
The score is ADVICE for the verifier - a person always makes the decision. Any failed check
blocks approval (Task 19).

Checks run when a report is sent, whenever its photos change, and again just before approval.
"""
import math
import re
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo.database import Database
from shapely.geometry import Point, shape
from shapely.ops import nearest_points

from app.config import settings
from app.db import get_db
from app.settings_store import get_setting

DHAKA = timezone(timedelta(hours=6))
NEARBY_METRES = 300
NEARBY_HOURS = 2
HISTORY_DAYS = 90
CLOSED = ["WITHDRAWN", "REJECTED"]


def km_between(a: Point, b: Point) -> float:
    """Distance in km between two (lng, lat) points (haversine: good on a round Earth)."""
    lng1, lat1, lng2, lat2 = map(math.radians, (a.x, a.y, b.x, b.y))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _check(code: str, result: str, en: str, bn: str, **data) -> dict:
    return {"code": code, "result": result, "message": en, "message_bn": bn, **data}


# ---------------------------------------------------------------- the six checks
def check_gd_format(report: dict, db: Database) -> dict:
    number = report["gd"]["number"]
    formats = list(db.gd_formats.find({"is_active": True}))
    if any(re.fullmatch(f["regex"], number) for f in formats):
        return _check("gd_format", "pass", "The GD number looks like a real GD number.",
                      "জিডি নম্বরটি আসল জিডি নম্বরের মতো।")
    example = formats[0]["example"] if formats else "1234"
    return _check("gd_format", "warning", f"The GD number '{number}' doesn't match a known format (e.g. {example}).",
                  f"জিডি নম্বর '{number}' পরিচিত কোনো ধরনের সাথে মেলে না (যেমন {example})।")


def check_gd_timing(report: dict, db: Database) -> dict:
    theft_day = report["occurred_at"].astimezone(DHAKA).date()
    gd_day = report["gd"]["date"].astimezone(DHAKA).date()
    days = (gd_day - theft_day).days
    limit = settings.gd_max_days_after_theft
    if days <= limit:
        return _check("gd_timing", "pass", f"The GD was filed {days} day(s) after the theft.",
                      f"চুরির {days} দিন পর জিডি করা হয়েছে।", days=days)
    return _check("gd_timing", "warning", f"The GD was filed {days} days after the theft (more than {limit}).",
                  f"চুরির {days} দিন পর জিডি করা হয়েছে ({limit} দিনের বেশি)।", days=days)


def check_place_in_gd_thana(report: dict, db: Database) -> dict:
    station = db.police_stations.find_one({"_id": report["gd"].get("police_station_id")})
    thana = db.areas.find_one({"_id": station.get("thana_id")}) if station and station.get("thana_id") else None
    if not thana:
        return _check("place_in_gd_thana", "warning", "Couldn't check: the GD's police station isn't linked to a thana.",
                      "যাচাই করা যায়নি: জিডির থানাটি কোনো এলাকার সাথে যুক্ত নয়।")
    lng, lat = report["location"]["coordinates"]
    spot, area = Point(lng, lat), shape(thana["geom"])
    if area.contains(spot):
        return _check("place_in_gd_thana", "pass", f"The place is inside {thana['name_en']} thana, where the GD was filed.",
                      f"জায়গাটি {thana.get('name_bn') or thana['name_en']} থানার ভেতরে, যেখানে জিডি করা হয়েছে।")
    km = round(km_between(spot, nearest_points(area, spot)[0]), 1)
    return _check("place_in_gd_thana", "warning", f"The place is {km} km outside {thana['name_en']} thana, where the GD was filed.",
                  f"জায়গাটি জিডির থানা {thana.get('name_bn') or thana['name_en']} থেকে {km} কিমি বাইরে।", km=km)


def check_duplicate(report: dict, db: Database) -> dict:
    others = {"_id": {"$ne": report.get("_id")}, "status": {"$nin": CLOSED}}
    if db.reports.find_one({**others, "gd_hash": report["gd_hash"], "gd_active": True}, {"_id": 1}):
        return _check("duplicate", "fail", "The same GD is on another active report.",
                      "একই জিডি দিয়ে আরেকটি সক্রিয় রিপোর্ট আছে।")
    window = timedelta(hours=NEARBY_HOURS)
    nearby = list(db.reports.find({
        **others,
        "location": {"$nearSphere": {"$geometry": report["location"], "$maxDistance": NEARBY_METRES}},
        "occurred_at": {"$gte": report["occurred_at"] - window, "$lte": report["occurred_at"] + window},
    }, {"_id": 1}).limit(10))  # count_documents can't be used with $nearSphere, so we find() instead
    if nearby:
        return _check("duplicate", "warning",
                      f"{len(nearby)} other report(s) within {NEARBY_METRES} m and {NEARBY_HOURS} hours. It may be the same theft.",
                      f"{NEARBY_METRES} মিটার ও {NEARBY_HOURS} ঘণ্টার মধ্যে আরও {len(nearby)}টি রিপোর্ট আছে। একই ঘটনা হতে পারে।",
                      report_ids=[str(r["_id"]) for r in nearby])
    return _check("duplicate", "pass", "No duplicate GD and no very similar report nearby.",
                  "একই জিডি বা কাছাকাছি একই রকম রিপোর্ট নেই।")


def check_history(report: dict, db: Database, now: datetime) -> dict:
    if not report.get("user_id"):
        return _check("history", "pass", "No reporter history (data deleted).", "রিপোর্টকারীর কোনো ইতিহাস নেই।", count=0)
    count = db.reports.count_documents({"user_id": report["user_id"], "status": "REJECTED", "_id": {"$ne": report.get("_id")},
                                        "submitted_at": {"$gte": now - timedelta(days=HISTORY_DAYS)}})
    if count == 0:
        return _check("history", "pass", f"No rejected reports in the last {HISTORY_DAYS} days.",
                      f"গত {HISTORY_DAYS} দিনে কোনো রিপোর্ট বাতিল হয়নি।", count=0)
    return _check("history", "warning", f"{count} rejected report(s) in the last {HISTORY_DAYS} days.",
                  f"গত {HISTORY_DAYS} দিনে {count}টি রিপোর্ট বাতিল হয়েছে।", count=count)


OCR_FIELD_NAMES = {"gd_type": ("GD/FIR", "জিডি/মামলা"), "gd_number": ("GD number", "জিডি নম্বর"),
                   "gd_date": ("GD date", "জিডির তারিখ"), "police_station": ("police station", "থানা"),
                   "theft_type": ("theft type", "চুরির ধরন")}


def check_ocr_match(report: dict, db: Database) -> dict:
    scan = db.gd_scans.find_one({"_id": report["gd_scan_id"]}) if report.get("gd_scan_id") else None
    if not scan or scan.get("status") != "done" or not scan.get("fields"):
        return _check("ocr_match", "pass", "No GD photo was read, nothing to compare.", "জিডির ছবি পড়া হয়নি, তুলনা করার কিছু নেই।")
    from app.modules.ocr.service import compare  # here, to avoid a loop between the two modules
    different = [row["field"] for row in compare(report, scan) if not row["same"] and row["field"] != "theft_type"]
    if not different:
        return _check("ocr_match", "pass", "The GD photo agrees with the form.", "জিডির ছবি ফর্মের সাথে মিলে যায়।")
    en = ", ".join(OCR_FIELD_NAMES[f][0] for f in different)
    bn = ", ".join(OCR_FIELD_NAMES[f][1] for f in different)
    return _check("ocr_match", "warning", f"The GD photo shows a different {en} than the form.",
                  f"জিডির ছবিতে ফর্মের চেয়ে আলাদা {bn} দেখা যাচ্ছে।", fields=different)


def check_gd_copy(report: dict, db: Database, has_gd_copy: bool | None = None) -> dict:
    if has_gd_copy is None:
        has_gd_copy = bool(report.get("_id")) and db.report_photos.count_documents(
            {"report_id": report["_id"], "kind": "gd_copy"}) > 0
    if has_gd_copy:
        return _check("gd_copy", "pass", "A photo of the GD copy was added.", "জিডির কপির ছবি দেওয়া হয়েছে।")
    return _check("gd_copy", "warning", "No photo of the GD copy.", "জিডির কপির ছবি নেই।")


# ---------------------------------------------------------------- all checks + the score
def run_checks(report: dict, db: Database | None = None, now: datetime | None = None,
               has_gd_copy: bool | None = None) -> list[dict]:
    db = db if db is not None else get_db()
    now = now or datetime.now(timezone.utc)
    return [
        check_gd_format(report, db),
        check_gd_timing(report, db),
        check_place_in_gd_thana(report, db),
        check_duplicate(report, db),
        check_history(report, db, now),
        check_gd_copy(report, db, has_gd_copy),
        check_ocr_match(report, db),
    ]


POINT_KEY = {"duplicate": "nearby_duplicate", "ocr_match": "ocr_mismatch"}  # the check's code -> its name in the admin's risk settings


def risk_score(checks: list[dict]) -> dict:
    points_for = get_setting("risk_points")
    levels = get_setting("risk_levels")
    reasons = []
    for c in checks:
        if c["result"] == "fail":
            reasons.append({"code": c["code"], "text": c["message"], "text_bn": c["message_bn"], "points": 100})
        elif c["result"] == "warning":
            key = POINT_KEY.get(c["code"], c["code"])
            points = points_for.get(key, 10) * (min(c.get("count", 1), 2) if c["code"] == "history" else 1)
            reasons.append({"code": c["code"], "text": c["message"], "text_bn": c["message_bn"], "points": points})
    score = min(100, sum(r["points"] for r in reasons))
    level = "high" if score >= levels["high_from"] else "medium" if score >= levels["medium_from"] else "low"
    return {"score": score, "level": level, "reasons": reasons, "checked_at": datetime.now(timezone.utc)}


def refresh_checks(report_id: ObjectId) -> dict | None:
    """Run all checks for a saved report and store the result on it. Returns the updated report."""
    db = get_db()
    report = db.reports.find_one({"_id": report_id})
    if not report:
        return None
    checks = run_checks(report, db)
    risk = risk_score(checks)
    db.reports.update_one({"_id": report_id}, {"$set": {"checks": checks, "risk": risk}})
    report.update(checks=checks, risk=risk)
    return report


VICTIM_TIPS = ("gd_format", "gd_timing", "place_in_gd_thana", "gd_copy")  # safe to show the victim before sending
