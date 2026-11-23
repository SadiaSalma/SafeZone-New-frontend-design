"""
notify.py - delivers one-time codes and short notices to people's MOBILE NUMBER by SMS.

Three channels, chosen with OTP_CHANNEL in .env:
  demo_screen  - free, for development and the teacher demo: the code is shown on the website
                 in a "Demo SMS" box (and printed in the backend window). No SMS is sent.
  console      - free, development only: the code is printed in the backend window only
  sms          - a real SMS through BulkSMSBD (a Bangladeshi SMS company, about 0.25-0.35 Tk per SMS).
                 Needs SMS_API_KEY and SMS_SENDER_ID in .env.
demo_screen and console are refused outside development, so a real server can never show codes.
"""
import json
import urllib.parse
import urllib.request

from app.config import settings
from app.errors import AppError

PURPOSE_TEXT = {
    "register": "confirm your SafeZone account",
    "reset": "reset your SafeZone password",
    "delete": "delete your SafeZone data",
}

# BulkSMSBD answers 202 when the SMS was accepted
SMS_ACCEPTED = 202


def mask_phone(phone: str) -> str:
    """'+8801712345678' -> '017*****678' (so screens don't show the full number)."""
    local = phone.removeprefix("+88")
    if len(local) != 11:
        return "***"
    return f"{local[:3]}*****{local[-3:]}"


def code_text(code: str, purpose: str) -> str:
    """The SMS itself: short (one SMS is 160 letters) and it says what the code is for."""
    why = PURPOSE_TEXT.get(purpose, "use SafeZone")
    return f"SafeZone code: {code}. Use it to {why}. Valid {settings.otp_minutes} min. Never share it."


def send_code(phone: str, code: str, purpose: str) -> None:
    """Deliver a code to a mobile number using the configured channel."""
    channel = settings.otp_channel
    if channel in ("console", "demo_screen"):
        if settings.app_env != "development":
            # R1: these channels must never be used on a real server
            raise AppError(500, "otp_channel_not_allowed", "Codes cannot be delivered right now.")
        print(f"\n[SafeZone SMS] to {mask_phone(phone)}: {code_text(code, purpose)}\n", flush=True)
        return
    if channel == "sms":
        _send_sms(phone, code_text(code, purpose))
        return
    raise AppError(500, "otp_channel_unknown", "Codes cannot be delivered right now.")


def send_notice(phone: str, text: str) -> None:
    """A short security message to the account owner (e.g. 'your account was locked').
    Uses the same channel as codes. A notice that fails to send never breaks the request."""
    if not phone or phone.startswith("deleted:"):
        return
    message = f"SafeZone: {text}"
    if settings.otp_channel == "sms":
        try:
            _send_sms(phone, message)
        except AppError:
            pass
        return
    print(f"\n[SafeZone SMS] to {mask_phone(phone)}: {message}\n", flush=True)


def _send_sms(phone: str, message: str) -> None:
    """Send one SMS with BulkSMSBD's web API (https://bulksmsbd.net)."""
    if not (settings.sms_api_key and settings.sms_sender_id):
        raise AppError(500, "sms_not_configured", "SMS is not set up on the server yet.")
    form = urllib.parse.urlencode({
        "api_key": settings.sms_api_key,
        "senderid": settings.sms_sender_id,
        "number": phone.removeprefix("+"),  # 8801XXXXXXXXX
        "message": message,
    }).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(settings.sms_api_url, data=form), timeout=15) as answer:
            result = json.loads(answer.read().decode() or "{}")
    except (OSError, ValueError) as error:
        raise AppError(502, "sms_failed", "We could not send the SMS. Please try again.") from error
    if result.get("response_code") != SMS_ACCEPTED:
        raise AppError(502, "sms_failed", "We could not send the SMS. Please try again.")
