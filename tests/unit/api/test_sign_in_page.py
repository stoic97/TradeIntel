"""Sign in (screen 4), rebuilt on layout.html: the first page on the design kit.

The proof page for Phase 0 (handoff section 10): it stands on the layout, the kit's
stylesheets and the components, and keeps the app's own words exactly (handoff
section 6). Two choices differ from the kit's template, both on purpose, and both are
tested here:
- the login id is not written back after a failed attempt: a wrong password and an
  unknown login id must give the same page (test_identity.py), and echoing what was
  typed would make the two differ;
- there is no "Scope page" link: it is not wording the app has, and new lines wait
  for the copy owner (D9).
"""

from __future__ import annotations

import os
import re

import pytest
from fastapi.testclient import TestClient

from services.production.api.app import create_app
from services.production.db.session import make_engine, run_migrations

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
FAILED = "That login id and password do not match an account."


@pytest.fixture()
def client():
    run_migrations(make_engine(os.environ["SCOPE_DB"]))
    return TestClient(create_app())


def words(html: str) -> str:
    """The page's main column as a reader sees it: text only, spaces collapsed."""
    main = html.split("<main", 1)[1].split("</main>", 1)[0]
    return " ".join(re.sub(r"<[^>]+>", " ", main.split(">", 1)[1]).split())


def failed_attempt(client, login_id="nobody-at-all", password="wrong-but-long-enough"):
    csrf = CSRF.search(client.get("/login").text).group(1)
    return client.post("/login", data={"login_id": login_id, "password": password,
                                       "csrf_token": csrf})


def test_sign_in_stands_on_the_design_kits_layout(client):
    html = client.get("/login").text
    assert '<link rel="stylesheet" href="/static/css/components.css">' in html
    assert "/static/scope.css" not in html
    assert "<title>Sign in · PlusEV Scope</title>" in html


def test_it_says_what_it_said_before_and_nothing_more(client):
    assert words(client.get("/login").text) == "Sign in Login id Password Sign in"


def test_the_fields_are_the_kits_and_keep_what_the_browser_needs(client):
    html = client.get("/login").text
    assert '<h1 class="title">Sign in</h1>' in html
    assert 'name="login_id" type="text" autocomplete="username" required>' in html
    assert 'name="password" type="password" autocomplete="current-password" required>' in html
    assert '<button class="btn btn--primary btn--block" type="submit">Sign in</button>' in html


def test_the_form_still_posts_to_login_with_its_token(client):
    html = client.get("/login").text
    assert '<form method="post" action="/login">' in html and CSRF.search(html)


def test_there_is_no_bottom_nav_and_no_link_the_app_has_no_words_for(client):
    html = client.get("/login").text
    assert "bottom-nav" not in html and "Scope page" not in html


def test_a_failed_sign_in_says_so_once_and_marks_both_fields(client):
    response = failed_attempt(client)
    assert response.status_code == 400
    assert response.text.count(FAILED) == 1
    assert f'<p class="field__error field__error--block" role="alert">{FAILED}</p>' in response.text
    assert response.text.count('class="field field--error"') == 2
    assert response.text.count('aria-invalid="true"') == 2


def test_nothing_typed_is_written_back(client):
    response = failed_attempt(client, login_id="someone-typed-this", password="typed-secret-1234")
    assert "someone-typed-this" not in response.text
    assert "typed-secret-1234" not in response.text
