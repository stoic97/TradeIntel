"""The door: the question first, then a trader's first questions answered, then a form
that asks only for a login id and a password. And a sign-in page with a way to reach us."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_session
from tests.unit.api.test_read_again import words
from tests.unit.api.test_upload import CSRF, engine  # noqa: F401

QUESTION = "When your first trade of the day loses, what usually happens next?"
ANSWERS = {"make-back": "I make it back", "break-even": "I break even",
           "lose-more": "I lose more", "unknown": "I don't know"}
ROWS = (
    ("You give us", "The trade file your broker lets you download. Never your broker login."),
    ("You get", "Your own trades, counted: where your results came from, with the trades behind every figure."),
    ("You won't get", "Tips or courses. No buy or sell calls, ever."),
    ("Brokers", "Dhan today. Others are coming."),
    ("Cost", "Free today."),
    ("Your file", "No third party receives it. Delete everything whenever you want."),
)
FORM = 'action="/signup"'


def door(path: str = "/") -> str:
    return TestClient(create_app()).get(path).text


def test_the_door_asks_the_question_first(engine):  # noqa: F811
    page = door()
    assert QUESTION in words(page)
    assert words(page).index(QUESTION) < words(page).index("You give us")
    for key, label in ANSWERS.items():
        assert f'href="/?said={key}#door-form"' in page and label in words(page)


def test_there_is_no_form_before_the_tap(engine):  # noqa: F811
    assert FORM not in door()


def test_the_first_questions_are_answered_on_the_door(engine):  # noqa: F811
    text = words(door())
    for label, answer in ROWS:
        assert f"{label} {answer}" in text, label


def test_after_the_tap_it_says_what_he_said_and_offers_the_form(engine):  # noqa: F811
    for key, label in ANSWERS.items():
        page = door(f"/?said={key}")
        assert f"You said: {label}." in words(page)
        assert FORM in page


def test_the_form_asks_for_a_login_id_and_a_password_and_nothing_else(engine):  # noqa: F811
    page = door("/?said=unknown")
    form = re.search(r'<form[^>]*action="/signup"[^>]*>(.*?)</form>', page, re.DOTALL)[1]
    names = set(re.findall(r'name="([^"]+)"', form)) - {"csrf_token"}
    assert names == {"login_id", "password"}
    text = words(form)
    assert "Choose a login id" in text and "Any name you like" in text
    assert "We don't ask for your email or phone, so we can't call or message you." in text


def test_an_answer_it_does_not_know_is_no_answer(engine):  # noqa: F811
    page = door("/?said=something-else")
    assert "You said" not in words(page) and FORM not in page


def test_signing_up_needs_only_a_login_id_and_a_password(engine):  # noqa: F811
    client = TestClient(create_app())
    csrf = CSRF.search(client.get("/?said=unknown").text).group(1)
    response = client.post("/signup", data={"login_id": "newcomer", "password": "a-long-enough-password",
                                            "csrf_token": csrf}, follow_redirects=False)
    assert response.status_code == 303
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "newcomer")).one()
    assert trader.display_name == "newcomer"


def test_there_is_one_door(engine):  # noqa: F811
    """/signup is the door's form, not a second sign-up page."""
    page = door("/signup")
    assert FORM in page and QUESTION in words(page)


def test_the_door_has_sign_in_and_the_sample(engine):  # noqa: F811
    for path in ("/", "/?said=make-back"):
        page = door(path)
        assert 'href="/login"' in page and 'href="/sample"' in page, path


def test_sign_in_carries_the_logo_and_a_way_to_reach_us(engine):  # noqa: F811
    page = door("/login")
    assert 'class="lockup' in page
    assert ("Forgot your password? Your account has no email, so a reset goes through us: "
            "team@plusev.in") in words(page)
    assert 'href="mailto:team@plusev.in"' in page
    assert 'href="/"' in page
