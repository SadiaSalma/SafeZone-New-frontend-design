"""
service.py (admin) - Task 30: the admin panel (FR-25, design doc API "admin").

  stats()            the overview numbers (also for verifiers)
  staff              list / create / suspend or reactivate verifiers and admins
  areas              rename, change the alert radius (FR-17: "set per ward"), switch off
  police stations    name, phone, on/off
  GD formats         the GD number patterns the automatic check accepts (Task 17)
  risk settings      points per warning and the level limits (Task 17, FR-13)
  audit log          every important action, newest first (NFR: an unchangeable record)

Every change made here is written to the audit log too.
"""
import re
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from app.audit import write_audit
from app.db import get_db
from app.errors import AppError
from app.modules.auth.repository import revoke_all_sessions
from app.modules.users.service import create_staff_user
from app.settings_store import get_setting, save_setting

DHAKA = timezone(timedelta(hours=6))


def _oid(value: str, what: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise AppError(404, f"{what}_not_found", f"This {what.replace('_', ' ')} does not exist.")


# ---------------------------------------------------------------- overview
def stats(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    db = get_db()
    by_status = {row["_id"]: row["n"] for row in db.reports.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}])}
    oldest = db.reports.find_one({"status": "PENDING_REVIEW"}, {"submitted_at": 1}, sort=[("submitted_at", 1)])

    # Average review time: from "sent" to the first decision
    review_minutes = []
    for d in db.decisions.aggregate([{"$sort": {"created_at": 1}}, {"$group": {"_id": "$report_id", "first": {"$first": "$created_at"}}}]):
        report = db.reports.find_one({"_id": d["_id"]}, {"submitted_at": 1})
        if report:
            review_minutes.append((d["first"] - report["submitted_at"]).total_seconds() / 60)

    sent = list(db.alerts.find({"status": "sent"}, {"phones": 1, "seconds_to_send": 1}))
    start = (now.astimezone(DHAKA) - timedelta(days=13)).replace(hour=0, minute=0, second=0, microsecond=0)
    per_day = {(start + timedelta(days=i)).date().isoformat(): 0 for i in range(14)}
    for r in db.reports.find({"submitted_at": {"$gte": start.astimezone(timezone.utc)}}, {"submitted_at": 1}):
        day = r["submitted_at"].astimezone(DHAKA).date().isoformat()
        if day in per_day:
            per_day[day] += 1

    users = {row["_id"]: row["n"] for row in db.users.aggregate([{"$match": {"status": {"$ne": "deleted"}}},
                                                                {"$group": {"_id": "$role", "n": {"$sum": 1}}}])}
    return {
        "reports": {"total": sum(by_status.values()), "by_status": by_status},
        "waiting": by_status.get("PENDING_REVIEW", 0),
        "oldest_waiting_minutes": round((now - oldest["submitted_at"]).total_seconds() / 60) if oldest else None,
        "average_review_minutes": round(sum(review_minutes) / len(review_minutes)) if review_minutes else None,
        "alerts_sent": len(sent),
        "phones_reached": sum(a.get("phones", 0) for a in sent),
        "average_send_seconds": round(sum(a.get("seconds_to_send") or 0 for a in sent) / len(sent), 1) if sent else None,
        "failed_alerts": db.alerts.count_documents({"status": "failed"}),
        "users": {"victims": users.get("victim", 0), "verifiers": users.get("verifier", 0), "admins": users.get("admin", 0)},
        "push_followers": db.push_subscriptions.count_documents({}),
        "per_day": [{"day": d, "count": n} for d, n in per_day.items()],
    }


# ---------------------------------------------------------------- staff
def public_staff(u: dict) -> dict:
    return {"id": str(u["_id"]), "name_en": u["name_en"], "phone": u["phone"], "role": u["role"],
            "status": u["status"], "created_at": u.get("created_at")}


def list_staff() -> list[dict]:
    return [public_staff(u) for u in get_db().users.find({"role": {"$in": ["verifier", "admin"]}}).sort("name_en", 1)]


def add_staff(admin: dict, name_en: str, phone: str, password: str, role: str) -> dict:
    user = create_staff_user(name_en, phone, password, role)
    write_audit("staff.add", "users", entity_id=user["_id"], actor_id=admin["_id"], actor_role="admin", after={"role": role})
    return public_staff(user)


def change_staff(admin: dict, user_id: str, status: str | None, role: str | None) -> dict:
    db = get_db()
    oid = _oid(user_id, "user")
    if oid == admin["_id"]:
        raise AppError(409, "not_yourself", "You can't change your own account here.")
    target = db.users.find_one({"_id": oid, "role": {"$in": ["verifier", "admin"]}})
    if not target:
        raise AppError(404, "user_not_found", "This staff member does not exist.")
    changes = {k: v for k, v in (("status", status), ("role", role)) if v}
    updated = db.users.find_one_and_update({"_id": oid}, {"$set": changes}, return_document=ReturnDocument.AFTER)
    if status == "suspended":
        revoke_all_sessions(oid, datetime.now(timezone.utc))  # logged out everywhere at once
    write_audit("staff.change", "users", entity_id=oid, actor_id=admin["_id"], actor_role="admin",
                after={"changed": sorted(changes), **changes})
    return public_staff(updated)


# ---------------------------------------------------------------- areas and police stations
def list_areas(area_type: str) -> list[dict]:
    areas = list(get_db().areas.find({"type": area_type}, {"geom": 0}))
    areas.sort(key=lambda a: (int(re.sub(r"\D", "", a["code"]) or 0) if area_type == "ward" else 0, a["name_en"]))
    return [{"code": a["code"], "name_en": a["name_en"], "name_bn": a.get("name_bn", ""), "type": a["type"],
             "size_km2": a.get("size_km2"), "alert_radius_m": a.get("alert_radius_m"), "is_active": a["is_active"],
             "source": a.get("source", "")} for a in areas]


