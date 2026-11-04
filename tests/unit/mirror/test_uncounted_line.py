"""Scope says when sold-option trades are missing from its totals [TICKET-811].

An interim line until sold options are counted (TICKET-810). Until then a total can be
wrong in a way the trader can check against his broker, so the page must not look
certain about it. Every page here shows a total, a worst day or a best trade.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import select

from services.production.db import models as m
from services.production.db.session import make_session
from services.production.journal import generate as gen

TOKEN = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
TRIPS_REFUSED = 3  # read by conftest's client

LINE = "3 sold-option trades are not yet counted — totals will change when they are."


def text(html: str) -> str:
    return " ".join(html.split())


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/mirror",
        "/mirror/chapter/1",
        "/mirror/chapter/3",
        "/mirror/fact/worst-days",
        "/mirror/fact/share",
        "/mirror/fact/money",
        "/mirror/fact/not-told",
    ],
)
def test_the_page_says_how_many_are_not_counted(client, path):
    assert LINE in text(client.get(path).text)


def test_the_reveal_says_it_too(client):
    """Outside production the guess comes first, and the guess shows no figures."""
    page = client.get("/guess").text
    client.post("/guess", data={"answer": "unknown", "csrf_token": TOKEN.search(page).group(1)})
    assert LINE in text(client.get("/mirror/reveal").text)


def test_a_journal_says_it_too(client, engine):
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "fx")).one()
        gen.for_import(sess, trader=trader)
        sess.commit()
        journal_id = sess.scalars(select(m.Journal.id)).first()
    assert LINE in text(client.get(f"/journals/{journal_id}").text)


def test_it_is_said_once_on_a_page(client):
    assert text(client.get("/mirror/chapter/1").text).count(LINE) == 1
