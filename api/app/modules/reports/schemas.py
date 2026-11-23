"""
schemas.py (reports) - Task 14: what a theft report looks like coming IN and going OUT.

Times: the website sends the theft time with its time zone (e.g. "2026-11-20T21:30:00+06:00").
A time without a zone is read as Dhaka time (UTC+6). Everything is stored in UTC.
"""
import re
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schema import THEFT_TYPES

DHAKA = timezone(timedelta(hours=6))
TheftType = Literal[THEFT_TYPES]  # the 10 theft types (FR-8)

# Bangla digits -> normal digits, so "১২৩৪" and "1234" are the same GD number
BN_TO_EN = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

THEFT_LABELS = {
    "phone_snatching": ("Phone snatching", "ফোন ছিনতাই"),
    "bag_snatching": ("Bag snatching", "ব্যাগ ছিনতাই"),
    "pickpocket": ("Pickpocketing", "পকেটমার"),
    "motorbike_theft": ("Motorbike theft", "মোটরসাইকেল চুরি"),
    "bicycle_theft": ("Bicycle theft", "সাইকেল চুরি"),
    "car_theft": ("Car theft", "গাড়ি চুরি"),
    "cng_theft": ("CNG auto-rickshaw theft", "সিএনজি অটোরিকশা চুরি"),
    "burglary": ("House burglary", "বাসায় চুরি"),
    "shop_theft": ("Shop theft", "দোকানে চুরি"),
    "other": ("Other theft", "অন্যান্য চুরি"),
}


def clean_gd_number(raw: str) -> str:
    """'  ০১২৩৪ ' -> '1234' ; 'gd-12/34' -> 'GD-12/34' (spaces removed, Bangla digits changed)."""
    value = re.sub(r"\s+", "", raw.translate(BN_TO_EN)).upper()
    if not re.fullmatch(r"[A-Z0-9/\-]{1,30}", value):
        raise ValueError("Use only letters, numbers, - and / (at most 30).")
    if value.isdigit():
        value = value.lstrip("0") or "0"
    return value


class GdIn(BaseModel):
    type: Literal["GD", "FIR"] = "GD"
    number: str = Field(examples=["1234"])
    date: date
    police_station: str = Field(min_length=1, max_length=60, examples=["ramna-model-ps"])  # a police station code

    @field_validator("number")
    @classmethod
    def check_number(cls, value: str) -> str:
        return clean_gd_number(value)


class ReportIn(BaseModel):
    """What the 4-step report form sends (FR-8)."""

    theft_type: TheftType
    occurred_at: datetime = Field(examples=["2026-11-20T21:30:00+06:00"])
    lat: float = Field(ge=20.5, le=26.7, examples=[23.7457])
    lng: float = Field(ge=88.0, le=92.7, examples=[90.4047])
    landmark: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=1000)
    stolen_items: str = Field(default="", max_length=300)
    gd: GdIn
    gd_scan_id: str | None = Field(default=None, max_length=24)  # Task 29: the photo of the GD copy that OCR read

    @field_validator("occurred_at")
    @classmethod
    def as_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=DHAKA)  # no zone given -> Dhaka time
        return value.astimezone(timezone.utc)

    @field_validator("landmark", "description", "stolen_items")
    @classmethod
    def strip_spaces(cls, value: str) -> str:
        return value.strip()


class GdCheckIn(BaseModel):
    """Task 15: "is this GD already on another report?" (asked while the victim types)."""

    type: Literal["GD", "FIR"] = "GD"
    number: str
    date: date
    police_station: str = Field(min_length=1, max_length=60)

    @field_validator("number")
    @classmethod
    def check_number(cls, value: str) -> str:
        return clean_gd_number(value)


class PrecheckIn(ReportIn):
    """Task 17: the whole form, plus "has the victim chosen a GD copy photo?" (photos are uploaded later)."""

    has_gd_copy: bool = False


class AnswerIn(BaseModel):
    """Task 19: the victim answers the verifier's question, and may fix some details."""

    answer: str = Field(min_length=3, max_length=1000)
    landmark: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    stolen_items: str | None = Field(default=None, max_length=300)
    gd: GdIn | None = None  # a corrected GD (number, date, police station)
