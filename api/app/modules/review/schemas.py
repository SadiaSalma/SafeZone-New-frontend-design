"""
schemas.py (review) - Task 19: what the verifier sends with a decision.
"""
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

RejectCode = Literal["gd_not_found", "not_a_theft", "duplicate", "outside_area", "not_enough_info", "other"]


class ApproveIn(BaseModel):
    note: str = Field(default="", max_length=300)  # a private note for other staff (optional)
    # Task 20: the verifier's edited alert texts (leave out to use the template). They must pass the privacy filter.
    text_en: str | None = Field(default=None, max_length=600)
    text_bn: str | None = Field(default=None, max_length=600)


class AlertCheckIn(BaseModel):
    """Task 20: "is this alert text safe to send?" (asked while the verifier edits it)."""

    text_en: str = Field(max_length=600)
    text_bn: str = Field(max_length=600)


class RejectIn(BaseModel):
    reason_code: RejectCode
    reason: str = Field(default="", max_length=300, validate_default=True)  # shown to the victim

    @field_validator("reason")
    @classmethod
    def other_needs_words(cls, value: str, info: ValidationInfo) -> str:
        # "Other" says nothing by itself, so then the verifier must write the reason
        if info.data.get("reason_code") == "other" and len(value.strip()) < 5:
            raise ValueError("Write the reason (at least 5 characters).")
        return value


class AskInfoIn(BaseModel):
    question: str = Field(min_length=10, max_length=500, examples=["Please add a photo of your GD copy."])
