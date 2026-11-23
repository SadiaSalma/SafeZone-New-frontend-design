"""
network.py (simulator) - Task 21: a pretend mobile network for Dhaka (Design Revisions R10).

A real cell broadcast needs the mobile operators. For a student project we SIMULATE it:

  cell towers  - placed on a honeycomb grid over the city (about every 800 m), each reaching 1 km.
                 In a honeycomb every place is close to a tower, with no big gaps.
  virtual phones - 5,000 points spread evenly over the 41 thanas. Each phone is "connected"
                 to its NEAREST tower, like a real phone.

When an alert is sent (Task 22), every tower whose range touches the alert circle broadcasts it,
and every phone on those towers receives it - just like real cell broadcast.

The same seed always builds the same network, so demos and tests are repeatable.
Admins' TEST phones (Task 24) are never removed when the network is rebuilt.
"""
import math
import random
from datetime import datetime, timezone

from pymongo.database import Database
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep

from app.config import settings
from app.db import get_db
from app.errors import AppError

M_PER_DEG_LAT = 111_320


def _metres_per_deg_lng(lat: float) -> float:
    return M_PER_DEG_LAT * math.cos(math.radians(lat))


def _city(db: Database):
    shapes = [shape(a["geom"]) for a in db.areas.find({"type": "thana", "is_active": True}, {"geom": 1})]
    if not shapes:
        raise AppError(503, "areas_not_loaded", "Load the Dhaka areas first (Run Task -> 'SafeZone: load Dhaka areas').")
    return unary_union(shapes)


def tower_points(city, spacing_m: int, range_m: int) -> list[tuple[float, float]]:
    """Honeycomb grid points (lng, lat) whose range touches the city."""
    west, south, east, north = city.bounds
    mid_lat = (south + north) / 2
    dlat = spacing_m * math.sqrt(3) / 2 / M_PER_DEG_LAT  # rows of a honeycomb are sqrt(3)/2 apart
    dlng = spacing_m / _metres_per_deg_lng(mid_lat)
    reach = prep(city.buffer(range_m / M_PER_DEG_LAT * 0.6))  # keep towers just outside the edge too
    points, row, lat = [], 0, south
    while lat <= north + dlat:
        lng = west + (dlng / 2 if row % 2 else 0)  # every other row is shifted half a step
        while lng <= east + dlng:
            if reach.contains(Point(lng, lat)):
                points.append((round(lng, 6), round(lat, 6)))
            lng += dlng
        lat += dlat
        row += 1
    return points


def phone_points(city, count: int, rng: random.Random) -> list[tuple[float, float]]:
    """`count` random points evenly spread inside the city (try random points in the box, keep those inside)."""
    west, south, east, north = city.bounds
    inside = prep(city)
    points = []
    while len(points) < count:
        lng, lat = rng.uniform(west, east), rng.uniform(south, north)
        if inside.contains(Point(lng, lat)):
            points.append((round(lng, 6), round(lat, 6)))
    return points


def nearest(phone: tuple[float, float], towers: list[tuple[float, float]]) -> int:
    """Index of the nearest tower (flat-Earth distance is exact enough inside one city)."""
    scale = math.cos(math.radians(phone[1]))
    return min(range(len(towers)),
               key=lambda i: ((towers[i][0] - phone[0]) * scale) ** 2 + (towers[i][1] - phone[1]) ** 2)


def build_network(db: Database | None = None, phones: int | None = None, seed: int | None = None) -> dict:
    """(Re)build the towers and the virtual phones. Test phones are kept and re-joined to the new towers."""
    db = db if db is not None else get_db()
    phones = settings.simulator_phones if phones is None else phones
    rng = random.Random(settings.simulator_seed if seed is None else seed)
    city = _city(db)

    towers = tower_points(city, settings.tower_spacing_m, settings.tower_range_m)
    old_phone_ids = [p["_id"] for p in db.virtual_phones.find({"is_test": False}, {"_id": 1})]
    db.virtual_inbox.delete_many({"phone_id": {"$in": old_phone_ids}})
    db.virtual_phones.delete_many({"is_test": False})
    db.cell_towers.delete_many({})

    tower_docs = [{"code": f"T-{i + 1:03d}", "location": {"type": "Point", "coordinates": [lng, lat]},
                   "range_m": settings.tower_range_m} for i, (lng, lat) in enumerate(towers)]
    tower_ids = db.cell_towers.insert_many(tower_docs).inserted_ids

    now = datetime.now(timezone.utc)
    phone_docs = []
    for lng, lat in phone_points(city, phones, rng):
        phone_docs.append({"location": {"type": "Point", "coordinates": [lng, lat]},
                           "tower_id": tower_ids[nearest((lng, lat), towers)], "is_test": False,
                           "owner_id": None, "label": "", "created_at": now})
    for start in range(0, len(phone_docs), 1000):  # in batches, so memory stays small
        db.virtual_phones.insert_many(phone_docs[start:start + 1000])

    for test_phone in db.virtual_phones.find({"is_test": True}):  # re-join test phones to the new towers
        coords = tuple(test_phone["location"]["coordinates"])
        db.virtual_phones.update_one({"_id": test_phone["_id"]}, {"$set": {"tower_id": tower_ids[nearest(coords, towers)]}})

    return {"towers": len(tower_docs), "phones": len(phone_docs)}


# ---------------------------------------------------------------- what the simulator map shows
def network_summary() -> dict:
    db = get_db()
    per_tower = {row["_id"]: row["n"] for row in db.virtual_phones.aggregate([{"$group": {"_id": "$tower_id", "n": {"$sum": 1}}}])}
    towers = [{"id": str(t["_id"]), "code": t["code"], "lng": t["location"]["coordinates"][0],
               "lat": t["location"]["coordinates"][1], "range_m": t["range_m"], "phones": per_tower.get(t["_id"], 0)}
              for t in db.cell_towers.find().sort("code", 1)]
    return {"towers": towers, "phones": db.virtual_phones.count_documents({"is_test": False}),
            "test_phones": db.virtual_phones.count_documents({"is_test": True})}


def phones_in_box(south: float, west: float, north: float, east: float, limit: int = 6000) -> dict:
    """Phones inside the map view (a box), at most `limit` of them (R10: keep the map fast)."""
    box = {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]}
    query = {"location": {"$geoWithin": {"$geometry": box}}}
    found = get_db().virtual_phones.find(query, {"location": 1, "tower_id": 1, "is_test": 1}).limit(limit)
    phones = [{"id": str(p["_id"]), "lng": p["location"]["coordinates"][0], "lat": p["location"]["coordinates"][1],
               "tower_id": str(p["tower_id"]), "is_test": p.get("is_test", False)} for p in found]
    return {"phones": phones, "limited": len(phones) >= limit}
