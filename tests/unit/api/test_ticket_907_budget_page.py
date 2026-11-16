"""TICKET-907 on /budget: his own history against a number he is considering [FB-0168..0171].

The page shows what his trades did against a number; it never recommends one. New words are
pending D9. Same synthetic tradebook as test_trades_past_number_upload, worked by hand. Six
positions, all same-day:

    14 Oct  spread +1300 (legs -600, +1900), +200     day +1500
    15 Oct  naked sale -500, +100                     day  -400   worst day
    16 Oct  +50, +50                                  day  +100

Against 400: one trade past it, 100 beyond. Against 500: none ("more than" is strict).
Running total 1500 -> 1100 -> 1200: deepest fall 400, 14 Oct to 15 Oct.
On capital 1,00,000, 400 is 0.4%: shown as 1%, never 0% for a part that is really there.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import select

from services.production.api import formatting
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import loader
from services.production.mirror import metrics as mx
from tests.unit.api.test_spread_upload import tradebook
from tests.unit.api.test_upload import (  # noqa: F401 - fixtures used by name
    CSRF,
    client,
    engine,
    upload,
)


def _record(client, **extra):  # noqa: F811
    token = CSRF.search(client.get("/budget").text).group(1)
    client.post(
        "/budget",
        data={
            "value": "400",
            "unit": "INR",
            "effective_from": "2026-10-14",
            "csrf_token": token,
            **extra,
        },
    )


@pytest.fixture()
def loaded(client):  # noqa: F811
    assert upload(client, content=tradebook()).status_code == 303
    _record(client)
    return client


@pytest.fixture()
def with_capital(client):  # noqa: F811
    assert upload(client, content=tradebook()).status_code == 303
    _record(client, capital_amount="100000")
    return client


def text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def trips_of(engine):  # noqa: F811
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        return loader.load_for(sess, trader)[0]


# ---------- FB-0168: the number against his own losses ----------


def test_a_number_he_tries_is_counted_against_his_trades(loaded):
    page = text(loaded.get("/budget?against=400").text)
    assert "1 of your 6 same-day trades lost more than ₹400." in page
    assert "The part past ₹400 came to ₹100." in page


def test_a_number_none_went_past_says_none(loaded):
    page = text(loaded.get("/budget?against=500").text)
    assert "None of your 6 same-day trades lost more than ₹500." in page
    assert "The part past" not in page


def test_the_slider_asks_for_the_same_words_without_a_page_load(loaded):
    fragment = loaded.get("/budget/against?against=400")
    assert fragment.status_code == 200
    assert "<html" not in fragment.text.lower()
    assert "1 of your 6 same-day trades lost more than ₹400." in text(fragment.text)


@pytest.mark.parametrize("bad", ["abc", "0", "-5", ""])
def test_a_number_that_is_not_one_reads_nothing(loaded, bad):
    page = loaded.get(f"/budget?against={bad}")
    assert page.status_code == 200
    assert "same-day trades lost more than" not in text(page.text)


def test_the_slider_is_drawn_over_his_own_losses(loaded, engine):  # noqa: F811
    html = loaded.get("/budget").text
    assert 'type="range"' in html and 'name="against"' in html
    assert 'hx-get="/budget/against"' in html
    assert 'method="get" action="/budget"' in html  # works with no script
    strip = re.search(r'<svg class="against__losses".*?</svg>', html, re.DOTALL).group(0)
    losses = [t for t in mx.same_day_trips(trips_of(engine)) if t.is_loss]
    assert strip.count("<rect") == len(losses)


def test_points_per_lot_for_each_instrument_he_trades(loaded, engine):  # noqa: F811
    page = text(loaded.get("/budget?against=400").text)
    rows = mx.points_per_lot(trips_of(engine), mx.Decimal("400"))
    assert rows, "the tradebook's instrument has a profile"
    for row in rows:
        assert f"On one lot, ₹400 is {formatting.price(row.points)} points of {row.symbol}." in page


# ---------- FB-0170: capital as a share ----------


def test_his_worst_day_as_a_share_of_his_capital(with_capital):
    page = text(with_capital.get("/budget").text)
    assert re.search(
        r"Your worst day, 15 Oct \d{4}, ended at −₹400\. That is 1% of your capital\.", page
    )


def test_his_deepest_fall_as_a_share_of_his_capital(with_capital):
    page = text(with_capital.get("/budget").text)
    assert re.search(
        r"Your deepest fall, from 14 Oct \d{4} to 15 Oct \d{4}, was ₹400\. "
        r"That is 1% of your capital\.",
        page,
    )


def test_his_biggest_premium_is_shown_when_he_bought_an_option(with_capital, engine):  # noqa: F811
    shares = mx.capital_shares(trips_of(engine), mx.Decimal("100000"))
    page = text(with_capital.get("/budget").text)
    if shares.premium:
        assert (
            f"Your biggest premium on one option was {formatting.rupees(shares.premium, signed=False)}. "
            f"That is {shares.premium_percent}% of your capital."
        ) in page
    else:
        assert "biggest premium" not in page


def test_with_no_capital_the_page_says_how_to_see_the_shares(loaded):
    page = text(loaded.get("/budget").text)
    assert "Enter your trading capital above to see these as a share of it." in page
    assert "% of your capital" not in page


# ---------- FB-0171: what recording does ----------


def test_the_page_says_plainly_what_recording_does(loaded):
    page = text(loaded.get("/budget").text)
    assert "Recording a number keeps the number and nothing else." in page
    assert "It does not and cannot stop a trade, and nothing here reaches your broker." in page
    assert "Each time you upload, the trades past it are counted again." in page


# ---------- the standing rule ----------


@pytest.mark.parametrize("path", ["/budget", "/budget?against=400", "/budget/against?against=400"])
def test_nothing_on_the_page_is_labelled_saved_avoided_kept_or_recommended(with_capital, path):
    page = text(with_capital.get(path).text).lower()
    for word in ("saved", "avoided", "kept", "recommend", "you should", "suggested"):
        assert not re.search(rf"\b{word}\b", page), word
