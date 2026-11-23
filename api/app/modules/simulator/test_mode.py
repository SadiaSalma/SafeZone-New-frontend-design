"""
test_mode.py (simulator) - Task 24: looking inside the simulation, and the admin's test phone (FR-19, FR-20).

  alert_view(id)      the alert's circle and which towers broadcast it
  phone_inbox(id)     every message one virtual phone received ("like a phone screen")
  place_test_phone()  an admin puts THEIR test phone anywhere in Dhaka; it joins the nearest tower,
                      exactly like a real phone, and receives every alert that tower broadcasts
  test_phone_report() for each recent alert: "Received" or "Not reached" (and why)
"""
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from app.audit import write_audit
from app.db import get_db
from app.errors import AppError
from app.modules.alerts.sender import towers_for
from app.modules.areas.service import find_area_ids


def _oid(value: str, what: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise AppError(404, f"{what}_not_found", f"This {what} does not exist.")


def alert_view(alert_id: str) -> dict:
    db = get_db()
    alert = db.alerts.find_one({"_id": _oid(alert_id, "alert")})
    if not alert:
        raise AppError(404, "alert_not_found", "This alert does not exist.")
    towers = towers_for(alert)
    lng, lat = alert["center"]["coordinates"]
    return {
        "id": str(alert["_id"]), "status": alert["status"], "text_en": alert["text_en"], "text_bn": alert["text_bn"],
        "center": {"lat": lat, "lng": lng}, "radius_m": alert["radius_m"],
        "tower_ids": [str(t["_id"]) for t in towers], "phones": alert.get("phones", 0), "sent_at": alert.get("sent_at"),
    }


def received_ids(alert_id: str, phone_ids: list[ObjectId]) -> set[ObjectId]:
    """Which of these phones have this alert in their inbox."""
    found = get_db().virtual_inbox.find({"alert_id": _oid(alert_id, "alert"), "phone_id": {"$in": phone_ids}}, {"phone_id": 1})
    return {row["phone_id"] for row in found}


def phone_inbox(phone_id: str) -> dict:
    db = get_db()
    phone = db.virtual_phones.find_one({"_id": _oid(phone_id, "phone")})
    if not phone:
        raise AppError(404, "phone_not_found", "This phone does not exist.")
    tower = db.cell_towers.find_one({"_id": phone["tower_id"]}, {"code": 1})
    messages = []
    for row in db.virtual_inbox.find({"phone_id": phone["_id"]}).sort("received_at", -1).limit(50):
        alert = db.alerts.find_one({"_id": row["alert_id"]}, {"text_en": 1, "text_bn": 1})
        if alert:
            messages.append({"alert_id": str(row["alert_id"]), "text_en": alert["text_en"], "text_bn": alert["text_bn"],
                             "received_at": row["received_at"]})
    lng, lat = phone["location"]["coordinates"]
    return {"id": str(phone["_id"]), "lat": lat, "lng": lng, "is_test": phone.get("is_test", False),
            "label": phone.get("label", ""), "tower": tower["code"] if tower else None, "messages": messages}


# ---------------------------------------------------------------- test mode (admins)
def place_test_phone(user: dict, lat: float, lng: float, label: str) -> dict:
    """One test phone per admin: placing it again just moves it."""
    if not find_area_ids(lat, lng)["thana_id"]:
        raise AppError(422, "invalid_input", "Put the test phone inside Dhaka city.", {"location": "Put the test phone inside Dhaka city."})
    db = get_db()
    point = {"type": "Point", "coordinates": [lng, lat]}
    tower = db.cell_towers.find_one({"location": {"$nearSphere": {"$geometry": point}}})
    if not tower:
        raise AppError(503, "no_network", "Build the phone network first (Run Task -> 'SafeZone: build phone network').")
    db.virtual_phones.update_one(
        {"is_test": True, "owner_id": user["_id"]},
        {"$set": {"location": point, "tower_id": tower["_id"], "label": label or "Test phone", "is_test": True,
                  "owner_id": user["_id"], "created_at": datetime.now(timezone.utc)}},
        upsert=True)
    write_audit("simulator.test_phone", "virtual_phones", actor_id=user["_id"], actor_role=user["role"],
                after={"tower": tower["code"]})
    return test_phone_report(user)


def remove_test_phone(user: dict) -> dict:
    db = get_db()
    phone = db.virtual_phones.find_one({"is_test": True, "owner_id": user["_id"]}, {"_id": 1})
    if phone:
        db.virtual_inbox.delete_many({"phone_id": phone["_id"]})
        db.virtual_phones.delete_one({"_id": phone["_id"]})
    return {"phone": None, "alerts": []}


def test_phone_report(user: dict) -> dict:
    """The admin's test phone, and for each of the last 20 alerts: did it arrive? If not, why not."""
    db = get_db()
    phone = db.virtual_phones.find_one({"is_test": True, "owner_id": user["_id"]})
    if not phone:
        return {"phone": None, "alerts": []}
    tower = db.cell_towers.find_one({"_id": phone["tower_id"]}, {"code": 1})
    got = {row["alert_id"] for row in db.virtual_inbox.find({"phone_id": phone["_id"]}, {"alert_id": 1})}
    alerts = []
    for alert in db.alerts.find({"status": "sent"}).sort("sent_at", -1).limit(20):
        if alert["_id"] in got:
            reason = "received"
        elif (alert.get("sent_at") or alert["queued_at"]).replace(tzinfo=timezone.utc) < phone["created_at"].replace(tzinfo=timezone.utc):
            reason = "before_phone"  # the alert went out before this test phone was placed
        else:
            reason = "tower_outside"  # its tower doesn't touch the alert circle
        alerts.append({"id": str(alert["_id"]), "text_en": alert["text_en"], "text_bn": alert["text_bn"],
                       "sent_at": alert.get("sent_at"), "received": reason == "received", "reason": reason})
    lng, lat = phone["location"]["coordinates"]
    return {"phone": {"id": str(phone["_id"]), "lat": lat, "lng": lng, "label": phone.get("label", ""),
                      "tower": tower["code"] if tower else None}, "alerts": alerts}
