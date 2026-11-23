"""
public_routes.py (crime) - Task 28: crime statistics for everyone (no log-in).

  GET /api/v1/public/crime/overview?months=3&category=&level=thana&mode=per_km2
      danger score per area, levels, the top 10, totals per category, sources
"""
from typing import Literal

from fastapi import APIRouter, Response

from app.errors import AppError
from app.modules.crime import overview

router = APIRouter(prefix="/api/v1/public/crime", tags=["Public"])


@router.get("/overview", summary="Danger score, levels and top 10")
def crime_overview(response: Response, months: int = 3, category: str | None = None,
                   level: Literal["thana", "ward"] = "thana", mode: Literal["per_km2", "total"] = "per_km2"):
    """Score = sum of (figure x category weight) per km2 (R6). Thanas and wards are ranked separately.
    Levels are relative: top 10% Very high, next 20% High, next 30% Medium, the rest Low."""
    if months not in (1, 3, 6, 12):
        raise AppError(422, "invalid_input", "Choose 1, 3, 6 or 12 months.", {"months": "Choose 1, 3, 6 or 12 months."})
    response.headers["Cache-Control"] = "public, max-age=300"
    return overview.overview(months, category or None, level, mode)
