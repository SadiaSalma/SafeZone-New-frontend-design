"""
routes.py (push) - Task 23: browser push notifications. Anyone may follow areas (no log-in needed).

  GET  /api/v1/push/key           the public VAPID key the browser needs (and whether push is on)
  POST /api/v1/push/subscribe     follow areas with this browser
  POST /api/v1/push/unsubscribe   stop all notifications for this browser
  POST /api/v1/push/status        which areas this browser follows
"""
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, HttpUrl

from app.deps import get_optional_user
from app.modules.push import service
from app.ratelimit import check_limit

router = APIRouter(prefix="/api/v1/push", tags=["Notifications"])


class Keys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class SubscribeIn(BaseModel):
    endpoint: HttpUrl  # the push service address the browser gave us
    keys: Keys
    areas: list[str] = Field(default_factory=list, max_length=20, description="Area codes, e.g. ['gulshan', 'dcc-w19']")
    lang: Literal["en", "bn"] = "en"


class EndpointIn(BaseModel):
    endpoint: HttpUrl


@router.get("/key", summary="The public push key")
def push_key():
    return service.public_key()


@router.post("/subscribe", summary="Follow areas with this browser")
def subscribe(data: SubscribeIn, request: Request, user: dict | None = Depends(get_optional_user)):
    check_limit(f"push:{request.client.host if request.client else 'x'}", 30, 3600)
    return service.subscribe(str(data.endpoint), data.keys.model_dump(), data.areas, data.lang, user)


@router.post("/unsubscribe", summary="Stop notifications for this browser")
def unsubscribe(data: EndpointIn):
    return service.unsubscribe(str(data.endpoint))


@router.post("/status", summary="Which areas this browser follows")
def push_status(data: EndpointIn):
    return service.status(str(data.endpoint))

