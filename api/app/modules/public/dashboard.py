"""
dashboard.py (public) - Task 26: the safety dashboard of one thana or ward (FR-22).

For the chosen period (30 or 90 days) and VERIFIED thefts only:
  total            how many thefts
  per_km2          thefts per square kilometre (big and small areas can be compared fairly - R6)
  vs_city          how that compares with the whole city (1.0 = average, 2.0 = twice the average)
  by_type          what is stolen most
  by_hour          24 numbers: thefts in each hour of the day (Dhaka time)
  by_weekday       7 numbers, Saturday first (the Bangladeshi week)
  weekly           thefts per week, oldest first
  hotspots         small squares (about 250 m) with 2 or more thefts
  latest           the latest few thefts (public form)

Hotspots are found with a simple COUNTING GRID: cut the map into squares of about 250 m and count
the thefts in each. No machine learning - easy to explain and to check by hand. The grid uses the
moved PUBLIC points, and house burglaries are left out (they are only shown per area).
"""
import math
from datetime import datetime, timedelta, timezone

from app.db import get_db
from app.errors import AppError
from app.modules.areas.service import public_area
from app.modules.public.service import AREA_ONLY, PUBLIC_STATUSES, _hour
from app.modules.reports.schemas import THEFT_LABELS

DHAKA = timezone(timedelta(hours=6))
CELL_M = 250  # hotspot grid square size
HOTSPOT_MIN = 2  # thefts in one square to call it a hotspot
WEEKDAYS = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu", "Fri"]


def hotspots(points: list[tuple[float, float]], cell_m: int = CELL_M, minimum: int = HOTSPOT_MIN) -> list[dict]:
    """Count (lng, lat) points per grid square; squares with `minimum` or more are hotspots (busiest first)."""
    if not points:
        return []
    mid_lat = sum(lat for _, lat in points) / len(points)
    dlat = cell_m / 111_320
    dlng = cell_m / (111_320 * math.cos(math.radians(mid_lat)))
    cells: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for lng, lat in points:
        cells.setdefault((math.floor(lng / dlng), math.floor(lat / dlat)), []).append((lng, lat))
    found = [{"lat": round(sum(p[1] for p in pts) / len(pts), 5), "lng": round(sum(p[0] for p in pts) / len(pts), 5),
              "count": len(pts), "radius_m": cell_m // 2 + 60}
             for pts in cells.values() if len(pts) >= minimum]
    return sorted(found, key=lambda h: -h["count"])[:8]


def dashboard(code: str, days: int, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    db = get_db()
    area = db.areas.find_one({"code": code, "is_active": True})
    if not area:
        raise AppError(404, "area_not_found", "We don't know this area.")

    since = now - timedelta(days=days)
    in_area = {"thana_id" if area["type"] == "thana" else "ward_id": area["_id"]}
    base = {"status": {"$in": PUBLIC_STATUSES}, "occurred_at": {"$gte": since}}
    reports = list(db.reports.find({**base, **in_area},
                                   {"theft_type": 1, "occurred_at": 1, "public_location": 1, "ward_id": 1, "thana_id": 1})
                   .sort("occurred_at", -1))

    # Thefts per km2 here, and in the whole city (all thanas together)
    size = area.get("size_km2") or 1
    city_total = db.reports.count_documents({**base, "thana_id": {"$ne": None}})
    city_size = sum(a.get("size_km2", 0) for a in db.areas.find({"type": "thana", "is_active": True}, {"size_km2": 1})) or 1
    per_km2 = len(reports) / size
    city_per_km2 = city_total / city_size

    by_type: dict[str, int] = {}
    by_hour = [0] * 24
    by_weekday = [0] * 7
    weeks = math.ceil(days / 7)
    weekly = [0] * weeks
    points = []
    for r in reports:
        by_type[r["theft_type"]] = by_type.get(r["theft_type"], 0) + 1
        local = r["occurred_at"].astimezone(DHAKA)
        by_hour[local.hour] += 1
        by_weekday[(local.weekday() + 2) % 7] += 1  # Python: Monday = 0 -> our Saturday-first week
        week = min(weeks - 1, max(0, weeks - 1 - (now - r["occurred_at"]).days // 7))
        weekly[week] += 1
        if r["theft_type"] not in AREA_ONLY and r.get("public_location"):
            points.append(tuple(r["public_location"]["coordinates"]))

    latest = []
    for r in reports[:5]:
        latest.append({"theft_type": r["theft_type"], "theft_name_en": THEFT_LABELS[r["theft_type"]][0],
                       "theft_name_bn": THEFT_LABELS[r["theft_type"]][1], "occurred_hour": _hour(r["occurred_at"])})

    return {
        "area": {**public_area(area), "geom": area["geom"]},
        "days": days,
        "total": len(reports),
        "per_km2": round(per_km2, 2),
        "city_per_km2": round(city_per_km2, 3),
        "vs_city": round(per_km2 / city_per_km2, 1) if city_per_km2 else None,
        "by_type": [{"code": c, "name_en": THEFT_LABELS[c][0], "name_bn": THEFT_LABELS[c][1], "count": n}
                    for c, n in sorted(by_type.items(), key=lambda kv: -kv[1])],
        "by_hour": by_hour,
        "busiest_hour": by_hour.index(max(by_hour)) if reports else None,
        "by_weekday": [{"day": d, "count": n} for d, n in zip(WEEKDAYS, by_weekday)],
        "weekly": weekly,
        "hotspots": hotspots(points),
        "latest": latest,
    }
