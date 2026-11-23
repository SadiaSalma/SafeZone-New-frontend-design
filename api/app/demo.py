"""
demo.py - Task 32: demo data for presentations, CLEARLY FLAGGED and removable with one command.

    python -m scripts.demo_data add      (or VS Code: Run Task -> "SafeZone: add demo data")
    python -m scripts.demo_data remove   (or VS Code: Run Task -> "SafeZone: remove demo data")

What "add" creates (everything gets is_demo: true, or the source "Demo data - not real figures"):
  - 4 demo accounts: 2 victims, 1 verifier, 1 admin (passwords below - for a local demo ONLY)
  - about 30 approved theft reports spread over Dhaka in the last 30 days, each with a sent alert,
    so the map, the alerts page and the area dashboards have something to show
  - 2 reports waiting in the review queue, so the verifier can show a review live
  - monthly crime figures for every thana for the last 6 whole months (for the danger map)
Every report text says "Demo report - not a real theft". Nothing is sent to real phones or browsers.

Reports the demo accounts sent by hand (practice) are flagged as demo too, so they are labelled.
Running "add" again replaces only the GENERATED demo items (demo_seed: true), never the practice ones.
"remove" deletes all of it again (the demo accounts and their practice reports too), and nothing else.
"""
import hashlib
import random
from datetime import datetime, timedelta, timezone

from pymongo import UpdateOne

from app.db import get_db
from app.modules.alerts.text import template
from app.modules.areas.service import find_area_ids
from app.modules.reports.checks import refresh_checks
from app.modules.review.decisions import move_point
from app.security import hash_password

DEMO_SOURCE = "Demo data - not real figures"
DEMO_TEXT = "Demo report - not a real theft."

# For a LOCAL demo only. Never use these on a real server.
DEMO_ACCOUNTS = [
    {"name_en": "Nila Rahman", "phone": "+8801799000222", "password": "demo-pass-123", "role": "victim"},
    {"name_en": "Karim Hossain", "phone": "+8801799000555", "password": "demo-pass-123", "role": "victim"},
    {"name_en": "Rafiq Hasan", "phone": "+8801799000333", "password": "verify-pass-123", "role": "verifier"},
    {"name_en": "Tania Akter", "phone": "+8801799000444", "password": "admin-pass-123", "role": "admin"},
]

# Busy, well-known places (longitude, latitude) - demo thefts happen near them
HOTSPOTS = [
    (90.3874, 23.7577, "Farmgate"), (90.3687, 23.8069, "Mirpur 10"), (90.4152, 23.7806, "Gulshan 1"),
    (90.3742, 23.7516, "Dhanmondi 27"), (90.4176, 23.7330, "Motijheel"), (90.3984, 23.8759, "Uttara"),
    (90.4005, 23.7778, "Mohakhali"), (90.4266, 23.7806, "Badda"), (90.4341, 23.7104, "Jatrabari"),
    (90.3958, 23.7384, "Shahbagh"), (90.3847, 23.7337, "New Market"), (90.4043, 23.7937, "Banani"),
    (90.4227, 23.7612, "Rampura"), (90.3587, 23.7662, "Mohammadpur"), (90.4253, 23.7487, "Khilgaon"),
    (90.4125, 23.7103, "Sadarghat"),
]
TYPES = ["phone_snatching"] * 5 + ["bag_snatching"] * 3 + ["pickpocket"] * 2 + ["motorbike_theft", "bicycle_theft",
                                                                                 "cng_theft", "shop_theft", "burglary"]


def _accounts(db, now: datetime) -> dict:
    """Create the demo accounts, or mark them as demo if they already exist. Returns {phone: user}."""
    users = {}
    for a in DEMO_ACCOUNTS:
        found = db.users.find_one({"phone": a["phone"]})
        if found:
            db.users.update_one({"_id": found["_id"]}, {"$set": {"is_demo": True}})
        else:
            db.users.insert_one({
                "name_en": a["name_en"], "name_bn": "", "phone": a["phone"],
                "password_hash": hash_password(a["password"]), "role": a["role"], "status": "active",
                "phone_verified_at": now, "failed_logins": 0, "locked_until": None, "created_at": now,
                "deleted_at": None, "is_demo": True})
        users[a["phone"]] = db.users.find_one({"phone": a["phone"]})
    return users


