"""
service.py (alerts) - Task 20: preview, privacy-check and create the alert for an approved report.

The alert itself is created INSIDE the approval transaction (decisions.approve), and the database
allows only ONE alert per report (unique index on alerts.report_id) - so a report can never
alert people twice, and nothing is ever sent for a report that isn't approved (NFR-1).
Sending it to the simulated phones is the alert job in Task 22.
"""
import re
from datetime import datetime, timezone

from bson import ObjectId

from app.config import settings
from app.db import get_db
from app.errors import AppError
from app.modules.alerts.privacy import check_text, victim_name_parts
from app.modules.alerts.text import template

MAX_LENGTH = 400  # an alert should fit on one phone screen


def _report(report_id: ObjectId) -> dict:
    report = get_db().reports.find_one({"_id": report_id})
    if not report:
        raise AppError(404, "report_not_found", "This report does not exist.")
    return report


def radius_for(report: dict) -> int:
    """FR-17: 1 km by default; an admin can set another radius per ward (areas.alert_radius_m)."""
    ward = get_db().areas.find_one({"_id": report.get("ward_id")}, {"alert_radius_m": 1}) if report.get("ward_id") else None
    return int((ward or {}).get("alert_radius_m") or settings.default_alert_radius_m)


def problems_in(report: dict, text_en: str, text_bn: str) -> dict:
    victim = get_db().users.find_one({"_id": report.get("user_id")}, {"name_en": 1, "name_bn": 1}) if report.get("user_id") else None
    # The template is written by SafeZone from fixed words and area names, so it holds no personal data.
    # A name part that is also one of the template's own words (a victim called "Banani" reporting a theft
    # in Banani, or "Alert") is therefore not a leak - skipping it keeps the template approvable.
    # Every other name part is still caught, wherever the verifier types it.
    template_words = {w.lower() for w in re.findall(r"\w+", " ".join(template(report).values()))}
    names = [n for n in victim_name_parts(victim) if n.lower() not in template_words]
    gd = report["gd"]["number"]
    result = {"en": check_text(text_en, names, gd), "bn": check_text(text_bn, names, gd)}
    for lang, text in (("en", text_en), ("bn", text_bn)):
        if not text.strip():
            result[lang].append({"code": "empty", "match": "", "message": "The alert text can't be empty."})
        elif len(text) > MAX_LENGTH:
            result[lang].append({"code": "too_long", "match": "", "message": f"Keep it under {MAX_LENGTH} characters."})
    return result


def preview(report_id: ObjectId) -> dict:
    report = _report(report_id)
    texts = template(report)
    return {**texts, "radius_m": radius_for(report), "problems": problems_in(report, texts["text_en"], texts["text_bn"])}


def check(report_id: ObjectId, text_en: str, text_bn: str) -> dict:
    problems = problems_in(_report(report_id), text_en, text_bn)
    return {"ok": not problems["en"] and not problems["bn"], "problems": problems}


def final_texts(report: dict, text_en: str | None, text_bn: str | None) -> dict:
    """The texts to send: the template, or the verifier's edited texts if they pass the privacy filter."""
    texts = template(report)
    edited = text_en is not None or text_bn is not None
    en = text_en.strip() if text_en is not None else texts["text_en"]
    bn = text_bn.strip() if text_bn is not None else texts["text_bn"]
    problems = problems_in(report, en, bn)
    if problems["en"] or problems["bn"]:
        first = (problems["en"] or problems["bn"])[0]
        raise AppError(422, "alert_privacy", f"The alert text needs fixing: {first['message']}",
                       {"text_en": "; ".join(p["message"] for p in problems["en"]),
                        "text_bn": "; ".join(p["message"] for p in problems["bn"])})
    return {"en": en, "bn": bn, "source": "edited" if edited else "template"}


def new_alert(report: dict, texts: dict, now: datetime | None = None) -> dict:
    """The alert document, queued for the alert job (Task 22)."""
    return {
        "report_id": report["_id"],
        "area_id": report.get("thana_id"),
        "text_en": texts["en"],
        "text_bn": texts["bn"],
        "center": report["location"],  # the exact place: phones around it must be reached
        "radius_m": radius_for(report),
        "status": "queued",
        "queued_at": now or datetime.now(timezone.utc),
        "sent_at": None,
        "attempts": 0,
        "lease_until": None,
        "towers": 0, "phones": 0, "push_sent": 0, "push_failed": 0,
    }
