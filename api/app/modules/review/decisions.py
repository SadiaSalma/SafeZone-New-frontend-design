"""
decisions.py (review) - Task 19: the verifier decides (FR-15, design doc 5.4, Design Revisions R7).

Three possible decisions, each needing the verifier to HOLD the report (Task 18 claim):

  approve   -> the checks run once more; ANY failed check blocks approval.
               Status VERIFIED, the public pin is moved 100-200 m in a random direction (R8),
               and (Task 20) the alert is created in the SAME transaction from the template or the
               verifier's edited text, which must pass the privacy filter. The alert job sends it (Task 22).
  reject    -> a reason is required. Status REJECTED. The GD is freed (gd_active = false),
               so a real victim is never locked out by a mistake.
  ask_info  -> a question for the victim. Status NEEDS_INFO for up to 7 days; the victim
               answers in "My reports" and the report comes back to the queue.

Every decision is added to the "decisions" collection, which is never changed afterwards
(append-only), plus a line in the audit log. The victim gets a notice about the decision.
"""
import math
import random
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo import ReturnDocument

from app.audit import write_audit
from app.db import client, get_db
from app.errors import AppError
from app.modules.alerts.service import final_texts, new_alert
from app.modules.reports.checks import refresh_checks
from app.modules.reports.schemas import THEFT_LABELS
from app.modules.review.service import REVIEWABLE, _oid
from app.jobs import wake_alert_worker
from app.modules.push.service import notify_user
from app.notify import send_notice

NEEDS_INFO_DAYS = 7
REJECT_REASONS = {
    "gd_not_found": "We could not confirm the GD with the police station.",
    "not_a_theft": "This does not look like a theft.",
    "duplicate": "This theft was already reported.",
    "outside_area": "The place is outside the area SafeZone covers.",
    "not_enough_info": "There is not enough information to confirm it.",
    "other": "Other reason.",
}


def move_point(lng: float, lat: float, rng: random.Random | None = None) -> tuple[float, float]:
    """A point 100-200 m away from (lng, lat) in a random direction - the PUBLIC pin (R8).
    Nobody can find a victim's home or exact spot from the public map."""
    rng = rng or random.SystemRandom()
    metres = rng.uniform(100, 200)
    bearing = rng.uniform(0, 2 * math.pi)
    dlat = (metres * math.cos(bearing)) / 111_320
    dlng = (metres * math.sin(bearing)) / (111_320 * math.cos(math.radians(lat)))
    return round(lng + dlng, 6), round(lat + dlat, 6)


def _held_by(user: dict, now: datetime) -> dict:
    """The filter "this verifier holds the report right now and it is still waiting"."""
    return {"status": REVIEWABLE, "claim.by": user["_id"], "claim.until": {"$gt": now}}


def _why_not(user: dict, oid: ObjectId, now: datetime):
    report = get_db().reports.find_one({"_id": oid}, {"status": 1, "claim": 1})
    if not report:
        raise AppError(404, "report_not_found", "This report does not exist.")
    if report["status"] != REVIEWABLE:
        raise AppError(409, "not_reviewable", "This report is not waiting for review any more.")
    raise AppError(409, "claim_required", "Open the report again to hold it before deciding (your 15 minutes ran out).")


def _record(oid: ObjectId, user: dict, decision: str, reason: str, note: str, session) -> None:
    get_db().decisions.insert_one({"report_id": oid, "verifier_id": user["_id"], "decision": decision, "reason": reason,
                                   "note": note, "created_at": datetime.now(timezone.utc)}, session=session)
    write_audit(f"report.{decision}", "reports", entity_id=oid, actor_id=user["_id"], actor_role=user["role"],
                after={"decision": decision}, session=session)
    if decision in ("approve", "reject"):  # Task 29 / R8: the GD scan is kept 30 more days, then deleted
        from app.modules.ocr.service import schedule_delete
        schedule_delete(oid, datetime.now(timezone.utc), session=session)


def _tell_victim(report: dict, subject: str, body: str) -> None:
    victim = get_db().users.find_one({"_id": report.get("user_id")}, {"phone": 1}) if report.get("user_id") else None
    if victim:
        send_notice(victim["phone"], f"{subject}. {body}")
        notify_user(victim["_id"], subject, body)  # Task 23: and a push, if they allowed notifications


