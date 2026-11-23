"""
routes.py (public) - Task 25: open to everyone, no log-in (FR-21).

  GET /api/v1/public/incidents?days=7|30|90&type=   verified thefts for the public map
  GET /api/v1/public/alerts                         the latest alerts
  GET /api/v1/public/alerts/{id}                    one alert (the page a push notification opens)
  GET /api/v1/public/areas/{code}/dashboard?days=30|90   one area's safety dashboard (Task 26)
"""
from fastapi import APIRouter, Response

from app.errors import AppError
from app.modules.public import dashboard, service
from app.modules.reports.schemas import TheftType

router = APIRouter(prefix="/api/v1/public", tags=["Public"])
SHORT_CACHE = "public, max-age=60"  # browsers may reuse the answer for a minute


@router.get("/incidents", summary="Verified thefts for the public map")
def public_incidents(response: Response, days: int = 30, type: TheftType | None = None):
    """Points are moved 100-200 m; house burglaries come only as counts per thana."""
    if days not in (7, 30, 90):
        raise AppError(422, "invalid_input", "Choose 7, 30 or 90 days.", {"days": "Choose 7, 30 or 90 days."})
    response.headers["Cache-Control"] = SHORT_CACHE
    return service.incidents(days, type)


@router.get("/alerts", summary="The latest alerts")
def public_alerts(response: Response):
    response.headers["Cache-Control"] = SHORT_CACHE
    return {"alerts": service.latest_alerts()}


@router.get("/alerts/{alert_id}", summary="One alert")
def public_alert(alert_id: str):
    return service.one_alert(alert_id)


@router.get("/areas/{code}/dashboard", summary="One area's safety dashboard")
def area_dashboard(code: str, response: Response, days: int = 90):
    """Thefts, per km2 vs the city, what is stolen, busiest hours and days, weekly trend, hotspots."""
    if days not in (30, 90):
        raise AppError(422, "invalid_input", "Choose 30 or 90 days.", {"days": "Choose 30 or 90 days."})
    response.headers["Cache-Control"] = SHORT_CACHE
    return dashboard.dashboard(code, days)
