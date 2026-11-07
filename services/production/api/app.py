"""The Scope web app: one FastAPI process, server-rendered, nothing external.

Every asset is served from ``static/``. No CDN, no font service, no analytics, no
error reporting -- each of those would be a system that sees a trader's pages, and
PRD section 10 makes every such system a line in the data-flow map and a name in the
consent text. A test scans rendered HTML for absolute URLs so this stays true by
accident as well as by intent.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from services.production.api import (
    dial,
    formatting,
    limits,
    routes_admin,
    routes_budget,
    routes_charges,
    routes_consent,
    routes_deletion,
    routes_eligibility,
    routes_events,
    routes_home,
    routes_identity,
    routes_journal,
    routes_mirror,
    routes_reveal,
    routes_upload,
)
from services.production.api.settings import Settings
from services.production.db.session import make_engine, run_migrations
from services.production.journal import constants as k

HERE = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(HERE / "templates"))
formatting.register(TEMPLATES.env)  # rupees, tone, count, minutes: one place, every page
dial.register(TEMPLATES.env)  # scope_dial: the Scope dial, drawn on the server


def code_version() -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True, cwd=HERE,
        ).stdout.strip()
        return sha or "unknown"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _body_too_large(scope) -> HTMLResponse:
    return routes_consent.upload_page(Request(scope), status_code=413, error=limits.TOO_LARGE)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings.from_env()
    app = FastAPI(title="Scope", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = config
    app.state.code_version = code_version()
    app.state.templates = TEMPLATES
    app.state.engine = make_engine(config.database_url)
    run_migrations(app.state.engine)
    app.state.signups = limits.HourlyCount(cap=k.SIGNUPS_PER_IP_PER_HOUR)
    app.state.login_ids = limits.HourlyCount(cap=k.LOGIN_FAILURES_PER_ID_PER_HOUR)
    app.state.login_connections = limits.HourlyCount(cap=k.LOGIN_FAILURES_PER_IP_PER_HOUR)
    app.add_middleware(limits.BodyCap, refuse=_body_too_large)
    app.state.since_restart = limits.SinceRestart()
    app.state.started_at = datetime.now(UTC)
    app.add_middleware(limits.ErrorCount)
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

    app.include_router(routes_home.router)
    app.include_router(routes_identity.router)
    app.include_router(routes_consent.router)
    app.include_router(routes_upload.router)
    app.include_router(routes_charges.router)
    app.include_router(routes_mirror.router)
    app.include_router(routes_reveal.router)
    app.include_router(routes_events.router)
    app.include_router(routes_budget.router)
    app.include_router(routes_journal.router)
    app.include_router(routes_eligibility.router)
    app.include_router(routes_deletion.router)
    app.include_router(routes_admin.router)

    @app.get("/health")
    def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "code_version": app.state.code_version})

    @app.exception_handler(404)
    def not_found(request: Request, _exc: Exception) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request=request, name="404.html", context={"title": "Not found"},
            status_code=404,
        )

    @app.exception_handler(405)
    async def method_not_allowed(request: Request, exc: Exception):
        """A 405 at /admin would say something is there, so there it is the same 404."""
        if routes_admin.is_admin_path(request.url.path):
            return not_found(request, exc)
        return await http_exception_handler(request, exc)

    return app
