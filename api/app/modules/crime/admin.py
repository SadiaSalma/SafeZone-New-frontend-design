"""
admin.py (crime) - Task 27: crime categories and the monthly crime figures (FR-24, design doc 5.8).

Crime statistics are NOT SafeZone's own theft reports - they are official monthly totals
(e.g. from DMP crime statistics) that an admin types in, per area and category, always with a SOURCE.
Only totals: never names, addresses or single cases.

  categories   e.g. "Robbery" with a WEIGHT (how serious it is). The danger score (Task 28) adds
               count x weight, so one murder (10) weighs as much as 10 "other" crimes (1).
  crime_stats  one number per (area, category, month). Saving only writes the cells that changed,
               and every change gets its own audit line (who, when, from what to what).
"""
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.audit import write_audit
from app.db import get_db
from app.errors import AppError

# Design doc 5.8: the starting categories and weights (admins can change them)
DEFAULT_CATEGORIES = [
    ("murder", "Murder", "হত্যা", 10),
    ("rape", "Rape", "ধর্ষণ", 10),
    ("kidnapping", "Kidnapping", "অপহরণ", 8),
    ("robbery", "Robbery", "ডাকাতি", 6),
    ("snatching", "Mugging / snatching", "ছিনতাই", 4),
    ("vehicle_theft", "Car or CNG theft", "গাড়ি বা সিএনজি চুরি", 3),
    ("motorbike_theft", "Motorbike theft", "মোটরসাইকেল চুরি", 3),
    ("burglary", "Burglary", "সিঁধেল চুরি", 3),
    ("other", "Other crimes", "অন্যান্য অপরাধ", 1),
]


def seed_categories(db: Database | None = None) -> int:
    db = db if db is not None else get_db()
    added = 0
    for order, (key, en, bn, weight) in enumerate(DEFAULT_CATEGORIES):
        result = db.crime_categories.update_one(
            {"key": key},
            {"$setOnInsert": {"key": key, "name_en": en, "name_bn": bn, "weight": weight, "is_active": True, "order": order}},
            upsert=True)
        added += result.upserted_id is not None
    return added


def public_category(c: dict) -> dict:
    return {"id": str(c["_id"]), "key": c["key"], "name_en": c["name_en"], "name_bn": c.get("name_bn", ""),
            "weight": c["weight"], "is_active": c["is_active"], "order": c["order"]}


def categories(active_only: bool = False) -> list[dict]:
    query = {"is_active": True} if active_only else {}
    return [public_category(c) for c in get_db().crime_categories.find(query).sort("order", 1)]


def _oid(value: str, what: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise AppError(404, f"{what}_not_found", f"This {what.replace('_', ' ')} does not exist.")


def add_category(user: dict, key: str, name_en: str, name_bn: str, weight: float) -> dict:
    db = get_db()
    last = db.crime_categories.find_one(sort=[("order", -1)])
    doc = {"key": key, "name_en": name_en, "name_bn": name_bn, "weight": weight, "is_active": True,
           "order": (last["order"] + 1) if last else 0}
    try:
        doc["_id"] = db.crime_categories.insert_one(doc).inserted_id
    except DuplicateKeyError:
        raise AppError(409, "category_exists", "A category with this key already exists.", {"key": "Already used."})
    write_audit("crime_category.create", "crime_categories", entity_id=doc["_id"], actor_id=user["_id"],
                actor_role=user["role"], after={"key": key, "weight": weight})
    return public_category(doc)


def update_category(user: dict, category_id: str, changes: dict) -> dict:
    db = get_db()
    oid = _oid(category_id, "category")
    before = db.crime_categories.find_one({"_id": oid})
    if not before:
        raise AppError(404, "category_not_found", "This category does not exist.")
    clean = {k: v for k, v in changes.items() if v is not None}
    after = db.crime_categories.find_one_and_update({"_id": oid}, {"$set": clean}, return_document=ReturnDocument.AFTER)
    write_audit("crime_category.update", "crime_categories", entity_id=oid, actor_id=user["_id"], actor_role=user["role"],
                after={k: clean[k] for k in clean})
    return public_category(after)


# ---------------------------------------------------------------- the monthly table
def month_start(month: str) -> datetime:
    """'2026-10' -> 1 October 2026, 00:00 UTC (the month is stored as its first day)."""
    try:
        year, number = (int(x) for x in month.split("-"))
        return datetime(year, number, 1, tzinfo=timezone.utc)
    except (ValueError, TypeError):
        raise AppError(422, "invalid_input", "Write the month like 2026-10.", {"month": "Write the month like 2026-10."})


def month_table(month: str, level: str) -> dict:
    """Rows = areas of one level (thanas or wards), columns = active categories, cells = the saved figures."""
    db = get_db()
    start = month_start(month)
    cats = categories(active_only=True)
    areas = list(db.areas.find({"type": level, "is_active": True}, {"geom": 0}))
    areas.sort(key=lambda a: (int(a["code"][5:]) if level == "ward" else 0, a["name_en"]))
    cells: dict[str, dict[str, int]] = {}
    sources = set()
    for stat in db.crime_stats.find({"month": start, "area_id": {"$in": [a["_id"] for a in areas]}}):
        cells.setdefault(str(stat["area_id"]), {})[str(stat["category_id"])] = stat["count"]
        sources.add(stat["source"])
    return {
        "month": month, "level": level, "categories": cats,
        "rows": [{"area_id": str(a["_id"]), "code": a["code"], "name_en": a["name_en"], "name_bn": a.get("name_bn", ""),
                  "cells": cells.get(str(a["_id"]), {})} for a in areas],
        "sources": sorted(sources),
    }


def save_figures(user: dict, month: str, source: str, changes: list[dict]) -> dict:
    """Write each changed cell (area, category, count). count = None deletes the figure. One audit line per change."""
    db = get_db()
    start = month_start(month)
    if start > datetime.now(timezone.utc):
        raise AppError(422, "invalid_input", "You can't enter figures for a future month.", {"month": "This month hasn't happened yet."})
    area_ids = {str(a["_id"]) for a in db.areas.find({"is_active": True}, {"_id": 1})}
    cat_ids = {str(c["_id"]) for c in db.crime_categories.find({}, {"_id": 1})}
    now = datetime.now(timezone.utc)
    saved = removed = 0
    for change in changes:
        if change["area_id"] not in area_ids or change["category_id"] not in cat_ids:
            raise AppError(422, "invalid_input", "Unknown area or category in the table.")
        key = {"area_id": ObjectId(change["area_id"]), "category_id": ObjectId(change["category_id"]), "month": start}
        before = db.crime_stats.find_one(key, {"count": 1})
        if change["count"] is None:
            if before:
                db.crime_stats.delete_one(key)
                removed += 1
        else:
            if before and before["count"] == change["count"]:
                continue  # nothing really changed
            db.crime_stats.update_one(key, {"$set": {**key, "count": change["count"], "source": source,
                                                     "updated_by": user["_id"], "updated_at": now}}, upsert=True)
            saved += 1
        write_audit("crime_stat.update", "crime_stats", actor_id=user["_id"], actor_role=user["role"],
                    after={"area_id": change["area_id"], "category_id": change["category_id"], "month": month,
                           "from": before["count"] if before else None, "to": change["count"], "source": source})
    return {"saved": saved, "removed": removed}
