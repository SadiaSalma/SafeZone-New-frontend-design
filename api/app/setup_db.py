"""
setup_db.py - applies schema.py to a database.

For each collection in schema.py it:
  1. creates the collection if it is missing, with its rules (validator), or
     updates the rules if the collection already exists;
  2. creates every index (if an index with the same name exists but is
     different, it is replaced).

  3. removes what is no longer used (RETIRED_INDEXES, and the old email fields: codes now go to
     the mobile number, so accounts have no email any more).

It is SAFE TO RUN AGAIN: things that are already correct are left alone.
Used by scripts/init_db.py and by the tests.
"""
from pymongo.database import Database
from pymongo.errors import OperationFailure

from app.schema import COLLECTIONS, RETIRED_INDEXES

# MongoDB error codes meaning "an index with this name/keys exists but is different"
INDEX_CONFLICT_CODES = {85, 86}


def apply_schema(db: Database) -> dict:
    """Create/update all collections and indexes. Returns a small summary."""
    summary = {"created": [], "updated": [], "indexes": 0}
    existing = set(db.list_collection_names())

    for name, spec in COLLECTIONS.items():
        # 1) The collection and its rules
        if name in existing:
            db.command("collMod", name, validator=spec["validator"], validationLevel="strict")
            summary["updated"].append(name)
        else:
            db.create_collection(name, validator=spec["validator"], validationLevel="strict")
            summary["created"].append(name)

        # 2) Its indexes
        for keys, options in spec["indexes"]:
            key_list = list(keys.items())
            try:
                db[name].create_index(key_list, **options)
            except OperationFailure as error:
                if error.code not in INDEX_CONFLICT_CODES:
                    raise
                db[name].drop_index(options["name"])  # replace the old version
                db[name].create_index(key_list, **options)
            summary["indexes"] += 1

    _remove_retired(db)
    return summary


def _remove_retired(db: Database) -> None:
    """Clean an older database: drop retired indexes and the email fields of accounts."""
    for name, indexes in RETIRED_INDEXES.items():
        present = set(db[name].index_information())
        for index in indexes:
            if index in present:
                db[name].drop_index(index)
    # Accounts made when codes were emailed: keep when they were confirmed, forget the email address
    db.users.update_many({"$or": [{"email": {"$exists": True}}, {"email_verified_at": {"$exists": True}}]}, [
        {"$set": {"phone_verified_at": {"$ifNull": ["$phone_verified_at", "$email_verified_at"]}}},
        {"$unset": ["email", "email_verified_at"]},
    ])
    db.otp_codes.delete_many({"channel": "email"})  # old emailed codes (they expire in minutes anyway)
    db.otp_codes.delete_many({"target": {"$regex": "@"}})
