"""
service.py (review) - Task 18: the verifier's queue and "claiming" a report (FR-14, design doc 5.4).

The queue lists reports waiting for review, OLDEST FIRST (fair: nobody waits forever).

Claiming: opening a report holds it for that verifier for 15 minutes, so two verifiers
never decide the same report. It is ONE atomic database step (find_one_and_update):
"give me this report only if nobody holds it, the hold has run out, or I already hold it".
Two verifiers clicking at the same moment -> MongoDB lets exactly one of them win.

Privacy (R8): verifiers see the exact place and the GD, but NOT the victim's name or phone -
only safe facts that help judge the report (account age, NID added, earlier reports).
"""
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from app import storage
from app.audit import write_audit
from app.config import settings
from app.db import get_db
from app.errors import AppError
from app.modules.ocr.service import for_review as ocr_for_review
from app.modules.areas.service import public_area
from app.modules.reports.schemas import DHAKA, THEFT_LABELS

REVIEWABLE = "PENDING_REVIEW"


def _oid(value: str, what: str = "report") -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise AppError(404, f"{what}_not_found", f"This {what} does not exist.")


def _claim_view(report: dict, user: dict, now: datetime) -> dict | None:
    """Who holds the report right now (None if nobody, or the hold ran out)."""
    claim = report.get("claim") or {}
    if not claim.get("by") or claim["until"] <= now:
        return None
    holder = get_db().users.find_one({"_id": claim["by"]}, {"name_en": 1})
    return {"mine": claim["by"] == user["_id"], "by_name": holder["name_en"] if holder else "?",
            "until": claim["until"]}


def _area(area_id):
    area = get_db().areas.find_one({"_id": area_id}, {"geom": 0}) if area_id else None
    return public_area(area) if area else None


