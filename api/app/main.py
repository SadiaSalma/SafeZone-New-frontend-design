"""
main.py - the starting point of the SafeZone backend.

The server program (uvicorn) loads the `app` object from this file:
    uvicorn app.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse

from app.config import settings
from app.db import database_status
from app.errors import register_error_handlers
from app.modules.areas.routes import router as areas_router
from app.modules.auth.routes import router as auth_router
from app.modules.reports.routes import router as reports_router
from app.modules.review.routes import router as review_router
from app.modules.simulator.routes import router as simulator_router
from app.modules.users.routes import router as users_router
from app.security import csrf_header_check

# Create the web application. The title and version appear on the /docs page.
# docs_url=None: we serve our own /docs page (see the bottom of this file).
app = FastAPI(title=settings.app_name, version="0.5.0", docs_url=None)

# Every error comes back in the same shape: {"error": {"code", "message", "fields"}}
register_error_handlers(app)

# Requests that change data must carry the X-SafeZone: 1 header (CSRF protection).
app.middleware("http")(csrf_header_check)

# CORS: only our own website may call this backend from a browser, never "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-SafeZone"],
)

# Feature modules: each adds its own web addresses
app.include_router(auth_router)  # /api/v1/auth/... (sign up, codes, log in)
app.include_router(users_router)  # /api/v1/me
app.include_router(areas_router)  # /api/v1/areas, /api/v1/police-stations (Task 12)
app.include_router(reports_router)  # /api/v1/reports, /api/v1/me/reports (Task 14)
app.include_router(review_router)  # /api/v1/review (Task 18, verifiers)
app.include_router(simulator_router)  # /api/v1/admin/simulator (Task 21)


@app.get("/api/v1/health")
def health():
    """Answer 'I am alive' and say whether the database is reachable.

    The website's status light calls this every 30 seconds.
    status is "ok" when everything works, "degraded" when the database is down.
    """
    database = database_status()
    return {
        "status": "ok" if database["ok"] else "degraded",
        "app": settings.app_name,
        "env": settings.app_env,
        "version": app.version,
        "database": database,
    }


@app.get("/docs", include_in_schema=False)
def docs_page():
    """The interactive docs page, where you can click "Try it out" on every address.

    Our own website always adds the X-SafeZone: 1 safety header to changes
    (web/lib/api.ts). This page does the same, so "Try it out" works for
    sign up, log in, etc. Security is unchanged: a bad website still cannot
    add this header to requests.
    """
    page = get_swagger_ui_html(openapi_url=app.openapi_url, title=f"{settings.app_name} - docs").body.decode()
    page = page.replace(
        "SwaggerUIBundle({",
        "SwaggerUIBundle({\n        requestInterceptor: (req) => { req.headers['X-SafeZone'] = '1'; return req; },",
        1,
    )
    return HTMLResponse(page)
