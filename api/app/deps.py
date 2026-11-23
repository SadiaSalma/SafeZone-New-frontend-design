"""
deps.py - "who is logged in?" checks that any address can use (design doc 3.3).

FastAPI "dependencies": an address writes  user = Depends(get_current_user)
and FastAPI runs this check first. If nobody is logged in, the address never runs.

The log-in tickets travel in cookies:
  sz_access  - the short ticket (15 minutes), sent with every request
  sz_refresh - the long ticket (7 days), only sent to /api/v1/auth/...
Both are "httpOnly": JavaScript on the page cannot read them, so even a bad
script cannot steal them.
"""
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, Request, Response

from app.config import settings
from app.db import get_db
from app.errors import AppError
from app.security import read_access_token

ACCESS_COOKIE = "sz_access"
REFRESH_COOKIE = "sz_refresh"


def set_login_cookies(response: Response, tickets: dict, remember: bool = True) -> None:
    """Put both tickets into secure cookies on the response.

    remember=True  -> the cookies are kept for 7 days (stay logged in).
    remember=False -> "session cookies": the browser deletes them when it closes
                      ("Remember me" not ticked, e.g. on a shared computer).
    """
    secure = settings.app_env != "development"  # on a real server: only over https
    response.set_cookie(ACCESS_COOKIE, tickets["access"],
                        max_age=settings.access_minutes * 60 if remember else None,
                        httponly=True, secure=secure, samesite="lax", path="/")
    response.set_cookie(REFRESH_COOKIE, tickets["refresh"],
                        max_age=settings.refresh_days * 24 * 3600 if remember else None,
                        httponly=True, secure=secure, samesite="lax", path="/api/v1/auth")


def clear_login_cookies(response: Response) -> None:
    """Remove both tickets from the browser (used when logging out)."""
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


def get_current_user(request: Request) -> dict:
    """Return the logged-in user, or stop with 401 'Please log in first.'"""
    token = request.cookies.get(ACCESS_COOKIE)
    payload = read_access_token(token) if token else None
    if not payload:
        raise AppError(401, "not_logged_in", "Please log in first.")

    try:
        user = get_db()["users"].find_one({"_id": ObjectId(payload["sub"])})
    except InvalidId:
        user = None
    if not user or user["status"] != "active":  # e.g. suspended since the ticket was made
        raise AppError(401, "not_logged_in", "Please log in first.")
    return user


def require_roles(*roles: str):
    """A door that only some roles may pass. Usage on an address:

        @router.get("/review/queue")
        def queue(user: dict = Depends(require_roles("verifier", "admin"))): ...

    Not logged in -> 401. Logged in with the wrong role -> 403.
    The website may hide staff links, but THIS check is what really protects them (design doc, Section 9).
    """

    def check(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise AppError(403, "forbidden", "You are not allowed to do this.")
        return user

    return check


def get_optional_user(request: Request) -> dict | None:
    """The logged-in user, or None for visitors (Task 23: anyone may follow an area)."""
    try:
        return get_current_user(request)
    except AppError:
        return None