def _report(db, owner: dict, n: int, rng: random.Random, now: datetime, status: str) -> dict:
    lng0, lat0, place = rng.choice(HOTSPOTS)
    lng, lat = move_point(lng0, lat0, rng)  # spread around the hotspot
    # at least 2 days old, so the demo victims can still send a live report (limit: 5 per 24 hours)
    occurred = now - timedelta(days=rng.uniform(2, 29))
    occurred = occurred.replace(hour=rng.choice([8, 9, 12, 13, 17, 18, 19, 20, 21, 22]), minute=rng.randrange(60))
    if occurred > now:
        occurred -= timedelta(days=1)
    station = db.police_stations.find_one({"location": {"$near": {"$geometry": {"type": "Point", "coordinates": [lng, lat]}}}})
    areas = find_area_ids(lat, lng)
    theft = rng.choice(TYPES)
    return {
        "user_id": owner["_id"], "status": status, "theft_type": theft, "occurred_at": occurred,
        "submitted_at": occurred + timedelta(minutes=rng.randint(40, 300)),
        "location": {"type": "Point", "coordinates": [lng, lat]},
        "public_location": {"type": "Point", "coordinates": list(move_point(lng, lat, rng))} if status == "ALERTED" else None,
        "thana_id": areas["thana_id"], "ward_id": areas["ward_id"],
        "landmark": f"Near {place} (demo)", "description": DEMO_TEXT, "stolen_items": "Demo item",
        "gd": {"type": "GD", "number": str(1000 + n), "date": occurred,
               "police_station_id": station["_id"] if station else None},
        "gd_hash": hashlib.sha256(f"demo|{n}".encode()).hexdigest(), "gd_active": True,
        "is_demo": True, "demo_seed": True,
    }


def _phones_near(db, lng: float, lat: float, radius_m: int) -> int:
    return db.virtual_phones.count_documents({"location": {"$geoWithin": {"$centerSphere": [[lng, lat], radius_m / 6_378_100]}}})


def add(seed: int = 7, reports: int = 30, now: datetime | None = None) -> dict:
    """Add the demo data. Running it twice first removes the old demo data, so nothing is doubled."""
    now = now or datetime.now(timezone.utc)
    db = get_db()
    remove(keep_accounts=True)
    rng = random.Random(seed)
    users = _accounts(db, now)
    # Practice reports sent by the demo accounts: label them as demo too
    practice = [r["_id"] for r in db.reports.find({"user_id": {"$in": [u["_id"] for u in users.values()]}}, {"_id": 1})]
    db.reports.update_many({"_id": {"$in": practice}}, {"$set": {"is_demo": True}})
    db.alerts.update_many({"report_id": {"$in": practice}}, {"$set": {"is_demo": True}})
    victims = [users["+8801799000222"], users["+8801799000555"]]
    verifier = users["+8801799000333"]

    made = 0
    for n in range(reports):
        doc = _report(db, victims[n % 2], n, rng, now, "ALERTED")
        if not doc["thana_id"]:
            continue
        rid = db.reports.insert_one(doc).inserted_id
        doc["_id"] = rid
        decided = doc["submitted_at"] + timedelta(minutes=rng.randint(5, 40))
        db.decisions.insert_one({"report_id": rid, "verifier_id": verifier["_id"], "decision": "approve",
                                 "reason": "", "note": "Demo", "created_at": decided, "is_demo": True})
        texts = template(doc, now)
        lng, lat = doc["location"]["coordinates"]
        db.alerts.insert_one({
            "report_id": rid, "area_id": doc["ward_id"], "text_en": "[DEMO] " + texts["text_en"], "text_bn": "[ডেমো] " + texts["text_bn"],
            "center": doc["location"], "radius_m": 1000, "status": "sent", "towers": rng.randint(4, 9),
            "phones": _phones_near(db, lng, lat, 1000), "push_sent": 0, "push_failed": 0,
            "queued_at": decided, "sent_at": decided + timedelta(seconds=rng.uniform(2, 9)),
            "seconds_to_send": round(rng.uniform(2, 9), 2), "attempts": 1, "lease_until": None, "last_error": "",
            "is_demo": True, "demo_seed": True})
        made += 1

    # Two reports waiting for review (one looks fine, one has warnings for the verifier to explain)
    waiting = 0
    for n in range(reports, reports + 2):
        doc = _report(db, victims[1], n, rng, now, "PENDING_REVIEW")
        doc["occurred_at"] = now - timedelta(hours=3 + n - reports)
        doc["submitted_at"] = now - timedelta(minutes=50 + 30 * (n - reports))
        doc["gd"]["date"] = doc["occurred_at"]
        if n == reports + 1:
            doc["gd"]["number"] = "X/99"  # an unusual GD number -> a warning
        rid = db.reports.insert_one(doc).inserted_id
        refresh_checks(rid)
        waiting += 1

    figures = _crime_figures(db, rng, now)
    return {"reports": made, "waiting": waiting, "crime_figures": figures, "accounts": len(users)}


