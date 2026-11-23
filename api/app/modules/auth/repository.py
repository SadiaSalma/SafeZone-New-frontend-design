"""
repository.py (auth) - the ONLY place in this module that reads or writes MongoDB.

Keeping database code here keeps service.py readable,
and lets tests check each part separately (design doc, Section 3.3).
"""
from datetime import datetime

from bson import ObjectId
from pymongo import ReturnDocument

from app.db import get_db


def insert_user(user: dict, session=None) -> ObjectId:
    return get_db()["users"].insert_one(user, session=session).inserted_id


def replace_unused_codes(target: str, purpose: str) -> None:
    """A new code makes older, unused codes for the same purpose useless."""
    get_db()["otp_codes"].delete_many({"target": target, "purpose": purpose, "used_at": None})


def find_user_by_phone(phone: str) -> dict | None:
    return get_db()["users"].find_one({"phone": phone})


def find_user_by_id(user_id: ObjectId) -> dict | None:
    return get_db()["users"].find_one({"_id": user_id})


def find_open_code(target: str, purpose: str) -> dict | None:
    """The newest code for this person and purpose that has not been used yet."""
    return get_db()["otp_codes"].find_one({"target": target, "purpose": purpose, "used_at": None},
                                          sort=[("created_at", -1)])


def count_wrong_try(code_id: ObjectId) -> int:
    """Add 1 to the code's wrong-try counter and return the new number."""
    code = get_db()["otp_codes"].find_one_and_update(
        {"_id": code_id}, {"$inc": {"attempts": 1}}, return_document=ReturnDocument.AFTER
    )
    return code["attempts"] if code else 0


def delete_code(code_id: ObjectId) -> None:
    get_db()["otp_codes"].delete_one({"_id": code_id})


def mark_code_used(code_id: ObjectId, now: datetime, session=None) -> None:
    get_db()["otp_codes"].update_one({"_id": code_id}, {"$set": {"used_at": now}}, session=session)


def activate_user(user_id: ObjectId, now: datetime, session=None) -> None:
    get_db()["users"].update_one(
        {"_id": user_id, "status": "pending_verify"},
        {"$set": {"status": "active", "phone_verified_at": now}},
        session=session,
    )


def insert_session(user_id: ObjectId, token_hash: str, expires_at: datetime, user_agent: str,
                   remember: bool = True) -> None:
    """Save the long ticket (only its hash) so it can be checked and cancelled later."""
    get_db()["sessions"].insert_one(
        {"user_id": user_id, "token_hash": token_hash, "expires_at": expires_at,
         "revoked_at": None, "user_agent": user_agent[:300], "remember": remember}
    )


# ---------------------------------------------------------------- sessions (long tickets)
def find_session(token_hash: str) -> dict | None:
    return get_db()["sessions"].find_one({"token_hash": token_hash})


def revoke_session(session_id: ObjectId, now: datetime) -> None:
    get_db()["sessions"].update_one({"_id": session_id, "revoked_at": None}, {"$set": {"revoked_at": now}})


def revoke_all_sessions(user_id: ObjectId, now: datetime) -> int:
    """Log a user out everywhere. Returns how many sessions were cancelled."""
    return get_db()["sessions"].update_many({"user_id": user_id, "revoked_at": None},
                                            {"$set": {"revoked_at": now}}).modified_count


# ---------------------------------------------------------------- wrong-password records (R9)
def add_login_failure(phone: str, ip: str, now: datetime) -> None:
    get_db()["login_attempts"].insert_one({"phone": phone, "ip": ip, "at": now})


def recent_failures(phone: str, since: datetime, ip: str | None = None) -> list[dict]:
    """Wrong passwords for this phone since a time (from one device if ip is given), newest first."""
    query = {"phone": phone, "at": {"$gt": since}}
    if ip is not None:
        query["ip"] = ip
    return list(get_db()["login_attempts"].find(query).sort("at", -1))


def clear_failures(phone: str, ip: str) -> None:
    get_db()["login_attempts"].delete_many({"phone": phone, "ip": ip})


def lock_user(user_id: ObjectId, until: datetime) -> None:
    get_db()["users"].update_one({"_id": user_id}, {"$set": {"locked_until": until}})


def insert_code(target: str, channel: str, purpose: str, code_hash: str, expires_at: datetime, now: datetime) -> None:
    get_db()["otp_codes"].insert_one(
        {
            "target": target,
            "channel": channel,
            "purpose": purpose,
            "code_hash": code_hash,  # only the scrambled code, never the code itself
            "attempts": 0,
            "expires_at": expires_at,  # MongoDB deletes the code automatically after this time
            "used_at": None,
            "created_at": now,
        }
    )


# ---------------------------------------------------------------- password reset (Task 11)
def set_password(user_id: ObjectId, password_hash: str, session=None) -> None:
    """Save a new password hash and lift any account lock."""
    get_db()["users"].update_one(
        {"_id": user_id},
        {"$set": {"password_hash": password_hash, "locked_until": None, "failed_logins": 0}},
        session=session,
    )


def clear_all_failures(phone: str) -> None:
    """Forget every wrong-password record for this phone (from all devices)."""
    get_db()["login_attempts"].delete_many({"phone": phone})
