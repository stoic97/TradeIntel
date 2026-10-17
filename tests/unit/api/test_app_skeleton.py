"""The app boots, serves its own assets, and reaches nothing outside itself.

The last point is the one with teeth. PRD section 10 makes every external system a
line in the data-flow map and a name in the consent text, and a font or a script
pulled from a CDN is an external system that sees every page a trader loads. So the
test is not "we intend to self-host" -- it scans the rendered HTML for any absolute
URL and fails on one.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from services.production.api import settings as st
from services.production.api.app import create_app
from services.production.journal import constants as k

ABSOLUTE_URL = re.compile(r"""(?:src|href|action)\s*=\s*["'](https?:)?//""", re.IGNORECASE)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOPE_DB", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("SCOPE_FILES", str(tmp_path / "files"))
    monkeypatch.setenv("SCOPE_SECRET_KEY", "test-secret-not-a-real-one")
    return TestClient(create_app())


def test_health_reports_ok_and_the_code_version(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["code_version"]


def test_an_unknown_path_is_our_own_404(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert "Traceback" not in response.text
    assert "<html" in response.text.lower()


def test_the_page_renders_with_a_title(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "<title>" in response.text.lower()
    assert "Scope" in response.text


def test_htmx_is_served_from_our_own_static_folder(client):
    page = client.get("/").text
    assert "/static/htmx.min.js" in page
    served = client.get("/static/htmx.min.js")
    assert served.status_code == 200
    assert len(served.content) > 1000, "a stub would make the page silently inert"


def test_no_page_references_anything_outside_this_app(client):
    for path in ("/", "/health"):
        body = client.get(path).text
        match = ABSOLUTE_URL.search(body)
        assert match is None, f"{path} references an external host: {match.group(0)}"


def test_settings_read_the_environment_and_default_no_secret(monkeypatch):
    monkeypatch.delenv("SCOPE_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SCOPE_SECRET_KEY"):
        st.Settings.from_env()

    monkeypatch.setenv("SCOPE_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("SCOPE_DB", "sqlite:///somewhere.db")
    loaded = st.Settings.from_env()
    assert loaded.database_url == "sqlite:///somewhere.db"
    assert loaded.secret_key == "x" * 32


def test_the_product_constants_are_in_one_place_with_their_arguments():
    assert k.DENSITY_THRESHOLD_TRIPS_PER_DAY == 2
    assert k.JOURNALS_ON_SURFACE == 5
    assert k.WTP_DAYS_SINCE_FIRST_UPLOAD == 14
    assert k.WTP_PRICE_INR == 500
    assert k.DEFAULT_TRIPS_PER_JOURNAL == 10
    for name in (
        "DENSITY_THRESHOLD_TRIPS_PER_DAY",
        "JOURNALS_ON_SURFACE",
        "WTP_DAYS_SINCE_FIRST_UPLOAD",
        "WTP_PRICE_INR",
    ):
        assert name in k.ARGUMENTS, f"{name} has no recorded argument"
        assert len(k.ARGUMENTS[name]) > 40, f"{name}'s argument is too thin to review"
