"""
service.py (areas) - Task 12: Dhaka's thanas, wards and police stations.

Two independent map layers (Design Revisions R3):
  - thanas (police areas, e.g. "Mirpur")
  - wards  (city corporation areas, e.g. "Ward 6")
A ward can overlap more than one thana, so we never assume "ward -> one thana".

The most important function is lookup(lat, lng): "which thana and ward is this
point in, and which police station is nearest?". The report form (Task 14/15)
uses it to fill in the area automatically.
"""
import json
import re
from pathlib import Path

from pymongo import UpdateOne
from shapely import set_precision
from shapely.geometry import mapping, shape
from shapely.ops import unary_union
from pymongo.database import Database

from app.config import settings
from app.db import get_db
from app.errors import AppError

API_FOLDER = Path(__file__).resolve().parents[3]  # .../api
AREA_TYPES = ("thana", "ward")


# ---------------------------------------------------------------- loading the data file
def load_area_file(db: Database | None = None, path: str | None = None) -> dict:
    """Put the thanas, wards and police stations from the data file into the database.

    Safe to run again: existing places (same code) are updated, not duplicated.
    Fields an admin can change (Task 30: names, alert radius, on/off, phone) are only set
    the first time, so loading the file again never undoes an admin's change.
    """
    db = db if db is not None else get_db()
    file = Path(path or API_FOLDER / settings.area_data_file)
    features = json.loads(file.read_text(encoding="utf-8"))["features"]
    areas = [f for f in features if f["properties"]["kind"] == "area"]
    stations = [f for f in features if f["properties"]["kind"] == "police_station"]

    # 1) thanas first, so wards can point at them
    def area_doc(f: dict) -> dict:
        p = f["properties"]
        return {"code": p["code"], "type": p["type"], "geom": f["geometry"], "size_km2": p["size_km2"],
                "source": p["source"], "source_date": p["source_date"]}

    def admin_fields(f: dict) -> dict:
        p = f["properties"]
        return {"name_en": p["name_en"], "name_bn": p["name_bn"], "alert_radius_m": settings.default_alert_radius_m,
                "is_active": True}

    thanas = [f for f in areas if f["properties"]["type"] == "thana"]
    if thanas:
        db.areas.bulk_write([UpdateOne({"code": f["properties"]["code"]}, {"$set": area_doc(f), "$setOnInsert": admin_fields(f)}, upsert=True)
                             for f in thanas])
    thana_ids = {a["code"]: a["_id"] for a in db.areas.find({"type": "thana"}, {"code": 1})}

    wards = [f for f in areas if f["properties"]["type"] == "ward"]
    if wards:
        db.areas.bulk_write([
            UpdateOne({"code": f["properties"]["code"]},
                      {"$set": {**area_doc(f), "thana_ids": [thana_ids[c] for c in f["properties"]["thana_codes"]
                                                              if c in thana_ids]},
                       "$setOnInsert": admin_fields(f)},
                      upsert=True)
            for f in wards])

    # 2) police stations, each linked to the thana it stands in
    ops = []
    for f in stations:
        p = f["properties"]
        thana = db.areas.find_one({"type": "thana", "geom": {"$geoIntersects": {"$geometry": f["geometry"]}}}, {"_id": 1})
        ops.append(UpdateOne({"code": p["code"]}, {"$set": {
            "code": p["code"], "location": f["geometry"], "thana_id": thana["_id"] if thana else None,
        }, "$setOnInsert": {"name_en": p["name_en"], "name_bn": p["name_bn"], "phone": p.get("phone", ""),
                            "address": "", "is_active": True}}, upsert=True))
    if ops:
        db.police_stations.bulk_write(ops)

    forget_city_outline()
    return {"thanas": len(thanas), "wards": len(wards), "police_stations": len(stations)}


# ---------------------------------------------------------------- answers for the website
def public_area(area: dict, with_shape: bool = False) -> dict:
    out = {"code": area["code"], "name_en": area["name_en"], "name_bn": area.get("name_bn", ""),
           "type": area["type"], "size_km2": area.get("size_km2")}
    if with_shape:
        out["geom"] = area["geom"]
    return out


def public_station(station: dict, distance_m: float | None = None) -> dict:
    lng, lat = station["location"]["coordinates"]
    out = {"code": station["code"], "name_en": station["name_en"], "name_bn": station.get("name_bn", ""),
           "phone": station.get("phone", ""), "lat": lat, "lng": lng}
    if distance_m is not None:
        out["distance_m"] = round(distance_m)
    return out