def _crime_figures(db, rng: random.Random, now: datetime) -> int:
    """Monthly figures for every thana for the last 6 whole months (busier in the old city)."""
    cats = list(db.crime_categories.find({"is_active": True}))
    base = {"snatching": 6, "robbery": 3, "burglary": 3, "vehicle_theft": 2, "motorbike_theft": 2,
            "murder": 0.3, "rape": 0.3, "kidnapping": 0.4, "other": 4}
    busy = {"kotwali", "lalbagh", "chawkbazar", "bangshal", "sutrapur", "motijheel", "paltan", "shahbagh",
            "tejgaon", "mirpur", "jatrabari"}
    months = []
    for back in range(1, 7):  # the 6 whole months before this one
        year, month = now.year, now.month - back
        while month <= 0:
            month += 12
            year -= 1
        months.append(datetime(year, month, 1, tzinfo=timezone.utc))
    # Never overwrite figures an admin entered
    taken = {(s["area_id"], s["category_id"], s["month"]) for s in db.crime_stats.find(
        {"month": {"$in": months}, "source": {"$ne": DEMO_SOURCE}}, {"area_id": 1, "category_id": 1, "month": 1})}
    ops = []
    for month in months:
        for area in db.areas.find({"type": "thana"}, {"code": 1, "size_km2": 1}):
            factor = (2.2 if any(b in area["code"] for b in busy) else 1.0) * min(3.0, max(0.6, (area.get("size_km2") or 5) / 6))
            for c in cats:
                if (area["_id"], c["_id"], month) in taken:
                    continue
                value = max(0, round(rng.gauss(base.get(c["key"], 1) * factor, 1.2)))
                key = {"area_id": area["_id"], "category_id": c["_id"], "month": month}
                ops.append(UpdateOne(key, {"$set": {**key, "count": value, "source": DEMO_SOURCE, "updated_at": now}}, upsert=True))
    if ops:
        db.crime_stats.bulk_write(ops, ordered=False)
    return len(ops)


def remove(keep_accounts: bool = False) -> dict:
    """Delete everything flagged as demo (and nothing else).
    keep_accounts=True (used by "add"): only the generated items go; accounts and practice reports stay."""
    db = get_db()
    demo_users = [u["_id"] for u in db.users.find({"is_demo": True}, {"_id": 1})]
    if keep_accounts:
        query: dict = {"$or": [{"demo_seed": True}, {"description": DEMO_TEXT, "is_demo": True}]}
    else:  # flagged ones, plus any report a demo account sent while practising
        query = {"$or": [{"is_demo": True}, {"user_id": {"$in": demo_users}}]}
    report_ids = [r["_id"] for r in db.reports.find(query, {"_id": 1})]
    alert_ids = [a["_id"] for a in db.alerts.find({"report_id": {"$in": report_ids}}, {"_id": 1})]

    from app import storage  # here, so importing this file never touches the disk
    for photo in db.report_photos.find({"report_id": {"$in": report_ids}}):
        storage.delete(photo["storage_key"])
    db.report_photos.delete_many({"report_id": {"$in": report_ids}})
    db.virtual_inbox.delete_many({"alert_id": {"$in": alert_ids}})
    db.alert_deliveries.delete_many({"alert_id": {"$in": alert_ids}})
    db.alerts.delete_many({"_id": {"$in": alert_ids}})
    db.decisions.delete_many({"report_id": {"$in": report_ids}})
    for scan in db.gd_scans.find({"report_id": {"$in": report_ids}}, {"storage_key": 1}):  # Task 29
        storage.delete(scan["storage_key"])
    db.gd_scans.delete_many({"report_id": {"$in": report_ids}})
    result = {"reports": db.reports.delete_many({"_id": {"$in": report_ids}}).deleted_count,
              "alerts": len(alert_ids),
              "crime_figures": db.crime_stats.delete_many({"source": DEMO_SOURCE}).deleted_count,
              "accounts": 0}
    if not keep_accounts:
        db.sessions.delete_many({"user_id": {"$in": demo_users}})
        db.push_subscriptions.delete_many({"user_id": {"$in": demo_users}})
        db.virtual_phones.delete_many({"owner_id": {"$in": demo_users}, "is_test": True})
        from app.modules.ocr.service import delete_for_user
        for uid in demo_users:
            delete_for_user(uid)
        result["accounts"] = db.users.delete_many({"_id": {"$in": demo_users}}).deleted_count
    return result
