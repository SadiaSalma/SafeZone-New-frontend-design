"""
service.py (reports) - Task 14: sending a theft report and looking at my reports.

The rules (design doc FR-8, FR-10 + Design Revisions R2, R7):
  1. Only a logged-in person (role "victim") who has added an NID may report.
  2. The theft happened in the last 30 days, and not in the future.
  3. At most 5 reports in 24 hours per person.
  4. The place is inside Dhaka (one of our 41 thanas).
  5. The GD date is not before the theft and not in the future.
  6. A GD can be on only ONE active report. The database itself enforces this
     with a partial unique index on gd_hash where gd_active is true (R2).
     When a report is rejected or withdrawn, gd_active becomes false and the
     GD is free again - so a mistake never locks a real victim out.
  7. A new report starts in PENDING_REVIEW (R7: there is no SUBMITTED status).
"""
import hashlib
from datetime import datetime, time, timedelta, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.audit import write_audit
from app.config import settings
from app.db import client, get_db
from app.errors import AppError
from app.modules.areas.service import find_area_ids, public_area
from app.modules.ocr import service as ocr_service
from app.modules.reports.checks import VICTIM_TIPS, refresh_checks, run_checks
from app.modules.reports.photos import photos_of
from app.modules.reports.schemas import DHAKA, THEFT_LABELS, AnswerIn, GdCheckIn, ReportIn
from app.modules.users.service import has_nid
from app.ratelimit import check_limit
from app.schema import THEFT_TYPES

CAN_WITHDRAW = ("PENDING_REVIEW", "NEEDS_INFO")

# Formats of GD numbers that verifiers recognise (admins can change them in Task 30)
DEFAULT_GD_FORMATS = [
    {"regex": r"^\d{1,6}$", "example": "1234", "label": "Thana GD serial number", "is_active": True},
    {"regex": r"^GD-\d{1,6}$", "example": "GD-1234", "label": "GD number with prefix", "is_active": True},
]


def seed_gd_formats(db: Database | None = None) -> int:
    """Add the default GD number formats if there are none yet. Returns how many were added."""
    db = db if db is not None else get_db()
    if db.gd_formats.count_documents({}):
        return 0
    db.gd_formats.insert_many([dict(f) for f in DEFAULT_GD_FORMATS])
    return len(DEFAULT_GD_FORMATS)


def gd_hash(gd_type: str, number: str, station_code: str, year: int) -> str:
    """The GD's "fingerprint": same type + number + police station + year = same GD (design doc 4.2)."""
    return hashlib.sha256(f"{gd_type}|{number}|{station_code}|{year}".encode()).hexdigest()


# ---------------------------------------------------------------- choices for the form
def options() -> dict:
    db = get_db()
    stations = db.police_stations.find({"is_active": True}, {"code": 1, "name_en": 1, "name_bn": 1}).sort("name_en", 1)
    return {
        "theft_types": [{"code": c, "name_en": THEFT_LABELS[c][0], "name_bn": THEFT_LABELS[c][1]} for c in THEFT_TYPES],
        "gd_types": [{"code": "GD", "name_en": "General Diary (GD)", "name_bn": "সাধারণ ডায়েরি (জিডি)"},
                     {"code": "FIR", "name_en": "First Information Report (FIR)", "name_bn": "এজাহার (এফআইআর)"}],
        "police_stations": [{"code": s["code"], "name_en": s["name_en"], "name_bn": s.get("name_bn", "")} for s in stations],
        "gd_examples": [f["example"] for f in db.gd_formats.find({"is_active": True})],
        "limits": {"max_age_days": settings.report_max_age_days, "per_day": settings.reports_per_day,
                   "landmark": 120, "description": 1000, "stolen_items": 300},
    }


