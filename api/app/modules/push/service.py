"""
service.py (push) - Task 23: browser push notifications (FR-18, Design Revisions R4).

How web push works, in short:
  1. The browser asks the person "Allow notifications?". If yes, it creates a SUBSCRIPTION:
     an address at its push service (Google / Mozilla / Apple) + two keys.
  2. The website sends that subscription here, with the areas the person wants to follow.
  3. When an alert is sent for one of those areas, we sign a small message with our private
     VAPID key and post it to that address. The push service wakes the browser, and our
     service worker (web/public/sw.js) shows the notification - even if the website is closed.

Limits (R4): push needs HTTPS (localhost is allowed for the demo), and on iPhones it only works
when SafeZone is added to the Home Screen. Everyone can always see alerts on the website too.
A subscription the push service says is gone (404/410) is deleted.

First alert after following: a few seconds after a browser starts following a NEW area
(FOLLOW_TEST_ALERT_SECONDS, 5 by default, 0 = off), it gets the area's LATEST REAL alert from the last
30 days (e.g. "Phone snatching · Tejgaon"), with its real date - nothing is made up. The person sees right
away what is happening in the area, and that notifications work on this device (pop-up + full-screen alarm).
An area with no alert in 30 days gets a short "alerts are on" message instead.
"""
import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pywebpush import WebPushException, webpush

from app.config import settings
from app.db import get_db
from app.errors import AppError
from app.modules.areas.service import public_area
from app.modules.alerts.text import template
from app.modules.reports.schemas import THEFT_LABELS

LATEST_ALERT_DAYS = 30


def enabled() -> bool:
    return bool(settings.vapid_public_key and settings.vapid_private_key)


def public_key() -> dict:
    return {"enabled": enabled(), "public_key": settings.vapid_public_key or None}


def _areas_from_codes(codes: list[str]) -> list[dict]:
    if len(codes) > settings.follow_areas_max:
        raise AppError(422, "too_many_areas", f"You can follow at most {settings.follow_areas_max} areas.")
    found = list(get_db().areas.find({"code": {"$in": codes}, "is_active": True}, {"geom": 0}))
    if len(found) != len(set(codes)):
        raise AppError(422, "unknown_area", "One of the areas does not exist.")
    return found


