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


def test_the_header_links_back_to_plusev(scope_environment):
    """Scope is a PlusEV product, and a trader should be able to get back.

    The wordmark was plain text. On its own subdomain that makes the app feel
    like somewhere he arrived at from nowhere.
    """
    page = TestClient(create_app()).get("/")
    assert 'href="https://plusev.in"' in page.text


def test_the_front_door_is_the_kits_navy_door(scope_environment):
    """Handoff 5, screen 0, in the app's own words."""
    page = TestClient(create_app()).get("/").text
    assert '<header class="stage stage--door on-navy">' in page
    assert '<p class="label label--plain door__note">Invitation only.</p>' in page
    assert ('<h1 class="title door__title">A record of how you traded, built from your own '
            "tradebook.</h1>") in page
    assert '<a class="link" href="/login">Sign in if you already have an account.</a>' in page
    assert '<nav class="bottom-nav"' not in page  # signed out: no tabs to go to

