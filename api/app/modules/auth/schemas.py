"""
schemas.py (auth) - the rules for data coming IN and going OUT.

Pydantic checks every request against these classes automatically.
If something is wrong, the person gets a clear message for that field
(e.g. {"phone": "Enter a Bangladeshi mobile number like 01712345678."}).
"""
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Bangladeshi mobile numbers: 01 + operator digit 3-9 + 8 digits (11 digits in total)
LOCAL_MOBILE = re.compile(r"^01[3-9]\d{8}$")


def normalize_phone(raw: str) -> str:
    """Accept '01712345678', '+880 1712-345678', '8801712345678' ... and return '+8801712345678'."""
    digits = re.sub(r"[\s\-()]", "", raw).lstrip("+")
    if digits.startswith("880"):
        digits = "0" + digits[3:]
    if not LOCAL_MOBILE.match(digits):
        raise ValueError("Enter a Bangladeshi mobile number like 01712345678.")
    return "+88" + digits


class RegisterIn(BaseModel):
    """What the sign-up form sends (FR-1). The 6-digit code goes to this mobile number by SMS."""

    name_en: str = Field(min_length=2, max_length=80, examples=["Rahim Uddin"])
    name_bn: str | None = Field(default=None, max_length=80, examples=["রহিম উদ্দিন"])
    phone: str = Field(examples=["01712345678"])
    password: str = Field(min_length=8, max_length=128, examples=["safe-pass-123"])

    @field_validator("name_en", "name_bn")
    @classmethod
    def strip_spaces(cls, value: str | None) -> str | None:
        return value.strip() if value else value

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str) -> str:
        return normalize_phone(value)

    @field_validator("password")
    @classmethod
    def strong_enough(cls, value: str) -> str:
        return check_password_strength(value)


def check_password_strength(value: str) -> str:
    """The password rule, shared by sign-up, password reset and create_admin."""
    if not (re.search(r"[A-Za-z]", value) and re.search(r"\d", value)):
        raise ValueError("Use at least one letter and one number.")
    return value


class ResetRequestIn(BaseModel):
    """Task 11 - step 1 of "forgot password": which account? (its mobile number)"""

    phone: str = Field(examples=["01712345678"])

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str) -> str:
        return normalize_phone(value)


class ResetConfirmIn(BaseModel):
    """Task 11 - step 2: the code from the SMS + the new password."""

    phone: str = Field(examples=["01712345678"])
    code: str = Field(pattern=r"^\d{6}$", examples=["123456"])
    new_password: str = Field(min_length=8, max_length=128, examples=["new-pass-456"])

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str) -> str:
        return normalize_phone(value)

    @field_validator("new_password")
    @classmethod
    def strong_enough(cls, value: str) -> str:
        return check_password_strength(value)


class RegisterOut(BaseModel):
    """What the backend answers after a successful sign-up."""

    user_id: str
    status: str  # "pending_verify" until the code is confirmed (Task 8)
    code_sent_to: str  # masked, e.g. "017*****678"
    channel: str  # how the code was delivered
    demo_code: str | None = None  # only filled in demo_screen mode
    message: str


class ResendIn(BaseModel):
    phone: str = Field(examples=["01712345678"])
    purpose: Literal["register"] = "register"

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str) -> str:
        return normalize_phone(value)


class MessageOut(BaseModel):
    message: str
    demo_code: str | None = None


class VerifyIn(BaseModel):
    """The 6-digit code the person received by SMS after signing up."""

    phone: str = Field(examples=["01712345678"])
    code: str = Field(pattern=r"^\d{6}$", examples=["123456"])

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str) -> str:
        return normalize_phone(value)


class LoginIn(BaseModel):
    """Log in with phone number and password (FR-2)."""

    phone: str = Field(examples=["01712345678"])
    password: str = Field(min_length=1, max_length=128, examples=["safe-pass-123"])
    remember: bool = True  # "Remember me": False = logged out when the browser closes

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str) -> str:
        return normalize_phone(value)


class UserOut(BaseModel):
    """What the website may know about the logged-in person."""

    id: str
    name_en: str
    name_bn: str
    phone: str
    role: str
    status: str
    nid_added: bool = False  # True once the person has added an NID
    nid_last4: str | None = None  # only the last 4 digits, e.g. "1234"


class LoginOut(BaseModel):
    user: UserOut
    message: str
