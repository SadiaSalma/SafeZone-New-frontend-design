"""
routes.py (reports) - Task 14: the addresses for theft reports.

  GET  /api/v1/reports/options             theft types, GD types, police stations, limits (anyone)
  POST /api/v1/reports                     send a report (victim, NID needed)
  POST /api/v1/reports/gd-check            is this GD already on an active report? (Task 15)
  POST /api/v1/reports/precheck            tips before sending (Task 17)
  GET  /api/v1/me/reports                  my reports, newest first
  GET  /api/v1/me/reports/{id}             one of my reports
  PUT  /api/v1/me/reports/{id}             answer the verifier's question (Task 19)
  POST /api/v1/me/reports/{id}/withdraw    take back a report nobody has decided on yet
  POST /api/v1/me/reports/{id}/photos      add an item photo or the GD copy (Task 16)
  GET, DELETE /api/v1/me/reports/{id}/photos/{photo_id}   see or remove one of my photos
"""
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.responses import FileResponse

from app.config import settings
from app.deps import require_roles
from app.modules.reports import photos, service
from app.modules.reports.schemas import AnswerIn, GdCheckIn, PrecheckIn, ReportIn

router = APIRouter(prefix="/api/v1", tags=["Theft reports"])
victim = require_roles("victim")


@router.get("/reports/options", summary="Choices for the report form")
def report_options():
    return service.options()


@router.post("/reports", status_code=201, summary="Send a theft report")
def send_report(data: ReportIn, user: dict = Depends(victim)):
    """Needs log-in and an NID. Starts in PENDING_REVIEW. A GD can be on only one active report."""
    return service.create_report(user, data)


@router.post("/reports/precheck", summary="Tips before sending a report")
def precheck_report(data: PrecheckIn, user: dict = Depends(victim)):
    """Task 17: runs the safe automatic checks without saving, and returns tips (e.g. "add a GD copy photo")."""
    return service.precheck(user, data, data.has_gd_copy)


@router.post("/reports/gd-check", summary="Is this GD already reported?")
def check_gd(data: GdCheckIn, user: dict = Depends(victim)):
    """Lets the form warn early. Answers {"free": true/false}. At most 30 checks a minute."""
    return service.gd_is_free(user, data)


@router.get("/me/reports", summary="My reports")
def list_my_reports(user: dict = Depends(victim)):
    return {"reports": service.my_reports(user)}


@router.get("/me/reports/{report_id}", summary="One of my reports")
def get_my_report(report_id: str, user: dict = Depends(victim)):
    return service.my_report(user, report_id)


@router.put("/me/reports/{report_id}", summary="Answer the verifier's question")
def answer_my_report(report_id: str, data: AnswerIn, user: dict = Depends(victim)):
    """Task 19: only while the report is NEEDS_INFO. Sends it back to the review queue."""
    return service.answer_info(user, report_id, data)


@router.post("/me/reports/{report_id}/withdraw", summary="Withdraw my report")
def withdraw_my_report(report_id: str, user: dict = Depends(victim)):
    return service.withdraw(user, report_id)


# ---------------------------------------------------------------- Task 16: photos
@router.post("/me/reports/{report_id}/photos", status_code=201, summary="Add a photo to my report")
async def add_report_photo(report_id: str, kind: Literal["item", "gd_copy"] = Form("item"),
                           file: UploadFile = File(...), user: dict = Depends(victim)):
    """JPEG, PNG or WebP up to 5 MB. Hidden data (like GPS) is removed. 3 item photos + 1 GD copy."""
    raw = await file.read(settings.photo_max_mb * 1024 * 1024 + 1)  # never read more than the limit + 1 byte
    return photos.add_photo(user, report_id, kind, raw)


@router.get("/me/reports/{report_id}/photos/{photo_id}", summary="See one of my photos",
            response_class=FileResponse)
def see_report_photo(report_id: str, photo_id: str, user: dict = Depends(victim)):
    return FileResponse(photos.photo_file_for_owner(user, report_id, photo_id), media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/me/reports/{report_id}/photos/{photo_id}", status_code=204, summary="Remove one of my photos")
def remove_report_photo(report_id: str, photo_id: str, user: dict = Depends(victim)):
    photos.remove_photo(user, report_id, photo_id)
    return Response(status_code=204)
