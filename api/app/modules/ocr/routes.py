"""
routes.py (ocr) - Task 29: reading a photo of the GD copy (FR-9, design doc API table "ocr").

  POST /api/v1/gd-scans              upload a photo -> {"id", "status": "processing" | "done" | "failed", ...}
  GET  /api/v1/gd-scans/{id}         the result (the website asks every second until it is not "processing")
  GET  /api/v1/gd-scans/{id}/photo   my own GD photo (to show it next to the form)

Only victims, and only their own scans. Nothing is filled in automatically on the server:
the website puts the fields into the form and the victim checks and corrects them.
"""
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse

from app.config import settings
from app.deps import require_roles
from app.modules.ocr import service

router = APIRouter(prefix="/api/v1/gd-scans", tags=["GD photo reading (OCR)"])
victim = require_roles("victim")


@router.post("", status_code=202, summary="Upload a photo of my GD copy")
async def upload_gd_photo(file: UploadFile = File(...), user: dict = Depends(victim)):
    """JPEG, PNG or WebP up to 5 MB. Hidden data (like GPS) is removed. Reading takes a few seconds."""
    raw = await file.read(settings.photo_max_mb * 1024 * 1024 + 1)
    return service.new_scan(user, raw)


@router.get("/{scan_id}", summary="The result of reading my GD photo")
def gd_scan_result(scan_id: str, user: dict = Depends(victim)):
    return service.get_scan(user, scan_id)


@router.get("/{scan_id}/photo", summary="My GD photo", response_class=FileResponse)
def gd_scan_photo(scan_id: str, user: dict = Depends(victim)):
    return FileResponse(service.photo_file(user, scan_id), media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=3600"})
