"""Blind replay's pages: closed until its three conditions hold, and leak-free when open.

The bars are a seeded random walk around a synthetic file's January 2024 trades; nothing
here is anyone's market data or anyone's trades.
"""

from __future__ import annotations

import dataclasses
import re
from datetime import date, datetime, timedelta

import numpy as np
import pytest
from sqlalchemy import func, select

from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror.prior_minute import IST, Bar, BarTable
from services.production.replay import blind as B
from services.production.replay import sources
from tests.unit.api.test_read_again import send, words
from tests.unit.api.test_upload import client, engine  # noqa: F401

DAYS = [date(2024, 1, 1) + timedelta(days=i) for i in range(31)]


def walk(seed: int = 3) -> BarTable:
    rng = np.random.default_rng(seed)
    bars, price = {}, 21000.0
    for d in DAYS:
        if d.weekday() >= 5:
            continue
        for minute in range(8 * 60, 16 * 60):
            start = datetime(d.year, d.month, d.day, minute // 60, minute % 60, tzinfo=IST)
            close = price + float(rng.choice([-3.0, -1.0, 1.0, 3.0]))
            bars[start] = Bar(open=price, close=close)
            price = close
    return BarTable(bars=bars, first_day=DAYS[0], last_day=DAYS[-1])


@pytest.fixture()
def bars(monkeypatch):
    table = walk()
    monkeypatch.setattr(sources, "series_for", lambda wanted: {"NIFTY": table})
    monkeypatch.setattr(B, "PREREG_SIGNED", True)
    return table


def plain(page: str) -> str:
    return re.sub(r'name="csrf_token" value="[^"]+"', "", page)


def rows(engine) -> dict[str, int]:  # noqa: F811
    with make_session(engine) as sess:
        return {t.name: sess.scalar(select(func.count()).select_from(t))
                for t in m.Base.metadata.sorted_tables}


def test_it_is_closed_until_the_rule_for_its_count_is_signed(client):  # noqa: F811
    send(client)
    said = words(client.get("/replay").text)
    assert "waits for the research seat to sign it" in said
    assert B.PREREG_SIGNED is False


def test_it_is_closed_without_bars(client, monkeypatch):  # noqa: F811
    send(client)
    monkeypatch.setattr(B, "PREREG_SIGNED", True)
    assert "one-minute prices for your trades' dates, and those aren't here yet" in words(
        client.get("/replay").text)


def test_it_states_the_age_cutoff(client, bars):  # noqa: F811
    send(client)
    said = words(client.get("/replay").text)
    assert f"Only trades more than {B.OLD_AFTER_DAYS} days old are used" in said


def test_a_card_shows_no_date_and_no_answer(client, bars):  # noqa: F811
    send(client)
    said = words(client.get("/replay/card").text)
    assert "Take it" in said and "Skip it" in said
    for leak in ("2024", "Jan", "your own entries", "random moment", "moved", "points"):
        assert leak not in said, leak


def test_the_page_before_the_reveal_does_not_move_when_the_future_does(client, bars, monkeypatch):  # noqa: F811
    """Change every bar at or after the first card's moment: the card page is identical."""
    send(client)
    first = client.get("/replay/card").text
    calls_seen = []

    def deal_spy(*args, **kwargs):
        dealt = real_deal(*args, **kwargs)
        calls_seen.append(dealt)
        return dealt
    real_deal = B.deal
    monkeypatch.setattr(B, "deal", deal_spy)
    client.get("/replay/card")
    moment = calls_seen[-1][0].card.moment
    future = {t: (Bar(open=b.open, close=b.close + 500.0) if t >= moment else b)
              for t, b in bars.bars.items()}
    monkeypatch.setattr(sources, "series_for",
                        lambda wanted: {"NIFTY": dataclasses.replace(bars, bars=future)})
    assert plain(client.get("/replay/card").text) == plain(first)


def test_the_reveal_says_whose_it_was_and_the_points_before_charges(client, bars):  # noqa: F811
    send(client)
    said = words(client.get("/replay/reveal?calls=T").text)
    assert ("One of your own entries" in said) != ("A random moment" in said)
    assert "points, before charges" in said and "2024" in said


def test_the_count_comes_first_against_a_coin_and_with_no_rupee_or_percent(client, bars):  # noqa: F811
    send(client)
    first = client.get("/replay/card").text
    cards = int(re.search(r"of\s*(?:<[^>]+>)*\s*(\d+)\s*(?:<[^>]+>)*\s*</p>", first).group(1))
    said = words(client.get("/replay/score?calls=" + "T" * cards).text)
    assert said.index(f"{cards} calls. Right on") < said.index("A coin flip on")
    for page in ("/replay", "/replay/card", "/replay/reveal?calls=T", "/replay/score?calls=TS"):
        text = words(client.get(page).text)
        assert "₹" not in text and "%" not in text, page
        for word in ("skill", "rating:", "score:", "leaderboard"):
            assert word not in text.lower(), (page, word)


def test_playing_stores_nothing(client, bars, engine):  # noqa: F811
    send(client)
    before = rows(engine)
    for path in ("/replay", "/replay/card", "/replay/reveal?calls=T", "/replay/card?calls=T",
                 "/replay/score?calls=TS"):
        client.get(path)
    assert rows(engine) == before
