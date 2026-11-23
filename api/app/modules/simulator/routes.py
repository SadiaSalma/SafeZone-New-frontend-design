"""
routes.py (simulator) - Tasks 21 + 24: the simulated phone network, for staff.

  GET    /api/v1/admin/simulator/network                  all towers (+ phones per tower) and phone counts
  GET    /api/v1/admin/simulator/phones?south=&west=&north=&east=[&alert_id=]
                                                          the phones in the map view (+ "received" for one alert)
  GET    /api/v1/admin/simulator/alerts/{id}              an alert's circle and the towers that broadcast it (Task 24)
  GET    /api/v1/admin/simulator/phones/{id}/inbox        one phone's messages (Task 24)
  GET    /api/v1/admin/simulator/test-phone               my test phone + Received / Not reached per alert (admin)
  POST   /api/v1/admin/simulator/test-phone               place (or move) my test phone (admin)
  DELETE /api/v1/admin/simulator/test-phone               remove my test phone (admin)
"""
from bson import ObjectId
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.deps import require_roles
from app.modules.simulator import network, test_mode

router = APIRouter(prefix="/api/v1/admin/simulator", tags=["Simulator (staff)"])
staff = require_roles("verifier", "admin")
admin = require_roles("admin")


class TestPhoneIn(BaseModel):
    lat: float = Field(ge=20.5, le=26.7)
    lng: float = Field(ge=88.0, le=92.7)
    label: str = Field(default="", max_length=40)


@router.get("/network", summary="Towers and phone counts")
def simulator_network(user: dict = Depends(staff)):
    return network.network_summary()


@router.get("/phones", summary="Virtual phones inside the map view")
def simulator_phones(south: float = Query(ge=20.5, le=26.7), west: float = Query(ge=88.0, le=92.7),
                     north: float = Query(ge=20.5, le=26.7), east: float = Query(ge=88.0, le=92.7),
                     alert_id: str | None = None, user: dict = Depends(staff)):
    answer = network.phones_in_box(south, west, north, east)
    if alert_id:  # Task 24: mark the phones that received this alert (shown red on the map)
        got = test_mode.received_ids(alert_id, [ObjectId(p["id"]) for p in answer["phones"]])
        for phone in answer["phones"]:
            phone["received"] = ObjectId(phone["id"]) in got
    return answer


@router.get("/alerts/{alert_id}", summary="One alert on the simulator")
def simulator_alert(alert_id: str, user: dict = Depends(staff)):
    return test_mode.alert_view(alert_id)


@router.get("/phones/{phone_id}/inbox", summary="One phone's messages")
def phone_inbox(phone_id: str, user: dict = Depends(staff)):
    return test_mode.phone_inbox(phone_id)


@router.get("/test-phone", summary="My test phone and what it received")
def my_test_phone(user: dict = Depends(admin)):
    return test_mode.test_phone_report(user)


@router.post("/test-phone", summary="Place my test phone")
def place_test_phone(data: TestPhoneIn, user: dict = Depends(admin)):
    """FR-20: the phone joins the nearest tower and gets every alert that tower broadcasts from now on."""
    return test_mode.place_test_phone(user, data.lat, data.lng, data.label)


@router.delete("/test-phone", summary="Remove my test phone")
def remove_test_phone(user: dict = Depends(admin)):
    return test_mode.remove_test_phone(user)
