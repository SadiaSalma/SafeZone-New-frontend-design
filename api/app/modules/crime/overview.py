"""
overview.py (crime) - Task 28: the danger score, levels and top 10 (FR-23, design doc 5.8, Design Revisions R6).

Danger score of an area, for the chosen months and category:

    score = sum over categories of (figure x category weight)  /  area size in km²

Dividing by km² is fair: a big thana naturally has more crime than a tiny one (R6).
A "total" mode (no division) is kept for people who want the raw numbers.

Thanas and wards are ranked SEPARATELY (mixing them would count each crime twice - R6).

Levels are RELATIVE (by rank, among areas that have figures):
    top 10% -> Very high, next 20% -> High, next 30% -> Medium, the rest -> Low
    no figures in the period -> No data
"Very high" therefore means "among the highest in Dhaka", not "above a safe limit".
"""
from datetime import datetime, timezone

from app.db import get_db
from app.errors import AppError

LEVELS = [("very_high", 0.10), ("high", 0.20), ("medium", 0.30)]  # the rest with figures: low


def _months_back(n: int, now: datetime) -> datetime:
    """The first day of the month that is n-1 months before now's month (n=1 -> this month)."""
    year, month = now.year, now.month - (n - 1)
    while month <= 0:
        month += 12
        year -= 1
    return datetime(year, month, 1, tzinfo=timezone.utc)


def level_for(rank: int, count: int) -> str:
    """rank 0 = highest score, among `count` areas that have figures."""
    position = rank / count  # 0 .. <1
    edge = 0.0
    for name, share in LEVELS:
        edge += share
        if position < edge - 1e-9:
            return name
    return "low"


def overview(months: int, category: str | None, level: str, mode: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    db = get_db()
    # Figures are monthly totals: "last 3 months" = the 3 most recent whole months before this one,
    # because the current month's figures are usually not published yet.
    since = _months_back(months + 1, now)
    until = _months_back(1, now)

    cats = {c["_id"]: c for c in db.crime_categories.find({"is_active": True})}
    if category:
        chosen = [c for c in cats.values() if c["key"] == category]
        if not chosen:
            raise AppError(422, "invalid_input", "Unknown crime category.", {"category": "Unknown crime category."})
        cats = {chosen[0]["_id"]: chosen[0]}

    areas = {a["_id"]: a for a in db.areas.find({"type": level, "is_active": True}, {"geom": 0})}
    stats = db.crime_stats.find({"month": {"$gte": since, "$lt": until}, "area_id": {"$in": list(areas)},
                                 "category_id": {"$in": list(cats)}})

    weighted: dict = {}
    totals: dict = {}
    by_cat_area: dict = {}
    by_category: dict = {}
    sources = set()
    for s in stats:
        cat = cats[s["category_id"]]
        weighted[s["area_id"]] = weighted.get(s["area_id"], 0) + s["count"] * cat["weight"]
        totals[s["area_id"]] = totals.get(s["area_id"], 0) + s["count"]
        by_cat_area.setdefault(s["area_id"], {}).setdefault(cat["key"], 0)
        by_cat_area[s["area_id"]][cat["key"]] += s["count"]
        by_category[cat["key"]] = by_category.get(cat["key"], 0) + s["count"]
        sources.add(s["source"])

    rows = []
    for area_id, area in areas.items():
        if area_id not in weighted:
            continue
        size = area.get("size_km2") or 1
        score = weighted[area_id] / size if mode == "per_km2" else weighted[area_id]
        top_key = max(by_cat_area[area_id].items(), key=lambda kv: kv[1])[0]
        rows.append({"code": area["code"], "name_en": area["name_en"], "name_bn": area.get("name_bn", ""),
                     "size_km2": area.get("size_km2"), "score": round(score, 2), "total": totals[area_id],
                     "top_category": top_key})
    rows.sort(key=lambda r: -r["score"])
    for rank, row in enumerate(rows):
        row["rank"] = rank + 1
        row["level"] = level_for(rank, len(rows))

    no_data = [{"code": a["code"], "name_en": a["name_en"], "name_bn": a.get("name_bn", ""), "level": "no_data"}
               for i, a in areas.items() if i not in weighted]
    cat_names = {c["key"]: (c["name_en"], c.get("name_bn", "")) for c in db.crime_categories.find()}
    return {
        "months": months, "from": since, "until": until, "level": level, "mode": mode, "category": category,
        "areas": rows + no_data,
        "top10": rows[:10],
        "by_category": [{"key": k, "name_en": cat_names[k][0], "name_bn": cat_names[k][1], "count": n}
                        for k, n in sorted(by_category.items(), key=lambda kv: -kv[1])],
        "categories": [{"key": c["key"], "name_en": c["name_en"], "name_bn": c.get("name_bn", ""), "weight": c["weight"]}
                       for c in sorted(db.crime_categories.find({"is_active": True}), key=lambda c: c["order"])],
        "sources": sorted(sources),
        "areas_with_data": len(rows),
    }

