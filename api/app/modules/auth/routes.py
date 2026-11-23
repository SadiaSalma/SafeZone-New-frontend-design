"""
routes.py (auth) - the web addresses for accounts.

Each function here is small: it receives the request, calls service.py,
and returns the answer. The real work happens in service.py.
"""
from fastapi import APIRouter, Request, Response

from app.deps import REFRESH_COOKIE, clear_login_cookies, set_login_cookies
from app.modules.auth import service
from app.modules.auth.schemas import (
    LoginIn,
    LoginOut,
    MessageOut,
    RegisterIn,
    RegisterOut,
    ResendIn,
    ResetConfirmIn,
    ResetRequestIn,
    VerifyIn,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Accounts"])


def client_ip(request: Request) -> str:
    """The visitor's IP address (used for spam limits)."""
    return request.client.host if request.client else "unknown"


@router.post("/register", response_model=RegisterOut, status_code=201, summary="Sign up")
def register(data: RegisterIn, request: Request):
    """Create an account (status pending_verify) and send a 6-digit code to the mobile number by SMS."""
    return service.register(data, client_ip(request))


@router.post("/resend-otp", response_model=MessageOut, summary="Send the code again")
def resend_otp(data: ResendIn):
    """Send a new code. Max 3 codes per hour for one mobile number."""
    return service.resend_code(data.phone, data.purpose)


@router.post("/verify-otp", response_model=LoginOut, summary="Confirm the code")
def verify_otp(data: VerifyIn, request: Request, response: Response):
    """Check the 6-digit code. The account becomes active and the person is logged in."""
    user, tickets = service.verify_code(data, request.headers.get("user-agent", ""))
    set_login_cookies(response, tickets)
    return {"user": service.public_user(user), "message": "Account confirmed. Welcome to SafeZone!"}


@router.post("/login", response_model=LoginOut, summary="Log in")
def login(data: LoginIn, request: Request, response: Response):
    """Log in with phone number and password. The tickets arrive as secure cookies."""
    user, tickets = service.login(data, request.headers.get("user-agent", ""), client_ip(request))
    set_login_cookies(response, tickets, remember=tickets["remember"])
    return {"user": service.public_user(user), "message": "Logged in."}


@router.post("/refresh", response_model=LoginOut, summary="Get new tickets")
def refresh(request: Request, response: Response):
    """Swap the long ticket (cookie) for a new pair. The website calls this when the
    15-minute ticket runs out, so people stay logged in for up to 7 days."""
    user, tickets = service.refresh(request.cookies.get(REFRESH_COOKIE), request.headers.get("user-agent", ""))
    set_login_cookies(response, tickets, remember=tickets["remember"])
    return {"user": service.public_user(user), "message": "Tickets renewed."}


@router.post("/logout", response_model=MessageOut, summary="Log out")
def logout(request: Request, response: Response):
    """Cancel this browser's long ticket and remove both cookies."""
    service.logout(request.cookies.get(REFRESH_COOKIE))
    clear_login_cookies(response)
    return {"message": "Logged out."}


@router.post("/password-reset/request", response_model=MessageOut, summary="Forgot password: send a code")
def password_reset_request(data: ResetRequestIn):
    """Send a reset code by SMS. The answer is always the same (it never
    reveals whether the number has an account). Max 3 codes per hour."""
    return service.request_password_reset(data.phone)


@router.post("/password-reset/confirm", response_model=MessageOut, summary="Forgot password: set a new one")
def password_reset_confirm(data: ResetConfirmIn):
    """Check the code and save the new password. All old log-ins stop working."""
    service.confirm_password_reset(data)
    return {"message": "Password changed. Please log in with your new password."}
