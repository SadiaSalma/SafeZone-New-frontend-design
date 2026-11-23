"""
service.py (auth) - the real work and the business rules for accounts.

Sign-up steps (FR-1):
  1. Limit: max registrations per hour from one device (R9).
  2. The mobile number must not already be registered.
  3. Save the user with an Argon2 password hash, status "pending_verify",
     and write an audit log entry - both in ONE transaction.
  4. Create a 6-digit code (max 3 per hour per mobile number) and send it to that number by SMS.

Confirm-code steps (Task 8): the code must match, not be expired, and have
fewer than 5 wrong tries. Then the account becomes "active" and the person is
logged in straight away.

Log-in steps (FR-2): phone + password -> two tickets (see security.py).
A wrong phone and a wrong password get the SAME answer (R9), so nobody can
use the log-in form to find out which phone numbers have accounts.
"""
from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError

from app.audit import write_audit
from app.config import settings
from app.db import client
from app.errors import AppError
from app.notify import mask_phone, send_code, send_notice
from app.ratelimit import check_limit
from app.security import (
    code_matches,
    create_access_token,
    hash_code,
    hash_password,
    hash_token,
    new_code,
    new_refresh_token,
    verify_password,
)
from app.modules.auth import repository
from app.modules.auth.schemas import LoginIn, RegisterIn, ResetConfirmIn, VerifyIn

ONE_HOUR = 3600

# Used when the phone number is unknown, so a wrong phone takes as long to check
# as a wrong password (otherwise attackers could tell them apart by timing).
_DUMMY_HASH = hash_password("not-a-real-account-0")


def register(data: RegisterIn, ip: str) -> dict:
    check_limit(f"register:ip:{ip}", settings.registrations_per_hour_per_ip, ONE_HOUR)

    # Is the mobile number already used? Tell the person on that field.
    if repository.find_user_by_phone(data.phone):
        raise _already_registered()

    now = datetime.now(timezone.utc)
    user = {
        "name_en": data.name_en,
        "name_bn": data.name_bn or "",
        "phone": data.phone,
        "phone_verified_at": None,
        "password_hash": hash_password(data.password),  # never the real password
        "role": "victim",
        "status": "pending_verify",
        "failed_logins": 0,
        "locked_until": None,
        "created_at": now,
        "deleted_at": None,
    }

    # Save the user and the audit entry together: both happen, or neither does.
    try:
        with client.start_session() as session:
            with session.start_transaction():
                user_id = repository.insert_user(user, session=session)
                write_audit(
                    "user.register", "users", entity_id=user_id, actor_id=user_id, actor_role="victim",
                    after={"changed": ["name_en", "name_bn", "phone"]},  # R8: names of fields only
                    session=session,
                )
    except DuplicateKeyError:  # someone registered the same number at the same moment
        raise _already_registered()

    demo_code = issue_code(data.phone, "register")
    return {
        "user_id": str(user_id),
        "status": "pending_verify",
        "code_sent_to": mask_phone(data.phone),
        "channel": settings.otp_channel,
        "demo_code": demo_code,
        "message": "Account created. Enter the 6-digit code we sent to your phone by SMS.",
    }


def issue_code(phone: str, purpose: str) -> str | None:
    """Create, save and send a new code by SMS. Returns the code only in demo_screen mode."""
    check_limit(f"code:{purpose}:{phone}", settings.codes_per_hour_per_target, ONE_HOUR)
    return _create_and_send(phone, purpose)


def resend_code(phone: str, purpose: str) -> dict:
    """Send a new code. The answer is the same whether or not the number has an account,
    so nobody can use this to find out who has an account."""
    check_limit(f"code:{purpose}:{phone}", settings.codes_per_hour_per_target, ONE_HOUR)
    user = repository.find_user_by_phone(phone)
    demo_code = None
    if user and user["status"] == "pending_verify":
        demo_code = _create_and_send(phone, purpose)
    return {"message": "If an account is waiting for a code, we have sent a new one.", "demo_code": demo_code}


def verify_code(data: VerifyIn, user_agent: str) -> tuple[dict, dict]:
    """Check the sign-up code. On success: activate the account and log the person in."""
    now = datetime.now(timezone.utc)
    user = repository.find_user_by_phone(data.phone)
    if user and user["status"] == "active":
        raise AppError(409, "already_verified", "This account is already confirmed. Please log in.")

    if not user:
        raise AppError(400, "code_invalid", "This code is wrong or has expired. Ask for a new one.")
    code = _check_code(data.phone, data.code, "register", now)

    # Correct code: mark it used + activate the account + audit, all together.
    with client.start_session() as session:
        with session.start_transaction():
            repository.mark_code_used(code["_id"], now, session=session)
            repository.activate_user(user["_id"], now, session=session)
            write_audit("user.verify", "users", entity_id=user["_id"], actor_id=user["_id"],
                        actor_role=user["role"], session=session)

    user = repository.find_user_by_id(user["_id"])
    return user, _start_session(user, user_agent)


