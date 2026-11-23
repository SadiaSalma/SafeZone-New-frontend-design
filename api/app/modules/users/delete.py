"""
delete.py (users) - Task 31: "Delete my data" (FR-4, Design Revisions R8).

Two steps, so nobody can delete an account by accident or from a stolen, logged-in laptop:
  1. request:  the person types their PASSWORD -> we send a 6-digit code by SMS (purpose "delete")
  2. confirm:  the person types the CODE -> everything below happens at once (one transaction)

What happens to the data:
  account        name, phone and password are replaced; the NID (hash + last 4) is removed;
                 status "deleted" - the phone number can be used again for a new account
  reports        kept for the statistics, but ANONYMOUS: no owner, no description, no stolen items,
                 no landmark, no answers; the exact place is replaced by a point moved 100-200 m
  waiting ones   reports still waiting for review are WITHDRAWN (they free their GD again)
  photos         deleted from the disk and from the database
  log-ins        all sessions, codes, wrong-password records and push subscriptions are deleted
  kept           alerts that were already sent (they never had personal data), decisions and the
                 audit log (they hold no personal values - R8)
Staff accounts can't delete themselves here: an admin suspends them (Task 30).
"""
from datetime import datetime, timezone

from app import storage
from app.audit import write_audit
from app.db import client, get_db
from app.errors import AppError
from app.modules.auth import repository
from app.modules.auth.service import _check_code, issue_code
from app.modules.review.decisions import move_point
from app.notify import mask_phone, send_notice
from app.security import verify_password

WAITING = ("PENDING_REVIEW", "NEEDS_INFO")


def summary(user: dict) -> dict:
    """What deleting would change - shown on the page before anything happens."""
    db = get_db()
    reports = list(db.reports.find({"user_id": user["_id"]}, {"status": 1}))
    ids = [r["_id"] for r in reports]
    return {
        "reports": len(reports),
        "waiting": sum(r["status"] in WAITING for r in reports),
        "photos": db.report_photos.count_documents({"report_id": {"$in": ids}}),
        "push_subscriptions": db.push_subscriptions.count_documents({"user_id": user["_id"]}),
        "nid_added": bool(user.get("nid_hash")),
        "phone_masked": mask_phone(user["phone"]),
    }


def _victims_only(user: dict) -> None:
    if user["role"] != "victim":
        raise AppError(403, "staff_account", "Staff accounts are removed by an admin.")


def request_delete(user: dict, password: str) -> dict:
    _victims_only(user)
    if not verify_password(password, user["password_hash"]):
        raise AppError(400, "wrong_password", "This password is not right.", {"password": "This password is not right."})
    demo_code = issue_code(user["phone"], "delete")
    return {"message": f"We sent a code by SMS to {mask_phone(user['phone'])}.", "demo_code": demo_code}


def confirm_delete(user: dict, code: str, now: datetime | None = None) -> dict:
    _victims_only(user)
    now = now or datetime.now(timezone.utc)
    db = get_db()
    found = _check_code(user["phone"], code, "delete", now)
    phone = user["phone"]
    uid = user["_id"]

    reports = list(db.reports.find({"user_id": uid}))
    photos = list(db.report_photos.find({"report_id": {"$in": [r["_id"] for r in reports]}}))

    with client.start_session() as session:
        with session.start_transaction():
            repository.mark_code_used(found["_id"], now, session=session)
            for report in reports:
                lng, lat = report["location"]["coordinates"]
                public = report.get("public_location") or {"type": "Point", "coordinates": list(move_point(lng, lat))}
                changes = {"user_id": None, "description": "", "stolen_items": "", "landmark": "",
                           "location": public, "anonymized_at": now}
                if report["status"] in WAITING:
                    changes.update({"status": "WITHDRAWN", "gd_active": False})
                db.reports.update_one({"_id": report["_id"]},
                                      {"$set": changes, "$unset": {"info_answer": "", "claim": ""}}, session=session)
            db.report_photos.delete_many({"_id": {"$in": [p["_id"] for p in photos]}}, session=session)
            db.users.update_one({"_id": uid}, {
                "$set": {"name_en": "Deleted user", "name_bn": "", "phone": f"deleted:{uid}",
                         "password_hash": "deleted", "status": "deleted", "deleted_at": now,
                         "phone_verified_at": None},
                "$unset": {"nid_hash": "", "nid_last4": "", "nid_added_at": ""},
            }, session=session)
            db.sessions.delete_many({"user_id": uid}, session=session)
            db.push_subscriptions.delete_many({"user_id": uid}, session=session)
            write_audit("user.delete", "users", entity_id=uid, actor_id=uid, actor_role="victim",
                        after={"changed": ["name_en", "phone", "password_hash", "nid_hash", "status"],
                               "reports": len(reports), "photos": len(photos)}, session=session)

    # Outside the transaction: files on disk and records keyed by the phone number
    for photo in photos:
        storage.delete(photo["storage_key"])
    from app.modules.ocr.service import delete_for_user
    delete_for_user(uid)  # Task 29: GD photos that were read by OCR
    db.otp_codes.delete_many({"target": phone})
    db.login_attempts.delete_many({"phone": phone})
    send_notice(phone, "Your account and personal data were deleted. Your reports stay only as anonymous statistics.")
    return {"message": "Your data was deleted.", "reports": len(reports), "photos": len(photos)}
