"""
routes.py (review) - Task 18: addresses for verifiers and admins only.

  GET  /api/v1/review/queue                     reports waiting for review (oldest first) + those waiting for the victim
  POST /api/v1/review/{id}/claim                hold the report for 15 minutes (only one verifier wins)
  POST /api/v1/review/{id}/release              let go of my hold
  GET  /api/v1/review/{id}                      the full review screen data
  GET  /api/v1/review/{id}/photos/{photo_id}    one photo of the report
  POST /api/v1/review/{id}/approve | /reject | /ask-info   the decision (Task 19)
  GET  /api/v1/review/{id}/alert-preview        the alert text from the template (Task 20)
  POST /api/v1/review/{id}/alert-check          is an edited alert text safe to send? (Task 20)
"""
from bson import ObjectId
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.deps import require_roles
from app.modules.review import decisions, service
from app.modules.alerts import service as alerts
from app.modules.review.schemas import AlertCheckIn, ApproveIn, AskInfoIn, RejectIn

router = APIRouter(prefix="/api/v1/review", tags=["Review (verifiers)"])
staff = require_roles("verifier", "admin")


@router.get("/queue", summary="The review queue")
def review_queue(user: dict = Depends(staff)):
    return service.queue(user)


@router.post("/{report_id}/claim", summary="Claim a report for 15 minutes")
def claim_report(report_id: str, user: dict = Depends(staff)):
    """Answers 409 'claimed_by_other' if another verifier holds it right now."""
    return service.claim(user, report_id)


@router.post("/{report_id}/release", summary="Release my claim")
def release_report(report_id: str, user: dict = Depends(staff)):
    return service.release(user, report_id)


@router.get("/{report_id}", summary="Everything a verifier needs to decide")
def review_detail(report_id: str, user: dict = Depends(staff)):
    data = service.detail(user, report_id)
    data["timeline"] = decisions.timeline(ObjectId(data["id"]))  # Task 19: the report's history
    data["reject_reasons"] = [{"code": c, "text": t} for c, t in decisions.REJECT_REASONS.items()]
    return data


@router.get("/{report_id}/photos/{photo_id}", summary="One photo of the report", response_class=FileResponse)
def review_photo(report_id: str, photo_id: str, user: dict = Depends(staff)):
    return FileResponse(service.photo_file(report_id, photo_id), media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=3600"})


# ---------------------------------------------------------------- Task 19: decisions
@router.post("/{report_id}/approve", summary="Approve the report")
def approve_report(report_id: str, data: ApproveIn, user: dict = Depends(staff)):
    """You must hold the report. The checks run again; any failed check blocks approval."""
    return decisions.approve(user, report_id, data.note, text_en=data.text_en, text_bn=data.text_bn)


@router.post("/{report_id}/reject", summary="Reject the report (reason required)")
def reject_report(report_id: str, data: RejectIn, user: dict = Depends(staff)):
    return decisions.reject(user, report_id, data.reason_code, data.reason)


@router.post("/{report_id}/ask-info", summary="Ask the victim for more information")
def ask_for_info(report_id: str, data: AskInfoIn, user: dict = Depends(staff)):
    return decisions.ask_info(user, report_id, data.question)


# ---------------------------------------------------------------- Task 20: the alert text
@router.get("/{report_id}/alert-preview", summary="The alert text from the template")
def alert_preview(report_id: str, user: dict = Depends(staff)):
    return alerts.preview(service._oid(report_id))


@router.post("/{report_id}/alert-check", summary="Privacy-check an edited alert text")
def alert_check(report_id: str, data: AlertCheckIn, user: dict = Depends(staff)):
    """Finds phone numbers, emails, GD numbers, house numbers, the victim's name and blaming words."""
    return alerts.check(service._oid(report_id), data.text_en, data.text_bn)
