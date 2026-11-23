"""
schema.py - the "shelves and labels" of the SafeZone database.

For every collection (like a table) we write down:
  validator - rules MongoDB itself checks on every save (required fields, allowed values)
  indexes   - fast lookups and "no duplicates" rules

scripts/init_db.py reads this file and applies it to the database.
Source: design doc Section 4.2 + the Design Revisions (R1, R2, R3, R5, R7, R9).

Index option words:
  unique                   - no two documents may have the same value
  partialFilterExpression  - the rule only applies to documents that match a filter
  expireAfterSeconds=0     - MongoDB deletes the document automatically at the time stored in that field (TTL)
  "2dsphere"               - a map index, for questions like "which area is this point in?"
"""

# ---------- Small helpers so the rules below stay short and readable ----------
STRING = {"bsonType": "string"}
DATE = {"bsonType": "date"}
BOOL = {"bsonType": "bool"}
ID = {"bsonType": "objectId"}
ID_OR_NULL = {"bsonType": ["objectId", "null"]}
DATE_OR_NULL = {"bsonType": ["date", "null"]}
WHOLE_NUMBER = {"bsonType": ["int", "long"]}
NUMBER = {"bsonType": ["int", "long", "double", "decimal"]}
OBJECT = {"bsonType": "object"}
ARRAY = {"bsonType": "array"}

# A map point, GeoJSON style: {"type": "Point", "coordinates": [longitude, latitude]}
POINT = {
    "bsonType": "object",
    "required": ["type", "coordinates"],
    "properties": {"type": {"enum": ["Point"]}, "coordinates": {"bsonType": "array", "minItems": 2, "maxItems": 2}},
}
POINT_OR_NULL = {"oneOf": [POINT, {"bsonType": "null"}]}

# An area shape (a thana or a ward)
SHAPE = {
    "bsonType": "object",
    "required": ["type", "coordinates"],
    "properties": {"type": {"enum": ["Polygon", "MultiPolygon"]}, "coordinates": ARRAY},
}


def one_of(*values):
    """Only these exact values are allowed."""
    return {"enum": list(values)}


def rules(required: list[str], properties: dict) -> dict:
    """Build a MongoDB validator from required fields + field rules."""
    return {"$jsonSchema": {"bsonType": "object", "required": required, "properties": properties}}


# Report statuses (Design Revisions R7: SUBMITTED removed, reports start in PENDING_REVIEW)
REPORT_STATUSES = ("PENDING_REVIEW", "NEEDS_INFO", "VERIFIED", "REJECTED", "WITHDRAWN", "ALERTED", "ALERT_FAILED")

# The 10 theft types (design doc FR-8)
THEFT_TYPES = (
    "phone_snatching", "bag_snatching", "pickpocket", "motorbike_theft", "bicycle_theft",
    "car_theft", "cng_theft", "burglary", "shop_theft", "other",
)

