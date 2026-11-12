"""TICKET-885: on the way in and out, a count says what it counts.

Cover the label, read the figure aloud, and it states a fact. These are the first numbers a new
trader reads. Most of this surface's words are already right, so this holds only what wasn't, and
the promises on the consent and delete pages stay as they are. All of it is on made-up files.
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api import glossary as GL
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_session
from tests.unit.api import figure_pages as P

TEMPLATES = Path("services/production/api/templates")


def words(html: str) -> str:
    text = re.sub(r"<(script|style|svg)\b.*?</\1>", " ", html, flags=re.DOTALL)
    text = re.sub(r"</?(span|a|strong|em)\b[^>]*>", "", text)
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", text)).replace("\xa0", " ").split())


@pytest.fixture()
def signed_up():
    app = create_app()
    client = TestClient(app, follow_redirects=False)
    P._sign_up(client, app.state.engine, "visitor")
    P._consent(client)
    return client


@pytest.fixture()
def client(signed_up):
    signed_up.post("/upload/demo", data={"csrf_token": P._token(signed_up, "/upload")})
    return signed_up


def latest_import(client) -> int:
    with make_session(client.app.state.engine) as sess:
        return sess.scalars(select(m.Import.id).order_by(m.Import.id.desc())).first()


def test_what_we_read_counts_its_rows_and_trades(client):
    text = words(client.get(f"/imports/{latest_import(client)}").text)
    assert re.search(r"Rows in the file [\d,]+ rows?\b", text)
    assert re.search(r"Rows we could read [\d,]+ rows?\b", text)
    assert re.search(r"Rows set aside [\d,]+ rows?\b", text)
    assert re.search(r"Trades rebuilt [\d,]+ trades?\b", text)


def test_the_same_trades_have_one_name_on_the_two_screens_after_an_upload(client):
    assert "Trades reconstructed" not in words(client.get(f"/imports/{latest_import(client)}").text)


def test_the_screen_a_file_lands_on_counts_its_rows_and_trades(signed_up):
    path = P.CLEAN
    response = signed_up.post(
        "/upload", files={"file": (path.name, path.read_bytes(), "text/csv")},
        data={"csrf_token": P._token(signed_up, "/upload")}, headers={"HX-Request": "true"})
    text = words(response.text)
    assert re.search(r"Rows read [\d,]+ of [\d,]+ rows\b", text), text[:300]
    assert re.search(r"Trades rebuilt [\d,]+ trades?\b", text)


def test_a_group_of_rows_is_one_group_in_the_singular():
    source = (TEMPLATES / "import_review.html").read_text(encoding="utf-8")
    assert '"group" if groups|length == 1 else "groups"' in source
    assert "</span> groups)" not in source


def test_rows_we_could_not_read_say_how_many_rows():
    source = (TEMPLATES / "import_review.html").read_text(encoding="utf-8")
    assert "Rows we could not read (" not in source
    assert "we could not read</h2>" in source


def test_home_names_an_upload_and_retires_import_from_its_card(client):
    html = client.get("/").text
    card = re.search(r'<a class="scope-card on-navy".*?</a>', html, re.DOTALL)[0]
    assert re.search(r"Your report · Upload \d+ · ", words(card))
    assert GL.HOME_CARD in {e.where for e in GL.GLOSSARY if e.word == "Import"}


@pytest.mark.parametrize("says", [
    r"(\d+ checks? (has|have) enough to work with|None of them has enough to work with yet)\.",
    r"\d+ checks? needs? more history than you have given us so far",
    r"\d+ checks? (is|are) waiting on something that is not your trades at all",
])
def test_each_count_on_what_we_can_check_names_the_checks(client, says):
    assert re.search(says, words(client.get("/eligibility").text))


def test_the_consent_ledger_says_version_not_a_bare_number(client):
    assert re.search(r"granted version \S+", words(client.get("/settings/consent").text))


def test_the_nine_pm_count_on_the_reveal_is_a_count_of_days():
    source = (TEMPLATES / "reveal.html").read_text(encoding="utf-8")
    assert 'Figure(five_days.past_nine, "days")' in source
    assert 'Figure(five_days.past_nine, "trades")' not in source
    assert "</span> of them ran past 9 pm" in source
