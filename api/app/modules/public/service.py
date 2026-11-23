"""
service.py (public) - Task 25: what EVERYONE may see, without logging in (FR-21).

Privacy rules (Design Revisions R8) - checked by tests/test_public.py:
  - only VERIFIED thefts (verified, alerted, or alert-failed); never pending or rejected ones
  - only the PUBLIC point, moved 100-200 m at approval - never the exact place
  - house burglaries are shown only as a COUNT per thana, never as a dot (a dot could point at a home)
  - the time is rounded to the hour; no story, no landmark, no stolen items, no GD, no names
"""
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from bson.errors import InvalidId
from shapely.geometry import shape

from app.db import get_db
from app.errors import AppError
from app.modules.areas.service import public_area
from app.modules.reports.schemas import THEFT_LABELS

PUBLIC_STATUSES = ["VERIFIED", "ALERTED", "ALERT_FAILED"]
AREA_ONLY = {"burglary"}  # FR-21: shown only at area level


def _hour(when: datetime) -> datetime:
    return when.replace(minute=0, second=0, microsecond=0)


def _areas(ids) -> dict:
    found = get_db().areas.find({"_id": {"$in": [i for i in ids if i]}}, {"geom": 0})
    return {a["_id"]: public_area(a) for a in found}


def incidents(days: int, theft_type: str | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    query: dict = {"status": {"$in": PUBLIC_STATUSES}, "public_location": {"$ne": None},
                   "occurred_at": {"$gte": now - timedelta(days=days)}}
    if theft_type:
        query["theft_type"] = theft_type
    fields = {"theft_type": 1, "occurred_at": 1, "public_location": 1, "thana_id": 1, "ward_id": 1, "is_demo": 1}
    reports = list(get_db().reports.find(query, fields).sort("occurred_at", -1).limit(2000))
    names = _areas({r.get("thana_id") for r in reports} | {r.get("ward_id") for r in reports})

    points, burglaries, by_type = [], {}, {}
    for r in reports:
        by_type[r["theft_type"]] = by_type.get(r["theft_type"], 0) + 1
        if r["theft_type"] in AREA_ONLY:  # count per thana, no dot
            thana = names.get(r.get("thana_id"))
            if thana:
                burglaries.setdefault(thana["code"], {"thana": thana, "count": 0})["count"] += 1
            continue
        lng, lat = r["public_location"]["coordinates"]
        points.append({
            "id": str(r["_id"]),  # an opaque id: it reveals nothing about the victim
            "theft_type": r["theft_type"],
            "theft_name_en": THEFT_LABELS[r["theft_type"]][0],
            "theft_name_bn": THEFT_LABELS[r["theft_type"]][1],
            "lat": lat, "lng": lng,
            "occurred_hour": _hour(r["occurred_at"]),
            "thana": names.get(r.get("thana_id")),
            "ward": names.get(r.get("ward_id")),
            "is_demo": bool(r.get("is_demo")),  # Task 32: demo data is labelled on the website
        })
    # A point inside each thana, to draw its burglary bubble (the middle of the area, not of any home)
    for item in burglaries.values():
        area = get_db().areas.find_one({"code": item["thana"]["code"]}, {"geom": 1})
        middle = shape(area["geom"]).representative_point()
        item["lat"], item["lng"] = round(middle.y, 5), round(middle.x, 5)
    return {"days": days, "total": len(reports), "points": points,
            "area_counts": sorted(burglaries.values(), key=lambda b: -b["count"]),
            "by_type": [{"code": c, "name_en": THEFT_LABELS[c][0], "name_bn": THEFT_LABELS[c][1], "count": n}
                        for c, n in sorted(by_type.items(), key=lambda kv: -kv[1])]}


def _public_alert(alert: dict, report: dict | None, names: dict) -> dict:
    report = report or {}
    point = (report.get("public_location") or {}).get("coordinates")
    theft = report.get("theft_type", "other")
    return {
        "id": str(alert["_id"]),
        "text_en": alert["text_en"],
        "text_bn": alert["text_bn"],
        "theft_type": theft,
        "theft_name_en": THEFT_LABELS[theft][0],
        "theft_name_bn": THEFT_LABELS[theft][1],
        "thana": names.get(report.get("thana_id")),
        "ward": names.get(report.get("ward_id")),
        "sent_at": alert.get("sent_at"),
        "radius_m": alert["radius_m"],
        # burglary: no point at all (area level only); otherwise the MOVED public point, never alert.center
        "point": {"lng": point[0], "lat": point[1]} if point and theft not in AREA_ONLY else None,
        "phones": alert.get("phones", 0),
        "is_demo": bool(alert.get("is_demo")),  # Task 32: demo data is labelled on the website
    }


def latest_alerts(limit: int = 30) -> list[dict]:
    db = get_db()
    alerts = list(db.alerts.find({"status": "sent"}).sort("sent_at", -1).limit(limit))
    reports = {r["_id"]: r for r in db.reports.find({"_id": {"$in": [a["report_id"] for a in alerts]}},
                                                     {"theft_type": 1, "thana_id": 1, "ward_id": 1, "public_location": 1})}
    names = _areas({r.get("thana_id") for r in reports.values()} | {r.get("ward_id") for r in reports.values()})
    return [_public_alert(a, reports.get(a["report_id"]), names) for a in alerts]


def one_alert(alert_id: str) -> dict:
    db = get_db()
    try:
        oid = ObjectId(alert_id)
    except (InvalidId, TypeError):
        raise AppError(404, "alert_not_found", "This alert does not exist.")
    alert = db.alerts.find_one({"_id": oid, "status": "sent"})
    if not alert:
        raise AppError(404, "alert_not_found", "This alert does not exist.")
    report = db.reports.find_one({"_id": alert["report_id"]}, {"theft_type": 1, "thana_id": 1, "ward_id": 1, "public_location": 1})
    names = _areas({(report or {}).get("thana_id"), (report or {}).get("ward_id")})
    return _public_alert(alert, report, names)
