"""
settings_store.py - settings that ADMINS can change while SafeZone runs (stored in the "settings" collection).

The .env file (config.py) holds things only the developer changes (secrets, ports).
This file holds things an admin may tune later in the admin pages (Task 30), for example
how many risk points each warning is worth (FR-13: "points are admin settings").

Every setting has a default here, so SafeZone works before any admin touches anything.
"""
from datetime import datetime, timezone

from app.db import get_db

DEFAULTS: dict[str, dict] = {
    # Task 17: risk points per warning (the score is capped at 100)
    "risk_points": {
        "gd_format": 20,  # the GD number doesn't look like a known format
        "gd_timing": 15,  # the GD was filed long after the theft
        "place_in_gd_thana": 20,  # the theft place is outside the GD police station's thana
        "nearby_duplicate": 20,  # another report very close in place and time
        "history": 15,  # per rejected report in the last 90 days (counted up to 2)
        "gd_copy": 10,  # no photo of the GD copy
        "ocr_mismatch": 15,  # Task 29: the GD photo shows a different number/date/station than the form
    },
    # Task 17: score -> level
    "risk_levels": {"medium_from": 30, "high_from": 60},
}


def get_setting(key: str) -> dict:
    """The current value (admin's saved value merged over the default)."""
    saved = get_db().settings.find_one({"key": key}) or {}
    value = dict(DEFAULTS.get(key, {}))
    value.update(saved.get("value", {}))
    return value


def save_setting(key: str, value: dict, user_id=None) -> dict:
    get_db().settings.update_one(
        {"key": key},
        {"$set": {"key": key, "value": value, "updated_by": user_id, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return get_setting(key)