def list_areas(area_type: str | None = None, search: str | None = None) -> list[dict]:
    query: dict = {"is_active": True}
    if area_type:
        query["type"] = area_type
    if search:
        # Simple "contains" search on the English or Bangla name (special characters made safe)
        pattern = re.escape(search.strip())
        query["$or"] = [{"name_en": {"$regex": pattern, "$options": "i"}}, {"name_bn": {"$regex": pattern}}]
    found = get_db().areas.find(query, {"geom": 0}).sort([("type", 1), ("name_en", 1)])
    areas = [public_area(a) for a in found]
    if area_type == "ward" or (area_type is None and search is None):
        areas.sort(key=lambda a: (a["type"], int(a["code"][5:]) if a["type"] == "ward" else 0, a["name_en"]))
    return areas


def area_shapes(area_type: str) -> dict:
    """All shapes of one layer as GeoJSON, for drawing the map."""
    features = [{"type": "Feature", "geometry": a["geom"], "properties": public_area(a)}
                for a in get_db().areas.find({"type": area_type, "is_active": True})]
    return {"type": "FeatureCollection", "features": features}


def get_area(code: str) -> dict:
    db = get_db()
    area = db.areas.find_one({"code": code, "is_active": True})
    if not area:
        raise AppError(404, "area_not_found", "We don't know this area.")
    out = public_area(area, with_shape=True)
    if area["type"] == "thana":
        out["wards"] = [public_area(w) for w in db.areas.find({"type": "ward", "thana_ids": area["_id"]}, {"geom": 0})]
        out["wards"].sort(key=lambda w: int(w["code"][5:]))
        out["police_stations"] = [public_station(s) for s in db.police_stations.find({"thana_id": area["_id"]})]
    else:
        out["thanas"] = [public_area(t) for t in db.areas.find({"_id": {"$in": area.get("thana_ids", [])}}, {"geom": 0})]
    return out


def nearest_stations(lat: float, lng: float, limit: int = 3) -> list[dict]:
    found = get_db().police_stations.aggregate([
        {"$geoNear": {"near": {"type": "Point", "coordinates": [lng, lat]}, "distanceField": "distance_m",
                      "spherical": True, "query": {"is_active": True}}},
        {"$limit": limit},
    ])
    return [public_station(s, s["distance_m"]) for s in found]


def find_area_ids(lat: float, lng: float) -> dict:
    """For the report task: the database ids of the thana and ward at this point (or None)."""
    point = {"type": "Point", "coordinates": [lng, lat]}
    ids = {"thana_id": None, "ward_id": None}
    for area in get_db().areas.find({"is_active": True, "geom": {"$geoIntersects": {"$geometry": point}}},
                                    {"type": 1}):
        ids[f"{area['type']}_id"] = ids[f"{area['type']}_id"] or area["_id"]
    return ids


def lookup(lat: float, lng: float) -> dict:
    """Which thana + ward is this point in, and which police stations are nearest?"""
    point = {"type": "Point", "coordinates": [lng, lat]}
    found = {"thana": None, "ward": None}
    for area in get_db().areas.find({"is_active": True, "geom": {"$geoIntersects": {"$geometry": point}}},
                                    {"geom": 0}):
        found[area["type"]] = found[area["type"]] or public_area(area)
    inside = bool(found["thana"] or found["ward"])
    return {
        "lat": lat, "lng": lng, "inside_dhaka": inside, **found,
        "nearest_police_stations": nearest_stations(lat, lng) if inside else [],
    }


# ---------------------------------------------------------------- Task 13: the city outline
_outline_cache: dict | None = None


def city_outline() -> dict:
    """The edge of the area SafeZone covers (all thanas joined into one shape) + its box.

    The map picker draws this edge and stops people scrolling far away from Dhaka.
    Joining 41 shapes takes a moment, so the answer is remembered after the first time.
    """
    global _outline_cache
    if _outline_cache is None:
        shapes = [shape(a["geom"]) for a in get_db().areas.find({"type": "thana", "is_active": True}, {"geom": 1})]
        if not shapes:
            raise AppError(503, "areas_not_loaded", "The map areas are not loaded yet. Run 'SafeZone: load Dhaka areas'.")
        city = unary_union(shapes).buffer(0.0003).buffer(-0.0003)  # close tiny gaps between neighbours
        west, south, east, north = city.bounds
        _outline_cache = {
            "outline": mapping(set_precision(city.simplify(0.0002), 0.00001)),  # ~1 m is precise enough
            "bounds": {"south": round(south, 5), "west": round(west, 5), "north": round(north, 5), "east": round(east, 5)},
            "center": {"lat": round((south + north) / 2, 5), "lng": round((west + east) / 2, 5)},
        }
    return _outline_cache


def forget_city_outline() -> None:
    """Called after the areas are (re)loaded, so the outline is rebuilt."""
    global _outline_cache
    _outline_cache = None
