"""
ratelimit.py - stops people from doing something too many times (Design Revisions R9).

Example: at most 3 codes per hour for one mobile number.

How it works: a counter document per "key" in the rate_counters collection,
e.g. {"key": "code:register:+8801712345678", "count": 2, "expires_at": ...}.
Each try adds 1. When the time window ends, the counter starts again from 0.
"""
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.db import get_db
from app.errors import AppError


def check_limit(key: str, limit: int, window_seconds: int) -> None:
    """Count one try for `key`. Raise a 429 error if there were too many in the window."""
    counters = get_db()["rate_counters"]
    now = datetime.now(timezone.utc)

    # A finished window starts again (MongoDB also deletes old counters by itself, within a minute)
    counters.delete_many({"key": key, "expires_at": {"$lte": now}})

    try:
        counter = counters.find_one_and_update(
            {"key": key},
            {"$inc": {"count": 1}, "$setOnInsert": {"expires_at": now + timedelta(seconds=window_seconds)}},
            upsert=True,  # create the counter if it doesn't exist yet
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:  # two requests created it at the same moment: just count again
        counter = counters.find_one_and_update({"key": key}, {"$inc": {"count": 1}}, return_document=ReturnDocument.AFTER)

    if counter["count"] > limit:
        wait = max(1, int((counter["expires_at"] - now).total_seconds() // 60) + 1)
        raise AppError(429, "too_many_requests", f"Too many tries. Please wait about {wait} minutes and try again.")
