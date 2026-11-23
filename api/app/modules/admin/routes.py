"""
routes.py (admin) - Task 30: the admin panel's addresses.

  GET  /api/v1/admin/stats                    overview numbers (verifiers and admins)
  GET  /api/v1/admin/staff                    all verifiers and admins
  POST /api/v1/admin/staff                    add a verifier or admin
  PUT  /api/v1/admin/staff/{id}               suspend / reactivate / change role
  GET  /api/v1/admin/areas?type=thana         thanas or wards
  PUT  /api/v1/admin/areas/{code}             names, alert radius, on/off
  GET  /api/v1/admin/stations                 police stations
  PUT  /api/v1/admin/stations/{code}          name, phone, on/off
  GET  /api/v1/admin/gd-formats               GD number formats
  POST /api/v1/admin/gd-formats               add a format (the example must match)
  PUT  /api/v1/admin/gd-formats/{id}          switch a format on or off
  GET  /api/v1/admin/settings/risk            risk points and levels
  PUT  /api/v1/admin/settings/risk            save them
  GET  /api/v1/admin/audit-logs?page=1        the audit log, newest first, 50 per page
"""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.deps import require_roles
from app.modules.admin import service

router = APIRouter(prefix="/api/v1/admin", tags=["Admin panel"])
admins = require_roles("admin")
staff = require_roles("verifier", "admin")


class StaffIn(BaseModel):
    name_en: str
    phone: str
    password: str
    role: Literal["verifier", "admin"]


class StaffChange(BaseModel):
    status: Literal["active", "suspended"] | None = None
    role: Literal["verifier", "admin"] | None = None


class AreaChange(BaseModel):
    name_en: str | None = Field(default=None, min_length=2, max_length=60)
    name_bn: str | None = Field(default=None, max_length=60)
    alert_radius_m: int | None = Field(default=None, ge=300, le=3000)  # FR-17: 1 km by default
    is_active: bool | None = None


class StationChange(BaseModel):
    name_en: str | None = Field(default=None, min_length=2, max_length=80)
    name_bn: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, pattern=r"^[0-9+\- ]{0,20}$")
    is_active: bool | None = None


class GdFormatIn(BaseModel):
    regex: str = Field(min_length=2, max_length=120)
    example: str = Field(min_length=1, max_length=40)
    label: str = Field(default="", max_length=80)


class GdFormatChange(BaseModel):
    is_active: bool


class RiskPoints(BaseModel):
    gd_format: int = Field(ge=0, le=100)
    gd_timing: int = Field(ge=0, le=100)
    place_in_gd_thana: int = Field(ge=0, le=100)
    nearby_duplicate: int = Field(ge=0, le=100)
    history: int = Field(ge=0, le=50)
    gd_copy: int = Field(ge=0, le=100)
    ocr_mismatch: int = Field(default=15, ge=0, le=100)  # Task 29


class RiskLevels(BaseModel):
    medium_from: int = Field(ge=1, le=99)
    high_from: int = Field(ge=2, le=100)


class RiskIn(BaseModel):
    risk_points: RiskPoints
    risk_levels: RiskLevels


@router.get("/stats")
def stats(user: dict = Depends(staff)):
    return service.stats()


@router.get("/staff")
def list_staff(user: dict = Depends(admins)):
    return {"staff": service.list_staff()}


@router.post("/staff", status_code=201)
def add_staff(data: StaffIn, user: dict = Depends(admins)):
    return service.add_staff(user, data.name_en, data.phone, data.password, data.role)


@router.put("/staff/{user_id}")
def change_staff(user_id: str, data: StaffChange, user: dict = Depends(admins)):
    return service.change_staff(user, user_id, data.status, data.role)


@router.get("/areas")
def list_areas(type: Literal["thana", "ward"] = "thana", user: dict = Depends(admins)):
    return {"areas": service.list_areas(type)}


@router.put("/areas/{code}")
def change_area(code: str, data: AreaChange, user: dict = Depends(admins)):
    return service.change_area(user, code, data.model_dump())


@router.get("/stations")
def list_stations(user: dict = Depends(admins)):
    return {"stations": service.list_stations()}


@router.put("/stations/{code}")
def change_station(code: str, data: StationChange, user: dict = Depends(admins)):
    return service.change_station(user, code, data.model_dump())


@router.get("/gd-formats")
def list_gd_formats(user: dict = Depends(admins)):
    return {"formats": service.list_gd_formats()}


@router.post("/gd-formats", status_code=201)
def add_gd_format(data: GdFormatIn, user: dict = Depends(admins)):
    return service.add_gd_format(user, data.regex, data.example, data.label)


@router.put("/gd-formats/{format_id}")
def change_gd_format(format_id: str, data: GdFormatChange, user: dict = Depends(admins)):
    return service.change_gd_format(user, format_id, data.is_active)


@router.get("/settings/risk")
def risk_settings(user: dict = Depends(admins)):
    return service.risk_settings()


@router.put("/settings/risk")
def save_risk_settings(data: RiskIn, user: dict = Depends(admins)):
    return service.save_risk_settings(user, data.risk_points.model_dump(), data.risk_levels.model_dump())


@router.get("/audit-logs")
def audit_logs(page: int = Query(1, ge=1, le=10_000), action: str | None = Query(None, max_length=40),
               entity: str | None = Query(None, max_length=40), user: dict = Depends(admins)):
    return service.audit_log(page, action, entity)
