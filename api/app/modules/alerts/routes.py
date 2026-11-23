"""
routes.py (alerts) - Task 22: the list of alerts for staff, and "send again" for admins.

  GET  /api/v1/admin/alerts               newest alerts first, with their status and how many phones they reached
  POST /api/v1/admin/alerts/{id}/resend   a FAILED alert goes back in the queue (admin only)
"""
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends

from app.audit import write_audit
from app.db import get_db
from app.deps import require_roles
from app.errors import AppError
from app.jobs import wake_alert_worker
from app.modules.areas.service import public_area
from app.modules.reports.schemas import THEFT_LABELS

router = APIRouter(prefix="/api/v1/admin/alerts", tags=["Alerts (staff)"])
staff = require_roles("verifier", "admin")
admin = require_roles("admin")


def public_alert(alert: dict) -> dict:
    db = get_db()
    report = db.reports.find_one({"_id": alert["report_id"]}, {"theft_type": 1, "thana_id": 1, "ward_id": 1}) or {}
    thana = db.areas.find_one({"_id": report.get("thana_id")}, {"geom": 0}) if report.get("thana_id") else None
    return {
        "id": str(alert["_id"]),
        "report_id": str(alert["report_id"]),
        "theft_name_en": THEFT_LABELS.get(report.get("theft_type", "other"))[0],
        "theft_name_bn": THEFT_LABELS.get(report.get("theft_type", "other"))[1],
        "thana": public_area(thana) if thana else None,
        "text_en": alert["text_en"],
        "text_bn": alert["text_bn"],
        "status": alert["status"],
        "radius_m": alert["radius_m"],
        "center": {"lng": alert["center"]["coordinates"][0], "lat": alert["center"]["coordinates"][1]},
        "towers": alert.get("towers", 0),
        "phones": alert.get("phones", 0),
        "push_sent": alert.get("push_sent", 0),
        "queued_at": alert["queued_at"],
        "sent_at": alert.get("sent_at"),
        "seconds_to_send": alert.get("seconds_to_send"),
        "attempts": alert.get("attempts", 0),
        "last_error": alert.get("last_error", ""),
    }


@router.get("", summary="All alerts, newest first")
def list_alerts(user: dict = Depends(staff)):
    return {"alerts": [public_alert(a) for a in get_db().alerts.find().sort("queued_at", -1).limit(100)]}


@router.post("/{alert_id}/resend", summary="Send a failed alert again (admin)")
def resend_alert(alert_id: str, user: dict = Depends(admin)):
    try:
        oid = ObjectId(alert_id)
    except (InvalidId, TypeError):
        raise AppError(404, "alert_not_found", "This alert does not exist.")
    db = get_db()
    alert = db.alerts.find_one_and_update({"_id": oid, "status": "failed"},
                                          {"$set": {"status": "queued", "attempts": 0, "lease_until": None}})
    if not alert:
        if not db.alerts.find_one({"_id": oid}, {"_id": 1}):
            raise AppError(404, "alert_not_found", "This alert does not exist.")
        raise AppError(409, "not_failed", "Only a failed alert can be sent again.")
    db.reports.update_one({"_id": alert["report_id"], "status": "ALERT_FAILED"}, {"$set": {"status": "VERIFIED"}})
    write_audit("alert.resend", "alerts", entity_id=oid, actor_id=user["_id"], actor_role=user["role"])
    wake_alert_worker()
    return {"status": "queued"}
