"""
routes.py (crime) - Task 27: crime categories and monthly figures, for ADMINS.

  GET  /api/v1/admin/crime-categories            all categories (with their weights)
  POST /api/v1/admin/crime-categories            add a category
  PUT  /api/v1/admin/crime-categories/{id}       change a name, weight or on/off
  GET  /api/v1/admin/crime-stats?month=2026-10&level=thana   the table for one month
  PUT  /api/v1/admin/crime-stats                 save the changed cells (a source is required)
"""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps import require_roles
from app.modules.crime import admin

router = APIRouter(prefix="/api/v1/admin", tags=["Crime statistics (admin)"])
admins = require_roles("admin")


class CategoryIn(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,30}$", examples=["fraud"])
    name_en: str = Field(min_length=2, max_length=60)
    name_bn: str = Field(default="", max_length=60)
    weight: float = Field(ge=0, le=20)


class CategoryChange(BaseModel):
    name_en: str | None = Field(default=None, min_length=2, max_length=60)
    name_bn: str | None = Field(default=None, max_length=60)
    weight: float | None = Field(default=None, ge=0, le=20)
    is_active: bool | None = None


class Cell(BaseModel):
    area_id: str
    category_id: str
    count: int | None = Field(ge=0, le=100_000)  # None = remove the figure


class FiguresIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-10"])
    source: str = Field(min_length=3, max_length=200, examples=["DMP monthly crime statistics, October 2026"])
    changes: list[Cell] = Field(min_length=1, max_length=5000)


@router.get("/crime-categories", summary="Crime categories and weights")
def list_categories(user: dict = Depends(admins)):
    return {"categories": admin.categories()}


@router.post("/crime-categories", status_code=201, summary="Add a crime category")
def add_category(data: CategoryIn, user: dict = Depends(admins)):
    return admin.add_category(user, data.key, data.name_en, data.name_bn, data.weight)


@router.put("/crime-categories/{category_id}", summary="Change a crime category")
def change_category(category_id: str, data: CategoryChange, user: dict = Depends(admins)):
    return admin.update_category(user, category_id, data.model_dump())


@router.get("/crime-stats", summary="The figures of one month")
def month_table(month: str, level: Literal["thana", "ward"] = "thana", user: dict = Depends(admins)):
    return admin.month_table(month, level)


@router.put("/crime-stats", summary="Save changed figures")
def save_figures(data: FiguresIn, user: dict = Depends(admins)):
    """Every figure needs a source (FR-24). Only totals - no names, addresses or single cases."""
    return admin.save_figures(user, data.month, data.source.strip(), [c.model_dump() for c in data.changes])
