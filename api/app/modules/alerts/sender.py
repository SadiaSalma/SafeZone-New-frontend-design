"""
sender.py (alerts) - Task 22: the alert job that sends approved alerts (design doc 5.5, Design Revisions R5).

The job works through the "queued" alerts one by one:

  1. LEASE the alert: one atomic step sets status "sending" and lease_until = now + 60 s.
     If the server crashes while sending, the lease runs out and the next run picks it up again.
  2. Find the towers whose 1 km range touches the alert circle.
  3. Find every virtual phone on those towers and put the alert in their inbox
     (in batches of 1000; the unique index (phone, alert) means a retry never gives a phone two copies).
  4. One delivery record per tower (upserted, so a retry doesn't double it).
  5. Web push to people who follow the area (Task 23 plugs in here).
  6. Mark the alert "sent" with the counts and how many seconds it took; the report becomes ALERTED;
     the victim is told how many phones were warned.

If something fails, the alert goes back to "queued" and is tried again after a short pause
(30 s, then 60 s - "back-off", so a struggling server isn't hammered), at most 3 attempts.
After 3 failures it is "failed" and the report becomes ALERT_FAILED - an admin can resend it.
Every step is safe to repeat, so retrying is always safe.
"""
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument, UpdateOne
from pymongo.errors import BulkWriteError

from app.audit import write_audit
from app.db import get_db
from app.modules.push.service import notify_user, push_for_alert
from app.notify import send_notice

LEASE_SECONDS = 60
MAX_ATTEMPTS = 3
RETRY_PAUSE_SECONDS = 30  # pause before the next attempt, times the number of attempts so far
BATCH = 1000



def claim_next(now: datetime | None = None) -> dict | None:
    """Take the oldest queued alert (or one whose lease ran out) - only ONE worker can win it.
    For a queued alert, lease_until means "not before" (the pause after a failed attempt)."""
    now = now or datetime.now(timezone.utc)
    ready = {"$or": [{"lease_until": None}, {"lease_until": {"$lt": now}}]}
    return get_db().alerts.find_one_and_update(
        {"$or": [{"status": "queued", **ready}, {"status": "sending", "lease_until": {"$lt": now}}]},
        {"$set": {"status": "sending", "lease_until": now + timedelta(seconds=LEASE_SECONDS)}, "$inc": {"attempts": 1}},
        sort=[("queued_at", 1)],
        return_document=ReturnDocument.AFTER,
    )


def towers_for(alert: dict) -> list[dict]:
    """Towers whose range touches the alert circle: centre distance <= alert radius + tower range."""
    db = get_db()
    biggest = db.cell_towers.find_one({}, {"range_m": 1}, sort=[("range_m", -1)])
    longest_range = biggest["range_m"] if biggest else 1000
    near = db.cell_towers.find({"location": {"$nearSphere": {"$geometry": alert["center"],
                                                             "$maxDistance": alert["radius_m"] + longest_range}}})
    return list(near)


def deliver(alert: dict) -> dict:
    """Steps 2-5. Safe to run again for the same alert."""
    db = get_db()
    now = datetime.now(timezone.utc)
    towers = towers_for(alert)
    tower_ids = [t["_id"] for t in towers]

    phones_reached = 0
    batch: list[dict] = []

    def flush():
        nonlocal batch
        if not batch:
            return
        try:
            db.virtual_inbox.insert_many(batch, ordered=False)
        except BulkWriteError as error:  # copies from an earlier attempt are already there: fine
            if any(e["code"] != 11000 for e in error.details.get("writeErrors", [])):
                raise
        batch = []

    for phone in db.virtual_phones.find({"tower_id": {"$in": tower_ids}}, {"_id": 1}):
        batch.append({"phone_id": phone["_id"], "alert_id": alert["_id"], "received_at": now})
        phones_reached += 1
        if len(batch) >= BATCH:
            flush()
    flush()

    per_tower = {row["_id"]: row["n"] for row in db.virtual_phones.aggregate([
        {"$match": {"tower_id": {"$in": tower_ids}}}, {"$group": {"_id": "$tower_id", "n": {"$sum": 1}}}])}
    if towers:
        db.alert_deliveries.bulk_write([
            UpdateOne({"alert_id": alert["_id"], "channel": "sim_broadcast", "target": t["code"]},
                      {"$set": {"count": per_tower.get(t["_id"], 0), "status": "sent", "sent_at": now}}, upsert=True)
            for t in towers])

    push_sent, push_failed = push_for_alert(alert)  # Task 23: people who follow this area
    return {"towers": len(towers), "phones": phones_reached, "push_sent": push_sent, "push_failed": push_failed}


def _finish(alert: dict, counts: dict) -> None:
    db = get_db()
    now = datetime.now(timezone.utc)
    queued_at = alert["queued_at"] if alert["queued_at"].tzinfo else alert["queued_at"].replace(tzinfo=timezone.utc)
    db.alerts.update_one({"_id": alert["_id"]}, {"$set": {
        **counts, "status": "sent", "sent_at": now, "lease_until": None, "last_error": "",
        "seconds_to_send": round((now - queued_at).total_seconds(), 2)}})
    report = db.reports.find_one_and_update({"_id": alert["report_id"], "status": {"$in": ["VERIFIED", "ALERT_FAILED"]}},
                                            {"$set": {"status": "ALERTED"}})
    write_audit("alert.sent", "alerts", entity_id=alert["_id"], actor_role="system",
                after={"phones": counts["phones"], "towers": counts["towers"]})
    if report and report.get("user_id"):
        message = f"Thank you. Your report warned {counts['phones']} phones near the place."
        victim = db.users.find_one({"_id": report["user_id"]}, {"phone": 1})
        if victim:
            send_notice(victim["phone"], message)
        notify_user(report["user_id"], "Your alert was sent", message)  # Task 23: a push too


def _failed(alert: dict, error: Exception) -> None:
    db = get_db()
    message = f"{type(error).__name__}: {error}"[:300]
    if alert["attempts"] >= MAX_ATTEMPTS:
        db.alerts.update_one({"_id": alert["_id"]}, {"$set": {"status": "failed", "lease_until": None, "last_error": message}})
        db.reports.update_one({"_id": alert["report_id"], "status": "VERIFIED"}, {"$set": {"status": "ALERT_FAILED"}})
        write_audit("alert.failed", "alerts", entity_id=alert["_id"], actor_role="system", after={"attempts": alert["attempts"]})
    else:  # try again after a pause
        pause = timedelta(seconds=RETRY_PAUSE_SECONDS * alert["attempts"])
        db.alerts.update_one({"_id": alert["_id"]}, {"$set": {"status": "queued", "last_error": message,
                                                             "lease_until": datetime.now(timezone.utc) + pause}})


def run_once() -> int:
    """Send every alert that is waiting. Returns how many were handled."""
    handled = 0
    while (alert := claim_next()) is not None:
        try:
            counts = deliver(alert)
            _finish(alert, counts)
        except Exception as error:  # noqa: BLE001 - any failure: retry later, never crash the job
            _failed(alert, error)
        handled += 1
    return handled
