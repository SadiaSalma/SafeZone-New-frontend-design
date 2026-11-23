"""
service.py (users) - "my account" rules.

NID (national ID) number, as decided for SafeZone:
  - Only the FORMAT is checked (10, 13 or 17 digits). Real checks with the
    Election Commission need a government agreement and cost money, so they
    are out of scope for a free student project (NFR-6).
  - One NID can belong to only ONE account.
  - The NID is stored scrambled (nid_hash) + its last 4 digits for display.
  - It is required before a person's FIRST theft report (checked in the report task).
"""
from datetime import datetime, timezone

from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from app.audit import write_audit
from app.config import settings
from app.db import get_db
from app.errors import AppError
from app.modules.auth.schemas import RegisterIn
from app.ratelimit import check_limit
from app.security import hash_nid, hash_password


def add_nid(user: dict, nid: str) -> dict:
    """Link an NID number to the logged-in user. Returns the updated user."""
    check_limit(f"nid:{user['_id']}", settings.nid_tries_per_hour, 3600)
    if user.get("nid_hash"):
        raise AppError(409, "nid_already_added", "Your account already has an NID. Contact staff to change it.")

    users = get_db()["users"]
    try:
        users.update_one(
            {"_id": user["_id"]},
            {"$set": {"nid_hash": hash_nid(nid), "nid_last4": nid[-4:],
                      "nid_added_at": datetime.now(timezone.utc)}},
        )
    except DuplicateKeyError:
        raise AppError(409, "nid_in_use", "This NID is already linked to another account.",
                       {"nid": "This NID is already linked to another account."})

    write_audit("user.nid_add", "users", entity_id=user["_id"], actor_id=user["_id"],
                actor_role=user["role"], after={"changed": ["nid"]})  # R8: never the number itself
    return users.find_one({"_id": user["_id"]})


def has_nid(user: dict) -> bool:
    """Used by the report task: a person must add an NID before the first report."""
    return bool(user.get("nid_hash"))


# ---------------------------------------------------------------- staff accounts (Task 11)
STAFF_ROLES = ("verifier", "admin")


def create_staff_user(name_en: str, phone: str, password: str, role: str = "admin") -> dict:
    """Create a ready-to-use staff account (verifier or admin).

    Staff cannot sign up on the website, so the first admin is made with
    scripts/create_admin.py, which calls this. The same rules as sign-up apply
    (phone format, password strength); the account starts "active".
    """
    if role not in STAFF_ROLES:
        raise AppError(422, "invalid_role", "Role must be 'verifier' or 'admin'.")
    try:
        checked = RegisterIn(name_en=name_en, phone=phone, password=password)
    except ValidationError as error:
        problems = {str(p["loc"][-1]): p["msg"].removeprefix("Value error, ") for p in error.errors()}
        raise AppError(422, "invalid_input", "Some details are not valid.", problems)

    now = datetime.now(timezone.utc)
    user = {
        "name_en": checked.name_en, "name_bn": "", "phone": checked.phone,
        "phone_verified_at": now, "password_hash": hash_password(checked.password),
        "role": role, "status": "active", "failed_logins": 0, "locked_until": None,
        "created_at": now, "deleted_at": None,
    }
    try:
        user["_id"] = get_db()["users"].insert_one(user).inserted_id
    except DuplicateKeyError:
        raise AppError(409, "already_registered", "An account with this phone number already exists.")

    write_audit("user.create_staff", "users", entity_id=user["_id"], actor_role="system",
                after={"changed": ["role"], "role": role})
    return user
