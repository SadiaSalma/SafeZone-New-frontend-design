"""
photos.py (reports) - Task 16: photos of the stolen items and of the GD copy.

Every upload is cleaned before it is kept:
  1. Only real images are accepted (JPEG, PNG or WebP), checked by opening them -
     the file name or the browser's word is never trusted.
  2. At most 5 MB, and not absurdly large in pixels (a "decompression bomb" could freeze the server).
  3. The photo is turned the right way up, shrunk to at most 1600 px, and saved again as JPEG.
     Saving again throws away ALL hidden data (EXIF), including the GPS position where the
     photo was taken - which could reveal where the victim lives (Design Revisions R8).

Limits: 3 item photos + 1 GD copy per report; only the owner; only while the report is still open.
"""
import io
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from PIL import Image, ImageOps, UnidentifiedImageError

from app import storage
from app.audit import write_audit
from app.config import settings
from app.db import get_db
from app.errors import AppError
from app.modules.reports.checks import refresh_checks

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_PIXELS = 40_000_000  # 40 megapixels: bigger than any phone camera
OPEN_STATUSES = ("PENDING_REVIEW", "NEEDS_INFO")  # photos can be added or removed only while the report is open


def clean_image(raw: bytes, max_side: int | None = None) -> tuple[bytes, int, int]:
    """Check and clean an uploaded image. Returns (jpeg bytes, width, height).
    max_side: the longest side after shrinking (GD scans for OCR keep a little more detail - Task 29)."""
    if len(raw) > settings.photo_max_mb * 1024 * 1024:
        raise AppError(413, "photo_too_big", f"Photos can be at most {settings.photo_max_mb} MB.")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ALLOWED_FORMATS:
                raise AppError(415, "not_a_photo", "Upload a JPEG, PNG or WebP photo.")
            if image.width * image.height > MAX_PIXELS:
                raise AppError(413, "photo_too_big", "This photo has too many pixels.")
            image = ImageOps.exif_transpose(image)  # turn it the right way up first
            image = image.convert("RGB")  # PNG/WebP with transparency -> plain colours
            side = max_side or settings.photo_max_side
            image.thumbnail((side, side))
            out = io.BytesIO()
            image.save(out, "JPEG", quality=82, optimize=True)  # no exif= given -> no hidden data is kept
            return out.getvalue(), image.width, image.height
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise AppError(415, "not_a_photo", "Upload a JPEG, PNG or WebP photo.")


def _open_report(user: dict, report_id: str) -> dict:
    try:
        oid = ObjectId(report_id)
    except (InvalidId, TypeError):
        raise AppError(404, "report_not_found", "This report does not exist.")
    report = get_db().reports.find_one({"_id": oid, "user_id": user["_id"]}, {"status": 1})
    if not report:
        raise AppError(404, "report_not_found", "This report does not exist.")
    return report


def photo_url(report_id, photo_id) -> str:
    return f"/api/v1/me/reports/{report_id}/photos/{photo_id}"


def public_photo(photo: dict) -> dict:
    return {"id": str(photo["_id"]), "kind": photo.get("kind", "item"), "url": photo_url(photo["report_id"], photo["_id"]),
            "width": photo.get("width"), "height": photo.get("height")}


def photos_of(report_id: ObjectId) -> list[dict]:
    found = get_db().report_photos.find({"report_id": report_id}).sort("created_at", 1)
    return [public_photo(p) for p in found]


def add_photo(user: dict, report_id: str, kind: str, raw: bytes) -> dict:
    report = _open_report(user, report_id)
    if report["status"] not in OPEN_STATUSES:
        raise AppError(409, "report_closed", "Photos can only be added while the report is waiting for review.")

    db = get_db()
    have = db.report_photos.count_documents({"report_id": report["_id"], "kind": kind})
    allowed = settings.item_photos_per_report if kind == "item" else 1
    if have >= allowed:
        message = (f"You can add at most {allowed} item photos." if kind == "item"
                   else "This report already has a GD copy. Remove it first to add another.")
        raise AppError(409, "too_many_photos", message)

    jpeg, width, height = clean_image(raw)
    key = storage.save(jpeg, "jpg")
    photo = {"user_id": user["_id"], "report_id": report["_id"], "kind": kind, "storage_key": key,
             "size_bytes": len(jpeg), "width": width, "height": height, "created_at": datetime.now(timezone.utc)}
    photo["_id"] = db.report_photos.insert_one(photo).inserted_id
    write_audit("report.photo_add", "reports", entity_id=report["_id"], actor_id=user["_id"],
                actor_role=user["role"], after={"kind": kind})
    if kind == "gd_copy":
        refresh_checks(report["_id"])  # Task 17: the "GD copy" check changes
    return public_photo(photo)


def _find_photo(report: dict, photo_id: str) -> dict:
    try:
        oid = ObjectId(photo_id)
    except (InvalidId, TypeError):
        raise AppError(404, "photo_not_found", "This photo does not exist.")
    photo = get_db().report_photos.find_one({"_id": oid, "report_id": report["_id"]})
    if not photo:
        raise AppError(404, "photo_not_found", "This photo does not exist.")
    return photo


def photo_file_for_owner(user: dict, report_id: str, photo_id: str):
    """The file of one of MY photos (other people get 404, as if it did not exist)."""
    return storage.path_of(_find_photo(_open_report(user, report_id), photo_id)["storage_key"])


def remove_photo(user: dict, report_id: str, photo_id: str) -> None:
    report = _open_report(user, report_id)
    if report["status"] not in OPEN_STATUSES:
        raise AppError(409, "report_closed", "Photos can only be removed while the report is waiting for review.")
    photo = _find_photo(report, photo_id)
    get_db().report_photos.delete_one({"_id": photo["_id"]})
    storage.delete(photo["storage_key"])
    write_audit("report.photo_remove", "reports", entity_id=report["_id"], actor_id=user["_id"],
                actor_role=user["role"], after={"kind": photo.get("kind", "item")})
    if photo.get("kind") == "gd_copy":
        refresh_checks(report["_id"])  # Task 17: the "GD copy" check changes
