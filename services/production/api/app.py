"""The Scope web app: one FastAPI process, server-rendered, nothing external.

Every asset is served from ``static/``. No CDN, no font service, no analytics, no
error reporting -- each of those would be a system that sees a trader's pages, and
PRD section 10 makes every such system a line in the data-flow map and a name in the
consent text. A test scans rendered HTML for absolute URLs so this stays true by
accident as well as by intent.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from services.production.api import (
    routes_budget,
    routes_consent,
    routes_deletion,
    routes_eligibility,
    routes_events,
    routes_identity,
    routes_journal,
    routes_mirror,
    routes_upload,
)
from services.production.api.settings import Settings
from services.production.db.session import make_engine, run_migrations

HERE = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(HERE / "templates"))


def code_version() -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True, cwd=HERE,
        ).stdout.strip()
        return sha or "unknown"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings.from_env()
    app = FastAPI(title="Scope", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = config
    app.state.code_version = code_version()
    app.state.templates = TEMPLATES
    app.state.engine = make_engine(config.database_url)
    run_migrations(app.state.engine)
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

    app.include_router(routes_identity.router)
    app.include_router(routes_consent.router)
    app.include_router(routes_upload.router)
    app.include_router(routes_mirror.router)
    app.include_router(routes_events.router)
    app.include_router(routes_budget.router)
    app.include_router(routes_journal.router)
    app.include_router(routes_eligibility.router)
    app.include_router(routes_deletion.router)

    @app.get("/health")
    def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "code_version": app.state.code_version})

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        return routes_identity.page(request, "home.html", title="Scope")

    @app.exception_handler(404)
    def not_found(request: Request, _exc: Exception) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request=request, name="404.html", context={"title": "Not found"},
            status_code=404,
        )

    return app