# ---------------------------------------------------------------- forgot password (Task 11, FR-3)
RESET_MESSAGE = "If an account uses this mobile number, we have sent it a code by SMS to reset the password."


def request_password_reset(phone: str) -> dict:
    """Step 1: send a reset code by SMS. The answer is the SAME whether or not the number
    has an account, so nobody can use this page to find out who has an account."""
    check_limit(f"code:reset:{phone}", settings.codes_per_hour_per_target, ONE_HOUR)
    user = repository.find_user_by_phone(phone)
    demo_code = None
    if user and user["status"] == "active":
        demo_code = _create_and_send(phone, "reset")
    return {"message": RESET_MESSAGE, "demo_code": demo_code}


def confirm_password_reset(data: ResetConfirmIn) -> None:
    """Step 2: check the code, save the new password, and log the account out
    everywhere (any old or stolen login stops working)."""
    now = datetime.now(timezone.utc)
    user = repository.find_user_by_phone(data.phone)
    if not user or user["status"] != "active":
        raise AppError(400, "code_invalid", "This code is wrong or has expired. Ask for a new one.")
    code = _check_code(data.phone, data.code, "reset", now)

    with client.start_session() as session:
        with session.start_transaction():
            repository.mark_code_used(code["_id"], now, session=session)
            repository.set_password(user["_id"], hash_password(data.new_password), session=session)
            write_audit("user.password_reset", "users", entity_id=user["_id"], actor_id=user["_id"],
                        actor_role=user["role"], after={"changed": ["password_hash"]}, session=session)

    repository.revoke_all_sessions(user["_id"], now)  # every device must log in again
    repository.clear_all_failures(user["phone"])  # the wrong-password lock starts fresh
    send_notice(user["phone"], "Your password was just changed. If this was not you, contact SafeZone staff.")


def login(data: LoginIn, user_agent: str, ip: str) -> tuple[dict, dict]:
    """Check phone + password and give out the log-in tickets.

    Password-guessing protection (FR-4 + R9):
      - max 20 login tries per minute from one device;
      - 10 wrong passwords for a phone from ONE device in 15 minutes
        -> that phone is locked on that device for 15 minutes
           (the real owner on their own device can still log in);
      - 50 wrong passwords for a phone from ANYWHERE in 1 hour
        -> the whole account is locked and the owner gets a notice.
    """
    check_limit(f"login:ip:{ip}", settings.logins_per_minute_per_ip, 60)
    now = datetime.now(timezone.utc)
    _refuse_if_device_locked(data.phone, ip, now)

    user = repository.find_user_by_phone(data.phone)
    if user and user.get("locked_until") and user["locked_until"] > now:
        minutes = _minutes_until(user["locked_until"], now)
        raise AppError(423, "account_locked",
                       f"This account is locked for safety. Try again in {minutes} minutes.")

    password_ok = verify_password(data.password, user["password_hash"] if user else _DUMMY_HASH)
    if not user or not password_ok:
        repository.add_login_failure(data.phone, ip, now)
        if user:
            _lock_account_if_attacked(user, now)
        raise AppError(401, "wrong_login", "Phone number or password is wrong.")

    repository.clear_failures(data.phone, ip)  # a correct password resets this device's count

    if user["status"] == "pending_verify":
        raise AppError(403, "account_not_verified",
                       "Confirm your account first with the 6-digit code we sent to your phone by SMS.")
    if user["status"] != "active":
        raise AppError(403, "account_unavailable", "This account cannot log in. Contact SafeZone staff.")

    write_audit("user.login", "users", entity_id=user["_id"], actor_id=user["_id"], actor_role=user["role"])
    return user, _start_session(user, user_agent, remember=data.remember)


# If an already-used long ticket comes back within this many seconds, we assume
# two browser tabs refreshed at the same moment (harmless), not a thief.
REUSE_GRACE_SECONDS = 20


def refresh(refresh_token: str | None, user_agent: str) -> tuple[dict, dict]:
    """Swap a long ticket for a NEW pair of tickets. Each long ticket works only once.

    If a long ticket that was already swapped is used again, someone may have
    stolen it: we log that account out everywhere (called "reuse detection").
    """
    now = datetime.now(timezone.utc)
    session = repository.find_session(hash_token(refresh_token)) if refresh_token else None
    if not session or session["expires_at"] <= now:
        raise AppError(401, "not_logged_in", "Please log in again.")

    if session.get("revoked_at"):
        if (now - session["revoked_at"]).total_seconds() > REUSE_GRACE_SECONDS:
            repository.revoke_all_sessions(session["user_id"], now)
            write_audit("session.reuse_detected", "sessions", entity_id=session["user_id"], actor_role="system")
        raise AppError(401, "not_logged_in", "Please log in again.")

    user = repository.find_user_by_id(session["user_id"])
    if not user or user["status"] != "active":
        raise AppError(401, "not_logged_in", "Please log in again.")

    repository.revoke_session(session["_id"], now)  # the old long ticket is now used up
    return user, _start_session(user, user_agent, remember=session.get("remember", True))