# ---------------------------------------------------------------- sending a report
def create_report(user: dict, data: ReportIn, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    db = get_db()

    if not has_nid(user):
        raise AppError(403, "nid_required", "Add your NID number before your first report.")

    since = now - timedelta(hours=24)
    if db.reports.count_documents({"user_id": user["_id"], "submitted_at": {"$gte": since}}) >= settings.reports_per_day:
        raise AppError(429, "too_many_reports",
                       f"You can send at most {settings.reports_per_day} reports in 24 hours. Please try again later.")

    report = build_report(user, data, now)
    scan = ocr_service.check_attachable(user, data.gd_scan_id)  # Task 29: mine, finished, not used yet
    if scan:
        report["gd_scan_id"] = scan["_id"]
    try:
        with client.start_session() as session, session.start_transaction():
            report["_id"] = db.reports.insert_one(report, session=session).inserted_id
            write_audit("report.create", "reports", entity_id=report["_id"], actor_id=user["_id"],
                        actor_role=user["role"], after={"status": "PENDING_REVIEW"}, session=session)
    except DuplicateKeyError:
        raise AppError(409, "gd_already_reported", "This GD is already on another report. Each GD can be reported once.",
                       {"gd_number": "This GD is already on another report."})
    if scan:
        ocr_service.attach(scan, report["_id"], user)  # its photo becomes the report's GD copy
    refresh_checks(report["_id"])  # Task 17: automatic checks + risk score (for the verifier)
    return report_for_owner(report)


def build_report(user: dict, data: ReportIn, now: datetime) -> dict:
    """Check the form's details and turn them into a report document (not saved yet).
    Raises a 422 with a message per field if something needs fixing."""
    db = get_db()
    problems: dict[str, str] = {}
    if data.occurred_at > now + timedelta(minutes=5):
        problems["occurred_at"] = "The theft time can't be in the future."
    elif data.occurred_at < now - timedelta(days=settings.report_max_age_days):
        problems["occurred_at"] = f"SafeZone takes thefts from the last {settings.report_max_age_days} days only."

    theft_day = data.occurred_at.astimezone(DHAKA).date()
    today = now.astimezone(DHAKA).date()
    if data.gd.date < theft_day:
        problems["gd_date"] = "The GD date can't be before the theft."
    elif data.gd.date > today:
        problems["gd_date"] = "The GD date can't be in the future."

    station = db.police_stations.find_one({"code": data.gd.police_station, "is_active": True})
    if not station:
        problems["gd_police_station"] = "Choose a police station from the list."

    place = find_area_ids(data.lat, data.lng)
    if not place["thana_id"]:
        problems["location"] = "Pick a place inside Dhaka city."

    if problems:
        raise AppError(422, "invalid_input", "Some details need fixing.", problems)

    report = {
        "user_id": user["_id"],
        "status": "PENDING_REVIEW",  # R7
        "theft_type": data.theft_type,
        "occurred_at": data.occurred_at,
        "submitted_at": now,
        "location": {"type": "Point", "coordinates": [data.lng, data.lat]},
        "public_location": None,  # set when a verifier approves (moved 100-200 m)
        "thana_id": place["thana_id"],
        "ward_id": place["ward_id"],
        "landmark": data.landmark,
        "description": data.description,
        "stolen_items": data.stolen_items,
        "gd": {"type": data.gd.type, "number": data.gd.number,
               "date": datetime.combine(data.gd.date, time(0), tzinfo=DHAKA).astimezone(timezone.utc),
               "police_station_id": station["_id"]},
        "gd_hash": gd_hash(data.gd.type, data.gd.number, station["code"], data.gd.date.year),
        "gd_active": True,  # R2: this report now "holds" the GD
        "checks": [],  # filled by the automatic checks (Task 17)
        "risk": {},
        "gd_scan_id": None,
        "is_demo": False,
    }
    return report


def precheck(user: dict, data: ReportIn, has_gd_copy: bool) -> dict:
    """Task 17: before sending, tell the victim what could slow down the review.
    Only "safe" checks are shown (never the risk score or other people's reports)."""
    if not has_nid(user):
        raise AppError(403, "nid_required", "Add your NID number before your first report.")
    report = build_report(user, data, datetime.now(timezone.utc))
    checks = run_checks(report, has_gd_copy=has_gd_copy)
    tips = [{"code": c["code"], "message": c["message"], "message_bn": c["message_bn"]}
            for c in checks if c["code"] in VICTIM_TIPS and c["result"] != "pass"]
    return {"tips": tips}


# ---------------------------------------------------------------- my reports
def _find_mine(user: dict, report_id: str) -> dict:
    try:
        oid = ObjectId(report_id)
    except (InvalidId, TypeError):
        raise AppError(404, "report_not_found", "This report does not exist.")
    report = get_db().reports.find_one({"_id": oid, "user_id": user["_id"]})  # only MY reports
    if not report:
        raise AppError(404, "report_not_found", "This report does not exist.")
    return report


def my_reports(user: dict) -> list[dict]:
    found = get_db().reports.find({"user_id": user["_id"]}).sort("submitted_at", -1).limit(50)
    return [report_for_owner(r) for r in found]


def my_report(user: dict, report_id: str) -> dict:
    return report_for_owner(_find_mine(user, report_id))


def withdraw(user: dict, report_id: str) -> dict:
    """The victim takes back a report that nobody has decided on yet. Frees the GD (R2)."""
    report = _find_mine(user, report_id)
    db = get_db()
    with client.start_session() as session, session.start_transaction():
        changed = db.reports.find_one_and_update(
            {"_id": report["_id"], "status": {"$in": list(CAN_WITHDRAW)}},  # only if still waiting
            {"$set": {"status": "WITHDRAWN", "gd_active": False}, "$unset": {"claim": ""}},
            return_document=True, session=session,
        )
        if not changed:
            raise AppError(409, "cannot_withdraw", "This report has already been decided, so it can't be withdrawn.")
        write_audit("report.withdraw", "reports", entity_id=report["_id"], actor_id=user["_id"],
                    actor_role=user["role"], after={"status": "WITHDRAWN"}, session=session)
    return report_for_owner(changed)


# ---------------------------------------------------------------- what the owner sees
def report_for_owner(report: dict) -> dict:
    """The victim's own view of a report: everything, including the exact place."""
    db = get_db()
    thana = db.areas.find_one({"_id": report.get("thana_id")}, {"geom": 0}) if report.get("thana_id") else None
    ward = db.areas.find_one({"_id": report.get("ward_id")}, {"geom": 0}) if report.get("ward_id") else None
    station = db.police_stations.find_one({"_id": report["gd"].get("police_station_id")})
    lng, lat = report["location"]["coordinates"]
    return {
        "id": str(report["_id"]),
        "status": report["status"],
        "theft_type": report["theft_type"],
        "theft_name_en": THEFT_LABELS[report["theft_type"]][0],
        "theft_name_bn": THEFT_LABELS[report["theft_type"]][1],
        "occurred_at": report["occurred_at"],
        "submitted_at": report["submitted_at"],
        "lat": lat,
        "lng": lng,
        "thana": public_area(thana) if thana else None,
        "ward": public_area(ward) if ward else None,
        "landmark": report.get("landmark", ""),
        "description": report.get("description", ""),
        "stolen_items": report.get("stolen_items", ""),
        "gd": {
            "type": report["gd"]["type"],
            "number": report["gd"]["number"],
            "date": report["gd"]["date"].astimezone(DHAKA).date(),
            "police_station": {"code": station["code"], "name_en": station["name_en"],
                               "name_bn": station.get("name_bn", "")} if station else None,
        },
        "info_request": report.get("info_request"),
        "info_answer": report.get("info_answer"),
        "needs_info_until": report.get("needs_info_until"),
        "reject_reason": report.get("reject_reason"),
        "can_withdraw": report["status"] in CAN_WITHDRAW,
        "photos": photos_of(report["_id"]),  # Task 16
        "alert": _alert_summary(report["_id"]),  # Task 22: how many phones the alert reached
    }


# ---------------------------------------------------------------- Task 15: GD check while typing
def gd_is_free(user: dict, data: GdCheckIn) -> dict:
    """Tell the form early if a GD is already on an active report (the real guard is still the
    unique index when the report is sent). Limited to 30 checks a minute so nobody can scan GDs."""
    check_limit(f"gdcheck:{user['_id']}", 30, 60)
    station = get_db().police_stations.find_one({"code": data.police_station, "is_active": True}, {"code": 1})
    if not station:
        raise AppError(422, "invalid_input", "Choose a police station from the list.",
                       {"gd_police_station": "Choose a police station from the list."})
    taken = get_db().reports.find_one(
        {"gd_hash": gd_hash(data.type, data.number, station["code"], data.date.year), "gd_active": True}, {"_id": 1})
    return {"free": taken is None, "number": data.number}


# ---------------------------------------------------------------- Task 19: answering the verifier
def answer_info(user: dict, report_id: str, data: AnswerIn, now: datetime | None = None) -> dict:
    """The victim answers "more information needed": the report goes back to the review queue (R7)."""
    now = now or datetime.now(timezone.utc)
    report = _find_mine(user, report_id)
    if report["status"] != "NEEDS_INFO":
        raise AppError(409, "not_waiting_for_answer", "This report is not waiting for an answer.")

    changes: dict = {"info_answer": data.answer.strip(), "status": "PENDING_REVIEW"}
    for field in ("landmark", "description", "stolen_items"):
        if getattr(data, field) is not None:
            changes[field] = getattr(data, field).strip()
    if data.gd:
        db = get_db()
        station = db.police_stations.find_one({"code": data.gd.police_station, "is_active": True})
        theft_day = report["occurred_at"].astimezone(DHAKA).date()
        problems = {}
        if not station:
            problems["gd_police_station"] = "Choose a police station from the list."
        if data.gd.date < theft_day:
            problems["gd_date"] = "The GD date can not be before the theft."
        elif data.gd.date > now.astimezone(DHAKA).date():
            problems["gd_date"] = "The GD date can not be in the future."
        if problems:
            raise AppError(422, "invalid_input", "Some details need fixing.", problems)
        changes["gd"] = {"type": data.gd.type, "number": data.gd.number, "police_station_id": station["_id"],
                         "date": datetime.combine(data.gd.date, time(0), tzinfo=DHAKA).astimezone(timezone.utc)}
        changes["gd_hash"] = gd_hash(data.gd.type, data.gd.number, station["code"], data.gd.date.year)

    try:
        updated = get_db().reports.find_one_and_update(
            {"_id": report["_id"], "status": "NEEDS_INFO"},
            {"$set": changes, "$unset": {"needs_info_until": ""}}, return_document=True)
    except DuplicateKeyError:
        raise AppError(409, "gd_already_reported", "This GD is already on another report.",
                       {"gd_number": "This GD is already on another report."})
    if not updated:
        raise AppError(409, "not_waiting_for_answer", "This report is not waiting for an answer.")
    write_audit("report.answer", "reports", entity_id=report["_id"], actor_id=user["_id"], actor_role=user["role"],
                after={"changed": sorted(changes)})
    refresh_checks(report["_id"])  # the answer may change the checks (e.g. a corrected GD)
    return report_for_owner(get_db().reports.find_one({"_id": report["_id"]}))


def _alert_summary(report_id) -> dict | None:
    alert = get_db().alerts.find_one({"report_id": report_id}, {"status": 1, "phones": 1, "sent_at": 1})
    return {"status": alert["status"], "phones": alert.get("phones", 0), "sent_at": alert.get("sent_at")} if alert else None
