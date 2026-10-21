"""The landing page, for someone who is not signed in.

A trader signs up once, closes the tab, and comes back a week later to read his
Journal. This is the page he lands on, and until now it said "Invitation only."
and offered him nothing to click -- he would have had to guess ``/login``.

Found by opening the deployed site rather than by a test, which is the third
time that has happened on this product and worth noticing.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from services.production.api.app import create_app


def test_the_landing_page_offers_a_way_back_in(scope_environment):
    page = TestClient(create_app()).get("/")
    assert page.status_code == 200
    assert 'href="/login"' in page.text, (
        "a returning trader lands here; without a way in it is a dead end"
    )
