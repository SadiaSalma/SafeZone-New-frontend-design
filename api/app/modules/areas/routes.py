"""
routes.py (areas) - Task 12: addresses about places. Anyone may use them (no log-in).

  GET /api/v1/areas                  list thanas and/or wards (search by name)
  GET /api/v1/areas/shapes?type=...  the map shapes of one layer (for drawing)
  GET /api/v1/areas/outline           the edge of Dhaka city (Task 13)
  GET /api/v1/areas/lookup?lat=&lng= which thana + ward is this point in? nearest police?
  GET /api/v1/areas/{code}           one area, with its wards / thanas and police stations
  GET /api/v1/police-stations/nearest?lat=&lng=
"""
from typing import Literal

from fastapi import APIRouter, Query, Response

from app.modules.areas import service

router = APIRouter(prefix="/api/v1", tags=["Areas"])

LAT = Query(ge=20.5, le=26.7, description="Latitude (Bangladesh is about 20.5 to 26.7)", examples=[23.7465])
LNG = Query(ge=88.0, le=92.7, description="Longitude (Bangladesh is about 88.0 to 92.7)", examples=[90.4045])
CACHE_ONE_HOUR = "public, max-age=3600"  # areas almost never change, so browsers may keep them for an hour


@router.get("/areas", summary="List thanas and wards")
def list_areas(response: Response, type: Literal["thana", "ward"] | None = None,
               q: str | None = Query(default=None, max_length=40, description="Part of a name, English or Bangla")):
    response.headers["Cache-Control"] = CACHE_ONE_HOUR
    return {"areas": service.list_areas(type, q)}


@router.get("/areas/shapes", summary="Map shapes of all thanas or all wards")
def area_shapes(response: Response, type: Literal["thana", "ward"] = "thana"):
    response.headers["Cache-Control"] = CACHE_ONE_HOUR
    return service.area_shapes(type)


@router.get("/areas/outline", summary="The edge of the city SafeZone covers")
def city_outline(response: Response):
    """One shape around all 41 thanas, plus the box around it (for the map picker, Task 13)."""
    response.headers["Cache-Control"] = CACHE_ONE_HOUR
    return service.city_outline()


@router.get("/areas/lookup", summary="Which thana and ward is this point in?")
def lookup(lat: float = LAT, lng: float = LNG):
    """Gives the thana, the ward and the 3 nearest police stations. inside_dhaka is false outside the city."""
    return service.lookup(lat, lng)


@router.get("/areas/{code}", summary="One area")
def get_area(code: str, response: Response):
    response.headers["Cache-Control"] = CACHE_ONE_HOUR
    return service.get_area(code)


@router.get("/police-stations/nearest", summary="Nearest police stations")
def nearest_police(lat: float = LAT, lng: float = LNG, limit: int = Query(default=3, ge=1, le=10)):
    return {"police_stations": service.nearest_stations(lat, lng, limit)}
