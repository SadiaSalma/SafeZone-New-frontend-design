"""
schemas.py (users) - rules for "my account" requests.
"""
import re
from datetime import date

from pydantic import BaseModel, Field, field_validator


def clean_nid(raw: str) -> str:
    """Accept '1234 567 890' or '19901234567890123' and return digits only, if the format is valid.

    Bangladeshi NID numbers come in three formats:
      10 digits - smart card NID
      13 digits - older paper NID
      17 digits - older NID with the birth year in front (e.g. 1990...)
    """
    digits = re.sub(r"[\s\-]", "", raw)
    if not digits.isdigit() or len(digits) not in (10, 13, 17):
        raise ValueError("Enter your NID number: 10, 13 or 17 digits.")
    if len(digits) == 17:
        year = int(digits[:4])
        if not 1900 <= year <= date.today().year:
            raise ValueError("A 17-digit NID starts with your birth year. Check the number.")
    return digits


class DeleteRequestIn(BaseModel):
    """Task 31, step 1: the password proves it is really the owner."""
    password: str = Field(min_length=1, max_length=200)


class DeleteConfirmIn(BaseModel):
    """Task 31, step 2: the 6-digit code from the SMS."""
    code: str = Field(pattern=r"^\d{6}$")


class NidIn(BaseModel):
    nid: str = Field(examples=["1234567890"])

    @field_validator("nid")
    @classmethod
    def check_nid(cls, value: str) -> str:
        return clean_nid(value)
