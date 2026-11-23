"""
routes.py (users) - addresses about "my account".

  GET  /api/v1/me                      who am I?
  POST /api/v1/me/nid                  add my NID
  GET  /api/v1/me/delete               what "Delete my data" would change (Task 31)
  POST /api/v1/me/delete/request       step 1: password -> a code is sent by SMS
  POST /api/v1/me/delete/confirm       step 2: the code -> the data is deleted and the cookies removed
"""
from fastapi import APIRouter, Depends, Response

from app.deps import clear_login_cookies, get_current_user
from app.modules.auth.schemas import UserOut
from app.modules.auth.service import public_user
from app.modules.users import delete, service
from app.modules.users.schemas import DeleteConfirmIn, DeleteRequestIn, NidIn
from app.ratelimit import check_limit

router = APIRouter(prefix="/api/v1", tags=["My account"])


@router.get("/me", response_model=UserOut, summary="Who am I?")
def me(user: dict = Depends(get_current_user)):
    """The logged-in person's details. Answers 401 if nobody is logged in."""
    return public_user(user)


@router.post("/me/nid", response_model=UserOut, summary="Add my NID number")
def add_my_nid(data: NidIn, user: dict = Depends(get_current_user)):
    """Link a national ID number (10, 13 or 17 digits) to my account. Needed before the first report."""
    return public_user(service.add_nid(user, data.nid))


# ---------------------------------------------------------------- Task 31: delete my data
@router.get("/me/delete", summary="What deleting my data would change")
def delete_summary(user: dict = Depends(get_current_user)):
    return delete.summary(user)


@router.post("/me/delete/request", summary="Delete my data, step 1: send a code")
def delete_request(data: DeleteRequestIn, user: dict = Depends(get_current_user)):
    """Type the password; a 6-digit code is sent by SMS (shown on screen in the demo set-up)."""
    check_limit(f"delete:{user['_id']}", 5, 3600)  # 5 password tries per hour
    return delete.request_delete(user, data.password)


@router.post("/me/delete/confirm", summary="Delete my data, step 2: confirm with the code")
def delete_confirm(data: DeleteConfirmIn, response: Response, user: dict = Depends(get_current_user)):
    """Deletes the account's personal data at once and logs this browser out."""
    result = delete.confirm_delete(user, data.code)
    clear_login_cookies(response)
    return result