def subscribe(endpoint: str, keys: dict, area_codes: list[str], lang: str, user: dict | None) -> dict:
    areas = _areas_from_codes(area_codes)
    now = datetime.now(timezone.utc)
    before = get_db().push_subscriptions.find_one({"endpoint": endpoint}, {"area_ids": 1}) or {}
    new_areas = [a for a in areas if a["_id"] not in before.get("area_ids", [])]
    get_db().push_subscriptions.update_one(
        {"endpoint": endpoint},
        {"$set": {"endpoint": endpoint, "keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]},
                  "area_ids": [a["_id"] for a in areas], "lang": lang,
                  "user_id": user["_id"] if user else None, "updated_at": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    answer = status(endpoint)
    answer["test_alert_in"], answer["first_alert"] = None, None
    if new_areas:
        message = first_alert(new_areas[-1], lang)
        answer["test_alert_in"] = schedule_first_alert(endpoint, message)
        if answer["test_alert_in"] is not None:  # the page shows the same alert, in case the push is slow
            answer["first_alert"] = {k: message[k] for k in ("title", "body", "url", "test")}
    return answer


# ---------------------------------------------------------------- the first alert after following
def latest_alert(area: dict, now: datetime | None = None) -> tuple[dict, dict] | None:
    """The newest SENT alert for a thana/ward in the last 30 days, with its report."""
    now = now or datetime.now(timezone.utc)
    db = get_db()
    reports = db.reports.find({"$or": [{"thana_id": area["_id"]}, {"ward_id": area["_id"]}], "status": "ALERTED",
                               "occurred_at": {"$gte": now - timedelta(days=LATEST_ALERT_DAYS)}}).sort("occurred_at", -1).limit(20)
    for report in reports:
        alert = db.alerts.find_one({"report_id": report["_id"], "status": "sent"})
        if alert:
            return alert, report
    return None


def first_alert(area: dict, lang: str) -> dict:
    """What a browser gets right after following `area`: its latest real alert, or an "alerts are on" note."""
    bangla = lang == "bn"
    name = (area.get("name_bn") or area["name_en"]) if bangla else area["name_en"]
    found = latest_alert(area)
    if found:
        alert, report = found
        texts = template(report)  # written again now, so "today"/"yesterday" are still right
        body = texts["text_bn"] if bangla else texts["text_en"]
        if alert.get("is_demo"):
            body = ("[ডেমো] " if bangla else "[DEMO] ") + body
        theft = THEFT_LABELS[report["theft_type"]][1 if bangla else 0]
        return {"title": f"{theft} · {name}", "body": body, "url": f"/alerts/{alert['_id']}",
                "tag": f"alert-{alert['_id']}", "test": False}
    if bangla:
        title, body = (f"{name}-এর সতর্কবার্তা চালু হয়েছে",
                       f"গত {LATEST_ALERT_DAYS} দিনে {name} এলাকায় কোনো যাচাই করা চুরি নেই। কোনো চুরি যাচাই হলে আপনি এভাবেই সতর্কবার্তা পাবেন।")
    else:
        title, body = (f"Alerts for {name} are on",
                       f"No verified theft near {name} in the last {LATEST_ALERT_DAYS} days. When one is verified, you will get an alert like this.")
    return {"title": title, "body": body, "url": f"/areas/{area['code']}", "tag": f"alert-on-{area['code']}", "test": True}


def schedule_first_alert(endpoint: str, message: dict) -> int | None:
    """Send the first alert after a few seconds. Returns the seconds, or None when it is off."""
    delay = settings.follow_test_alert_seconds
    if not enabled() or delay < 0 or (delay > 0 and not settings.background_jobs):
        return None  # tests switch the background jobs off; they call send_first_alert() themselves
    if delay == 0:
        send_first_alert(endpoint, message)
    else:
        timer = threading.Timer(delay, send_first_alert, args=(endpoint, message))
        timer.daemon = True
        timer.start()
    return delay


def send_first_alert(endpoint: str, message: dict) -> str:
    sub = get_db().push_subscriptions.find_one({"endpoint": endpoint})
    if not sub:
        return "gone"  # unfollowed in the meantime
    return send(sub, message["title"], message["body"], message["url"], message["tag"], extra={"test": message["test"]})


def unsubscribe(endpoint: str) -> dict:
    get_db().push_subscriptions.delete_one({"endpoint": endpoint})
    return {"subscribed": False, "areas": []}


def status(endpoint: str) -> dict:
    sub = get_db().push_subscriptions.find_one({"endpoint": endpoint})
    if not sub:
        return {"subscribed": False, "areas": []}
    areas = get_db().areas.find({"_id": {"$in": sub["area_ids"]}}, {"geom": 0})
    return {"subscribed": True, "areas": [public_area(a) for a in areas]}


# ---------------------------------------------------------------- sending
def send(sub: dict, title: str, body: str, url: str, tag: str, extra: dict | None = None) -> str:
    """Push one message. Returns "sent", "gone" (subscription deleted) or "failed"."""
    if not enabled():
        return "failed"
    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag, **(extra or {})})
    try:
        webpush(subscription_info={"endpoint": sub["endpoint"], "keys": sub["keys"]}, data=payload,
                vapid_private_key=settings.vapid_private_key, vapid_claims={"sub": settings.vapid_subject}, ttl=3600)
        return "sent"
    except WebPushException as error:
        code = getattr(error.response, "status_code", None)
        if code in (404, 410):  # the browser unsubscribed or the person cleared site data
            get_db().push_subscriptions.delete_one({"_id": sub["_id"]})
            return "gone"
        get_db().push_subscriptions.update_one({"_id": sub["_id"]}, {"$set": {"last_error": str(error)[:200]}})
        return "failed"
    except Exception as error:  # noqa: BLE001 - a push problem must never stop the alert job
        get_db().push_subscriptions.update_one({"_id": sub["_id"]}, {"$set": {"last_error": str(error)[:200]}})
        return "failed"


def push_for_alert(alert: dict) -> tuple[int, int]:
    """Step 6-8 of the alert job: push to everyone who follows the alert's thana or ward."""
    db = get_db()
    report = db.reports.find_one({"_id": alert["report_id"]}, {"thana_id": 1, "ward_id": 1}) or {}
    area_ids = [i for i in (report.get("thana_id"), report.get("ward_id")) if i]
    if not area_ids or not enabled():
        return 0, 0
    sent = failed = 0
    for sub in db.push_subscriptions.find({"area_ids": {"$in": area_ids}}):
        bangla = sub.get("lang") == "bn"
        result = send(sub, "সেফজোন সতর্কবার্তা" if bangla else "SafeZone alert",
                      alert["text_bn"] if bangla else alert["text_en"], f"/alerts/{alert['_id']}", f"alert-{alert['_id']}")
        target = hashlib.sha256(sub["endpoint"].encode()).hexdigest()[:24]  # never store the address itself twice
        db.alert_deliveries.update_one({"alert_id": alert["_id"], "channel": "web_push", "target": target},
                                       {"$set": {"status": result, "count": 1, "sent_at": datetime.now(timezone.utc)}},
                                       upsert=True)
        if result == "sent":
            sent += 1
        else:
            failed += 1
    return sent, failed


def notify_user(user_id: ObjectId | None, title: str, body: str, url: str = "/me/reports") -> int:
    """FR-18: tell a victim about their own report (on every browser where they allowed notifications)."""
    if not user_id or not enabled():
        return 0
    return sum(send(sub, title, body, url, f"report-{user_id}") == "sent"
               for sub in get_db().push_subscriptions.find({"user_id": user_id}))