def logout(refresh_token: str | None) -> None:
    """Cancel this browser's long ticket (if any). Always succeeds."""
    if refresh_token:
        session = repository.find_session(hash_token(refresh_token))
        if session:
            repository.revoke_session(session["_id"], datetime.now(timezone.utc))


def public_user(user: dict) -> dict:
    """Only the fields the website may see (never the password hash)."""
    return {
        "id": str(user["_id"]),
        "name_en": user["name_en"],
        "name_bn": user.get("name_bn", ""),
        "phone": user["phone"],
        "role": user["role"],
        "status": user["status"],
        "nid_added": bool(user.get("nid_hash")),
        "nid_last4": user.get("nid_last4"),
    }


# ---------------------------------------------------------------- helpers
def _check_code(phone: str, typed: str, purpose: str, now: datetime) -> dict:
    """Shared by sign-up, password reset and "delete my data": the newest unused code for this
    mobile number must exist, not be expired, and match. After 5 wrong tries the code is thrown away."""
    code = repository.find_open_code(phone, purpose)
    if not code or code["expires_at"] <= now:
        raise AppError(400, "code_invalid", "This code is wrong or has expired. Ask for a new one.")

    if not code_matches(typed, phone, purpose, code["code_hash"]):
        tries = repository.count_wrong_try(code["_id"])
        left = settings.max_code_attempts - tries
        if left <= 0:
            repository.delete_code(code["_id"])  # too many guesses: this code is finished
            raise AppError(400, "code_invalid", "Too many wrong tries. Ask for a new code.")
        raise AppError(400, "wrong_code", f"Wrong code. {left} tries left.",
                       {"code": f"Wrong code. {left} tries left."})
    return code


def _minutes_until(moment: datetime, now: datetime) -> int:
    return max(1, int((moment - now).total_seconds() // 60) + 1)


def _refuse_if_device_locked(phone: str, ip: str, now: datetime) -> None:
    """10 wrong passwords from this device in 15 minutes -> wait 15 minutes."""
    window_start = now - timedelta(minutes=settings.device_lock_window_minutes)
    failures = repository.recent_failures(phone, window_start, ip=ip)
    if len(failures) >= settings.device_lock_after:
        unlock_at = failures[0]["at"] + timedelta(minutes=settings.device_lock_minutes)
        if unlock_at > now:
            raise AppError(429, "too_many_wrong_logins",
                           f"Too many wrong passwords from this device. Try again in "
                           f"{_minutes_until(unlock_at, now)} minutes.")


def _lock_account_if_attacked(user: dict, now: datetime) -> None:
    """Many wrong passwords from anywhere -> lock the whole account and tell the owner."""
    failures = repository.recent_failures(user["phone"], now - timedelta(hours=1))
    if len(failures) >= settings.account_lock_after:
        until = now + timedelta(minutes=settings.account_lock_minutes)
        repository.lock_user(user["_id"], until)
        repository.revoke_all_sessions(user["_id"], now)
        write_audit("user.lock", "users", entity_id=user["_id"], actor_role="system",
                    after={"changed": ["locked_until"]})
        send_notice(user["phone"], f"Someone tried many wrong passwords on your account. It is locked for "
                                   f"{settings.account_lock_minutes} minutes. If this was not you, change your password.")


def _start_session(user: dict, user_agent: str, remember: bool = True) -> dict:
    """Create the two log-in tickets. Only a hash of the long ticket is saved."""
    refresh = new_refresh_token()
    repository.insert_session(
        user["_id"],
        hash_token(refresh),
        datetime.now(timezone.utc) + timedelta(days=settings.refresh_days),
        user_agent,
        remember,
    )
    return {"access": create_access_token(str(user["_id"]), user["role"]), "refresh": refresh,
            "remember": remember}


def _create_and_send(phone: str, purpose: str) -> str | None:
    """Save a new code and send it to the mobile number. Returns the code only in demo_screen mode."""
    now = datetime.now(timezone.utc)
    code = new_code()
    repository.replace_unused_codes(phone, purpose)
    repository.insert_code(
        target=phone,
        channel=settings.otp_channel,
        purpose=purpose,
        code_hash=hash_code(code, phone, purpose),  # only a scrambled copy is saved
        expires_at=now + timedelta(minutes=settings.otp_minutes),
        now=now,
    )
    send_code(phone, code, purpose)
    return code if settings.otp_channel == "demo_screen" else None


def _already_registered() -> AppError:
    return AppError(409, "already_registered", "An account with this mobile number already exists. Try logging in.",
                    {"phone": "This phone number is already registered."})