# ---------- The collections ----------
COLLECTIONS: dict[str, dict] = {
    # ===== Accounts =====
    "users": {
        "validator": rules(
            ["name_en", "phone", "email", "password_hash", "role", "status", "created_at"],
            {
                "name_en": STRING,
                "name_bn": STRING,
                "phone": {"bsonType": "string", "pattern": r"^(\+8801\d{9}|deleted:.+)$"},  # +8801XXXXXXXXX
                "email": STRING,  # R1: codes are sent by email
                "email_verified_at": DATE_OR_NULL,
                "password_hash": STRING,  # Argon2 hash, never the real password
                "role": one_of("victim", "verifier", "admin"),
                "status": one_of("pending_verify", "active", "suspended", "deleted"),
                "failed_logins": WHOLE_NUMBER,
                "locked_until": DATE_OR_NULL,
                "created_at": DATE,
                "deleted_at": DATE_OR_NULL,
                # NID (added before the first report): only a scrambled copy + the last 4 digits
                "nid_hash": STRING,
                "nid_last4": {"bsonType": "string", "pattern": r"^\d{4}$"},
                "nid_added_at": DATE_OR_NULL,
            },
        ),
        "indexes": [
            ({"phone": 1}, {"unique": True, "name": "phone_unique"}),
            ({"email": 1}, {"unique": True, "name": "email_unique"}),
            # One NID = one account (only for users who have added an NID)
            ({"nid_hash": 1}, {"unique": True, "partialFilterExpression": {"nid_hash": {"$type": "string"}},
                               "name": "one_account_per_nid"}),
        ],
    },
    "otp_codes": {
        "validator": rules(
            ["target", "channel", "purpose", "code_hash", "attempts", "expires_at"],
            {
                "target": STRING,  # the email address (or phone) the code was sent to
                "channel": one_of("console", "email", "demo_screen"),  # R1
                "purpose": one_of("register", "reset", "delete"),
                "code_hash": STRING,
                "attempts": WHOLE_NUMBER,
                "expires_at": DATE,
                "used_at": DATE_OR_NULL,
                "created_at": DATE,
            },
        ),
        "indexes": [
            ({"expires_at": 1}, {"expireAfterSeconds": 0, "name": "delete_when_expired"}),
            ({"target": 1, "purpose": 1}, {"name": "target_purpose"}),
        ],
    },
    "sessions": {
        "validator": rules(
            ["user_id", "token_hash", "expires_at"],
            {"user_id": ID, "token_hash": STRING, "expires_at": DATE, "revoked_at": DATE_OR_NULL, "user_agent": STRING,
             "remember": BOOL},
        ),
        "indexes": [
            ({"token_hash": 1}, {"unique": True, "name": "token_unique"}),
            ({"expires_at": 1}, {"expireAfterSeconds": 0, "name": "delete_when_expired"}),
            ({"user_id": 1}, {"name": "by_user"}),
        ],
    },
    "login_attempts": {  # R9: lockout counted per (phone, IP address)
        "validator": rules(["phone", "ip", "at"], {"phone": STRING, "ip": STRING, "at": DATE}),
        "indexes": [
            ({"phone": 1, "ip": 1, "at": -1}, {"name": "phone_ip_time"}),
            ({"at": 1}, {"expireAfterSeconds": 3600, "name": "delete_after_1_hour"}),
        ],
    },
    "rate_counters": {  # R9: simple request limits, stored in MongoDB
        "validator": rules(["key", "count", "expires_at"], {"key": STRING, "count": WHOLE_NUMBER, "expires_at": DATE}),
        "indexes": [
            ({"key": 1}, {"unique": True, "name": "key_unique"}),
            ({"expires_at": 1}, {"expireAfterSeconds": 0, "name": "delete_when_expired"}),
        ],
    },
    # ===== Places =====
    "areas": {  # thanas and wards (R3: two independent layers)
        "validator": rules(
            ["code", "name_en", "type", "geom", "is_active"],
            {
                "code": STRING,  # e.g. "mirpur", "dncc-w06"
                "name_en": STRING,
                "name_bn": STRING,
                "type": one_of("thana", "ward"),
                "thana_ids": ARRAY,  # R3: for a ward, every thana it overlaps
                "geom": SHAPE,
                "size_km2": NUMBER,
                "alert_radius_m": WHOLE_NUMBER,
                "is_active": BOOL,
                "source": STRING,  # R3: where the shape came from
                "source_date": STRING,
            },
        ),
        "indexes": [
            ({"code": 1}, {"unique": True, "name": "code_unique"}),
            ({"geom": "2dsphere"}, {"name": "geom_map"}),
            ({"type": 1}, {"name": "by_type"}),
        ],
    },
    "police_stations": {
        "validator": rules(
            ["code", "name_en", "location", "is_active"],
            {"code": STRING, "name_en": STRING, "name_bn": STRING, "thana_id": ID_OR_NULL, "location": POINT,
             "address": STRING, "phone": STRING, "is_active": BOOL},
        ),
        "indexes": [
            ({"code": 1}, {"unique": True, "name": "code_unique"}),
            ({"location": "2dsphere"}, {"name": "location_map"}),
        ],
    },
    "gd_formats": {
        "validator": rules(["regex", "is_active"], {"regex": STRING, "example": STRING, "is_active": BOOL}),
        "indexes": [],
    },
    # ===== Reports =====
    "reports": {
        "validator": rules(
            ["status", "theft_type", "occurred_at", "submitted_at", "location", "gd", "gd_hash", "gd_active"],
            {
                "user_id": ID_OR_NULL,  # null after the victim deletes their data
                "status": one_of(*REPORT_STATUSES),
                "theft_type": one_of(*THEFT_TYPES),
                "occurred_at": DATE,
                "submitted_at": DATE,
                "location": POINT,  # exact place: private (victim + staff only)
                "public_location": POINT_OR_NULL,  # moved 100-200 m, set at approval
                "thana_id": ID_OR_NULL,
                "ward_id": ID_OR_NULL,
                "landmark": STRING,
                "description": STRING,
                "stolen_items": STRING,
                "gd": {
                    "bsonType": "object",
                    "required": ["type", "number", "date"],
                    "properties": {"type": one_of("GD", "FIR"), "number": STRING, "date": DATE,
                                   "police_station_id": ID_OR_NULL},
                },
                "gd_hash": STRING,
                "gd_active": BOOL,  # R2: true while the report still "holds" its GD
                "checks": ARRAY,
                "risk": OBJECT,
                "alert_text": OBJECT,
                "claim": OBJECT,
                "info_request": STRING,  # R7
                "needs_info_until": DATE_OR_NULL,  # R7
                "gd_scan_id": ID_OR_NULL,
                "anonymized_at": DATE_OR_NULL,
                "is_demo": BOOL,
            },
        ),
        "indexes": [
            # R2: a GD may be on only ONE active report (rejected/withdrawn ones free it)
            ({"gd_hash": 1}, {"unique": True, "partialFilterExpression": {"gd_active": True},
                              "name": "one_active_report_per_gd"}),
            ({"status": 1, "submitted_at": 1}, {"name": "review_queue_oldest_first"}),
            ({"user_id": 1, "submitted_at": -1}, {"name": "my_reports"}),
            ({"location": "2dsphere"}, {"name": "location_map"}),
            ({"public_location": "2dsphere"}, {"name": "public_location_map"}),
        ],
    },
    "report_photos": {
        "validator": rules(
            ["report_id", "storage_key", "size_bytes", "created_at"],
            {"user_id": ID_OR_NULL, "report_id": ID, "storage_key": STRING, "size_bytes": WHOLE_NUMBER, "created_at": DATE,
             "kind": one_of("item", "gd_copy"),  # Task 16: a photo of a stolen item, or of the GD copy
             "width": WHOLE_NUMBER, "height": WHOLE_NUMBER},
        ),
        "indexes": [({"report_id": 1}, {"name": "by_report"})],
    },
    "gd_scans": {
        "validator": rules(
            ["status", "storage_key"],
            {"user_id": ID_OR_NULL, "report_id": ID_OR_NULL, "status": one_of("processing", "done", "failed"),
             "storage_key": STRING, "raw_text": STRING, "fields": OBJECT, "confidence": NUMBER, "seconds": NUMBER,
             "delete_after": DATE_OR_NULL},
        ),
        "indexes": [({"delete_after": 1}, {"name": "cleanup_queue"})],
    },
    "decisions": {  # append-only: decisions are never changed afterwards
        "validator": rules(
            ["report_id", "verifier_id", "decision", "created_at"],
            {"report_id": ID, "verifier_id": ID, "decision": one_of("approve", "reject", "ask_info"),
             "reason": STRING, "note": STRING, "created_at": DATE},
        ),
        "indexes": [({"report_id": 1, "created_at": 1}, {"name": "by_report"})],
    },
    # ===== Alerts and the simulated phone network =====
    "alerts": {
        "validator": rules(
            ["report_id", "text_en", "text_bn", "center", "radius_m", "status", "queued_at"],
            {
                "report_id": ID,
                "area_id": ID_OR_NULL,
                "text_en": STRING,
                "text_bn": STRING,
                "center": POINT,
                "radius_m": WHOLE_NUMBER,
                "status": one_of("queued", "sending", "sent", "failed"),  # R5 adds "sending"
                "towers": WHOLE_NUMBER, "phones": WHOLE_NUMBER, "push_sent": WHOLE_NUMBER, "push_failed": WHOLE_NUMBER,
                "queued_at": DATE, "sent_at": DATE_OR_NULL, "seconds_to_send": NUMBER,
                "attempts": WHOLE_NUMBER, "lease_until": DATE_OR_NULL, "last_error": STRING,  # R5
            },
        ),
        "indexes": [
            ({"report_id": 1}, {"unique": True, "name": "one_alert_per_report"}),  # NFR-1
            ({"status": 1, "lease_until": 1}, {"name": "sending_queue"}),  # R5
            ({"center": "2dsphere"}, {"name": "center_map"}),
        ],
    },
    "alert_deliveries": {
        "validator": rules(
            ["alert_id", "channel", "target", "status"],
            {"alert_id": ID, "channel": one_of("sim_broadcast", "web_push"), "target": STRING,
             "count": WHOLE_NUMBER, "status": STRING, "error": STRING, "sent_at": DATE_OR_NULL},
        ),
        "indexes": [({"alert_id": 1, "channel": 1, "target": 1}, {"unique": True, "name": "one_per_target"})],  # R5
    },
    "cell_towers": {
        "validator": rules(["code", "location", "range_m"], {"code": STRING, "location": POINT, "range_m": WHOLE_NUMBER}),
        "indexes": [
            ({"code": 1}, {"unique": True, "name": "code_unique"}),
            ({"location": "2dsphere"}, {"name": "location_map"}),
        ],
    },
    "virtual_phones": {
        "validator": rules(
            ["location", "tower_id", "is_test"],
            {"location": POINT, "tower_id": ID, "is_test": BOOL, "owner_id": ID_OR_NULL, "label": STRING},
        ),
        "indexes": [
            ({"location": "2dsphere"}, {"name": "location_map"}),
            ({"tower_id": 1}, {"name": "by_tower"}),
            ({"owner_id": 1}, {"name": "test_phones_by_owner", "partialFilterExpression": {"is_test": True}}),
        ],
    },
    "virtual_inbox": {
        "validator": rules(["phone_id", "alert_id", "received_at"], {"phone_id": ID, "alert_id": ID, "received_at": DATE}),
        "indexes": [({"phone_id": 1, "alert_id": 1}, {"unique": True, "name": "one_copy_per_phone"})],  # R5
    },
    "push_subscriptions": {
        "validator": rules(
            ["endpoint", "keys", "area_ids", "created_at"],
            {"endpoint": STRING, "keys": OBJECT, "area_ids": ARRAY, "user_id": ID_OR_NULL, "created_at": DATE,
             "last_error": STRING},
        ),
        "indexes": [
            ({"endpoint": 1}, {"unique": True, "name": "endpoint_unique"}),
            ({"area_ids": 1}, {"name": "followers_of_area"}),
        ],
    },
    # ===== Crime statistics =====
    "crime_categories": {
        "validator": rules(
            ["key", "name_en", "weight", "is_active", "order"],
            {"key": STRING, "name_en": STRING, "name_bn": STRING, "weight": NUMBER, "is_active": BOOL,
             "order": WHOLE_NUMBER},
        ),
        "indexes": [({"key": 1}, {"unique": True, "name": "key_unique"})],
    },
    "crime_stats": {
        "validator": rules(
            ["area_id", "category_id", "month", "count", "source"],
            {"area_id": ID, "category_id": ID, "month": DATE, "count": WHOLE_NUMBER, "source": STRING,
             "note": STRING, "updated_by": ID_OR_NULL, "updated_at": DATE},
        ),
        "indexes": [({"area_id": 1, "category_id": 1, "month": 1}, {"unique": True, "name": "one_figure_per_cell"})],
    },
    # ===== Admin =====
    "settings": {
        "validator": rules(["key"], {"key": STRING, "updated_by": ID_OR_NULL, "updated_at": DATE}),
        "indexes": [({"key": 1}, {"unique": True, "name": "key_unique"})],
    },
    "audit_logs": {  # append-only: an unchangeable record of important actions
        "validator": rules(
            ["action", "entity", "created_at"],
            {"actor_id": ID_OR_NULL, "actor_role": STRING, "action": STRING, "entity": STRING,
             "entity_id": ID_OR_NULL, "before": OBJECT, "after": OBJECT, "created_at": DATE},
        ),
        "indexes": [
            ({"created_at": -1}, {"name": "newest_first"}),
            ({"entity": 1, "entity_id": 1}, {"name": "by_entity"}),
        ],
    },
}