def change_area(admin: dict, code: str, changes: dict) -> dict:
    db = get_db()
    clean = {k: v for k, v in changes.items() if v is not None}
    updated = db.areas.find_one_and_update({"code": code}, {"$set": clean}, projection={"geom": 0},
                                           return_document=ReturnDocument.AFTER)
    if not updated:
        raise AppError(404, "area_not_found", "We don't know this area.")
    write_audit("area.update", "areas", entity_id=updated["_id"], actor_id=admin["_id"], actor_role="admin", after=clean)
    return {k: updated.get(k) for k in ("code", "name_en", "name_bn", "type", "size_km2", "alert_radius_m", "is_active")}


def list_stations() -> list[dict]:
    return [{"code": s["code"], "name_en": s["name_en"], "name_bn": s.get("name_bn", ""), "phone": s.get("phone", ""),
             "is_active": s["is_active"], "lat": s["location"]["coordinates"][1], "lng": s["location"]["coordinates"][0]}
            for s in get_db().police_stations.find().sort("name_en", 1)]


def change_station(admin: dict, code: str, changes: dict) -> dict:
    clean = {k: v for k, v in changes.items() if v is not None}
    updated = get_db().police_stations.find_one_and_update({"code": code}, {"$set": clean}, return_document=ReturnDocument.AFTER)
    if not updated:
        raise AppError(404, "station_not_found", "This police station does not exist.")
    write_audit("police_station.update", "police_stations", entity_id=updated["_id"], actor_id=admin["_id"],
                actor_role="admin", after=clean)
    return {"code": updated["code"], "name_en": updated["name_en"], "name_bn": updated.get("name_bn", ""),
            "phone": updated.get("phone", ""), "is_active": updated["is_active"]}


# ---------------------------------------------------------------- GD number formats
def _checked_format(pattern: str, example: str) -> None:
    try:
        compiled = re.compile(pattern)
    except re.error as error:
        raise AppError(422, "invalid_input", "This pattern is not valid.", {"regex": f"Not a valid pattern: {error.msg}"})
    if not compiled.fullmatch(example):
        raise AppError(422, "invalid_input", "The example doesn't match the pattern.", {"example": "The example must match the pattern."})


def list_gd_formats() -> list[dict]:
    return [{"id": str(f["_id"]), "regex": f["regex"], "example": f.get("example", ""), "label": f.get("label", ""),
             "is_active": f["is_active"]} for f in get_db().gd_formats.find()]


def add_gd_format(admin: dict, regex: str, example: str, label: str) -> dict:
    _checked_format(regex, example)
    oid = get_db().gd_formats.insert_one({"regex": regex, "example": example, "label": label, "is_active": True}).inserted_id
    write_audit("gd_format.create", "gd_formats", entity_id=oid, actor_id=admin["_id"], actor_role="admin", after={"regex": regex})
    return {"id": str(oid), "regex": regex, "example": example, "label": label, "is_active": True}


def change_gd_format(admin: dict, format_id: str, is_active: bool) -> dict:
    oid = _oid(format_id, "gd_format")
    updated = get_db().gd_formats.find_one_and_update({"_id": oid}, {"$set": {"is_active": is_active}}, return_document=ReturnDocument.AFTER)
    if not updated:
        raise AppError(404, "gd_format_not_found", "This GD format does not exist.")
    write_audit("gd_format.update", "gd_formats", entity_id=oid, actor_id=admin["_id"], actor_role="admin", after={"is_active": is_active})
    return {"id": str(oid), "regex": updated["regex"], "example": updated.get("example", ""), "label": updated.get("label", ""),
            "is_active": updated["is_active"]}


# ---------------------------------------------------------------- risk settings (Task 17)
def risk_settings() -> dict:
    return {"risk_points": get_setting("risk_points"), "risk_levels": get_setting("risk_levels")}


def save_risk_settings(admin: dict, points: dict, levels: dict) -> dict:
    if levels["medium_from"] >= levels["high_from"]:
        raise AppError(422, "invalid_input", "'Medium from' must be lower than 'High from'.", {"medium_from": "Must be lower than 'High from'."})
    save_setting("risk_points", points, admin["_id"])
    save_setting("risk_levels", levels, admin["_id"])
    write_audit("settings.update", "settings", actor_id=admin["_id"], actor_role="admin", after={"changed": ["risk_points", "risk_levels"]})
    return risk_settings()


# ---------------------------------------------------------------- audit log
def audit_log(page: int, action: str | None, entity: str | None) -> dict:
    db = get_db()
    query: dict = {}
    if action:
        query["action"] = {"$regex": f"^{re.escape(action)}"}
    if entity:
        query["entity"] = entity
    per_page = 50
    rows = list(db.audit_logs.find(query).sort("created_at", -1).skip((page - 1) * per_page).limit(per_page))
    staff_names = {u["_id"]: u["name_en"] for u in db.users.find(
        {"_id": {"$in": [r.get("actor_id") for r in rows if r.get("actor_id")]}, "role": {"$in": ["verifier", "admin"]}},
        {"name_en": 1})}
    return {
        "page": page, "total": db.audit_logs.count_documents(query),
        "entries": [{"id": str(r["_id"]), "action": r["action"], "entity": r["entity"],
                     "entity_id": str(r["entity_id"]) if r.get("entity_id") else None, "actor_role": r.get("actor_role", ""),
                     # staff are named; victims never (privacy): only their role is shown
                     "actor_name": staff_names.get(r.get("actor_id"), ""), "after": r.get("after") or {},
                     "created_at": r["created_at"]} for r in rows],
    }