# ---------------------------------------------------------------- the queue
def queue(user: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    db = get_db()

    def card(r: dict) -> dict:
        return {
            "id": str(r["_id"]),
            "status": r["status"],
            "theft_type": r["theft_type"],
            "theft_name_en": THEFT_LABELS[r["theft_type"]][0],
            "theft_name_bn": THEFT_LABELS[r["theft_type"]][1],
            "thana": _area(r.get("thana_id")),
            "ward": _area(r.get("ward_id")),
            "occurred_at": r["occurred_at"],
            "submitted_at": r["submitted_at"],
            "risk": {"score": r.get("risk", {}).get("score", 0), "level": r.get("risk", {}).get("level", "low")},
            "has_failed_check": any(c["result"] == "fail" for c in r.get("checks", [])),
            "photos": db.report_photos.count_documents({"report_id": r["_id"]}),
            "claim": _claim_view(r, user, now),
        }

    waiting = db.reports.find({"status": REVIEWABLE}).sort("submitted_at", 1).limit(100)  # oldest first
    asked = db.reports.find({"status": "NEEDS_INFO"}).sort("submitted_at", 1).limit(100)
    return {"waiting": [card(r) for r in waiting], "needs_info": [card(r) for r in asked]}


# ---------------------------------------------------------------- claiming
def claim(user: dict, report_id: str, now: datetime | None = None) -> dict:
    """Hold the report for 15 minutes (or renew my hold). Only one verifier can win."""
    now = now or datetime.now(timezone.utc)
    oid = _oid(report_id)
    free_or_mine = {"$or": [{"claim": {"$exists": False}}, {"claim": None}, {"claim.until": {"$lte": now}},
                            {"claim.by": user["_id"]}]}
    new_claim = {"by": user["_id"], "until": now + timedelta(minutes=settings.claim_minutes)}
    before = get_db().reports.find_one_and_update(
        {"_id": oid, "status": REVIEWABLE, **free_or_mine},
        {"$set": {"claim": new_claim}},
        return_document=ReturnDocument.BEFORE,  # we want to know if I already held it
    )
    if before:
        if not _claim_view(before, user, now):  # a NEW hold (not just renewing mine) goes in the history
            write_audit("report.claim", "reports", entity_id=oid, actor_id=user["_id"], actor_role=user["role"])
        return {"claim": _claim_view({**before, "claim": new_claim}, user, now)}

    # Why not? Tell the verifier clearly.
    existing = get_db().reports.find_one({"_id": oid}, {"status": 1, "claim": 1})
    if not existing:
        raise AppError(404, "report_not_found", "This report does not exist.")
    if existing["status"] != REVIEWABLE:
        raise AppError(409, "not_reviewable", "This report is not waiting for review any more.")
    holder = _claim_view(existing, user, now)
    raise AppError(409, "claimed_by_other",
                   f"{holder['by_name'] if holder else 'Another verifier'} is reviewing this report right now. Try again later.")


def release(user: dict, report_id: str) -> dict:
    """Let go of my hold (e.g. the verifier goes back to the queue without deciding)."""
    get_db().reports.update_one({"_id": _oid(report_id), "claim.by": user["_id"]}, {"$unset": {"claim": ""}})
    return {"claim": None}


# ---------------------------------------------------------------- the review screen
def review_photo_url(report_id, photo_id) -> str:
    return f"/api/v1/review/{report_id}/photos/{photo_id}"


def detail(user: dict, report_id: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    db = get_db()
    report = db.reports.find_one({"_id": _oid(report_id)})
    if not report:
        raise AppError(404, "report_not_found", "This report does not exist.")

    station = db.police_stations.find_one({"_id": report["gd"].get("police_station_id")})
    reporter = db.users.find_one({"_id": report.get("user_id")}) if report.get("user_id") else None
    reporter_facts = None
    if reporter:
        mine = {"user_id": reporter["_id"], "_id": {"$ne": report["_id"]}}
        reporter_facts = {  # safe facts only: no name, no phone, no email (R8)
            "account_days": (now - reporter["created_at"]).days,
            "nid_added": bool(reporter.get("nid_hash")),
            "nid_last4": reporter.get("nid_last4"),
            "other_reports": db.reports.count_documents(mine),
            "verified_reports": db.reports.count_documents({**mine, "status": {"$in": ["VERIFIED", "ALERTED", "ALERT_FAILED"]}}),
            "rejected_reports": db.reports.count_documents({**mine, "status": "REJECTED"}),
        }
    lng, lat = report["location"]["coordinates"]
    photos = db.report_photos.find({"report_id": report["_id"]}).sort("created_at", 1)
    decisions = db.decisions.find({"report_id": report["_id"]}).sort("created_at", 1)
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
        "thana": _area(report.get("thana_id")),
        "ward": _area(report.get("ward_id")),
        "landmark": report.get("landmark", ""),
        "description": report.get("description", ""),
        "stolen_items": report.get("stolen_items", ""),
        "gd": {
            "type": report["gd"]["type"],
            "number": report["gd"]["number"],
            "date": report["gd"]["date"].astimezone(DHAKA).date(),
            "police_station": {"code": station["code"], "name_en": station["name_en"], "name_bn": station.get("name_bn", ""),
                               "lat": station["location"]["coordinates"][1], "lng": station["location"]["coordinates"][0]}
            if station else None,
        },
        "checks": report.get("checks", []),
        "risk": report.get("risk", {}),
        "ocr": ocr_for_review(report),  # Task 29: what OCR read from the GD photo, next to the form
        "photos": [{"id": str(p["_id"]), "kind": p.get("kind", "item"), "url": review_photo_url(report["_id"], p["_id"]),
                    "width": p.get("width"), "height": p.get("height")} for p in photos],
        "reporter": reporter_facts,
        "info_request": report.get("info_request"),
        "info_answer": report.get("info_answer"),  # Task 19: the victim's answer
        "decisions": [{"decision": d["decision"], "reason": d.get("reason", ""), "created_at": d["created_at"]}
                      for d in decisions],
        "claim": _claim_view(report, user, now),
    }


def photo_file(report_id: str, photo_id: str):
    photo = get_db().report_photos.find_one({"_id": _oid(photo_id, "photo"), "report_id": _oid(report_id)})
    if not photo:
        raise AppError(404, "photo_not_found", "This photo does not exist.")
    return storage.path_of(photo["storage_key"])