# ---------------------------------------------------------------- approve
def approve(user: dict, report_id: str, note: str = "", now: datetime | None = None,
            text_en: str | None = None, text_bn: str | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    oid = _oid(report_id)
    db = get_db()
    if not db.reports.find_one({"_id": oid, **_held_by(user, now)}, {"_id": 1}):
        _why_not(user, oid, now)

    report = refresh_checks(oid)  # run the checks once more, just before approving (design doc 5.3)
    failed = [c for c in report["checks"] if c["result"] == "fail"]
    if failed:
        raise AppError(409, "check_failed", f"A check failed, so this report can't be approved: {failed[0]['message']}")

    texts = final_texts(report, text_en, text_bn)  # Task 20: template or edited text, privacy-checked
    lng, lat = report["location"]["coordinates"]
    public_lng, public_lat = move_point(lng, lat)
    with client.start_session() as session, session.start_transaction():
        updated = db.reports.find_one_and_update(
            {"_id": oid, **_held_by(user, now)},
            {"$set": {"status": "VERIFIED", "verified_at": now, "decided_by": user["_id"], "alert_text": texts,
                      "public_location": {"type": "Point", "coordinates": [public_lng, public_lat]}},
             "$unset": {"claim": ""}},
            return_document=ReturnDocument.AFTER, session=session)
        if not updated:
            _why_not(user, oid, now)
        _record(oid, user, "approve", "", note, session)
        # NFR-1: the alert is born inside the transaction that made the report VERIFIED,
        # and the unique index on alerts.report_id makes a second alert impossible.
        db.alerts.insert_one(new_alert(updated, texts, now), session=session)

    wake_alert_worker()  # Task 22: send the alert right away
    _tell_victim(updated, "Your SafeZone report was verified",
                 f"Your {THEFT_LABELS[updated['theft_type']][0].lower()} report was verified. People nearby will be warned.")
    return {"status": "VERIFIED"}


# ---------------------------------------------------------------- reject
def reject(user: dict, report_id: str, reason_code: str, reason: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    oid = _oid(report_id)
    db = get_db()
    text = reason.strip() or REJECT_REASONS.get(reason_code, "")
    with client.start_session() as session, session.start_transaction():
        updated = db.reports.find_one_and_update(
            {"_id": oid, **_held_by(user, now)},
            {"$set": {"status": "REJECTED", "gd_active": False, "decided_by": user["_id"], "reject_reason": text},
             "$unset": {"claim": ""}},
            return_document=ReturnDocument.AFTER, session=session)
        if not updated:
            _why_not(user, oid, now)
        _record(oid, user, "reject", f"{reason_code}: {text}", "", session)

    _tell_victim(updated, "Your SafeZone report was not approved", f"Reason: {text} You can send a new report if needed.")
    return {"status": "REJECTED"}


# ---------------------------------------------------------------- ask for more information
def ask_info(user: dict, report_id: str, question: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    oid = _oid(report_id)
    db = get_db()
    with client.start_session() as session, session.start_transaction():
        updated = db.reports.find_one_and_update(
            {"_id": oid, **_held_by(user, now)},
            {"$set": {"status": "NEEDS_INFO", "info_request": question.strip(),
                      "needs_info_until": now + timedelta(days=NEEDS_INFO_DAYS)},
             "$unset": {"claim": "", "info_answer": ""}},
            return_document=ReturnDocument.AFTER, session=session)
        if not updated:
            _why_not(user, oid, now)
        _record(oid, user, "ask_info", question.strip(), "", session)

    _tell_victim(updated, "SafeZone needs a little more information",
                 f"The verifier asks: {question.strip()} Please answer in 'My reports' within {NEEDS_INFO_DAYS} days.")
    return {"status": "NEEDS_INFO"}


# ---------------------------------------------------------------- the report's history (for the review screen)
ACTION_WORDS = {
    "report.create": "Report sent", "report.photo_add": "Photo added", "report.photo_remove": "Photo removed",
    "report.claim": "Opened by a verifier", "report.approve": "Approved", "report.reject": "Rejected",
    "report.ask_info": "More information asked", "report.answer": "Victim answered", "report.withdraw": "Withdrawn",
}


def timeline(report_id: ObjectId) -> list[dict]:
    """The audit lines for one report, oldest first. Names are not shown - only roles."""
    entries = get_db().audit_logs.find({"entity": "reports", "entity_id": report_id}).sort("created_at", 1)
    return [{"action": e["action"], "text": ACTION_WORDS.get(e["action"], e["action"]), "role": e.get("actor_role", ""),
             "created_at": e["created_at"]} for e in entries]
