"""A declared day limit, and the three counts either side of it (TICKET-974).

Once a trader has declared a day limit, /budget shows three counts from trades that happened:
how many days went past it, what those days ended at, and what the trades after the line came
to. Never a replay: nothing says what he would have kept, and no word on the page says saved,
avoided or kept. New words are pending D9.

The rulings (25 Nov 2026) the fixture is worked from:
  - a day is measured on its NET; "past" is strict, a day that ends exactly on the limit is not;
  - realised trades only (an open position is not a trade here);
  - the trading day is the ENTRY date (definitions_v1 section 1);
  - the limit in force is the one declared at that trading day (section 5);
  - a declaration counts only from its declared day, never before it: trades before are not
    counted and not shown as "would have".
"The part after the line": in exit order, the day's running net first falls past the limit at
one trade; the trades that close after it are the part after the line.

Synthetic tradebook, worked by hand (every pair is one single-leg trade, net = price move x 100).
Limit Rs 1,000, declared on 15 Oct 2026:

    13 Oct  -1500                                        before the declaration: not counted
    15 Oct  -400, -700 (running -1100: past), +200, -400  day -1300  PAST   after the line -200
    16 Oct  -400, -600                                   day -1000  exactly on it: not past
    19 Oct  +500                                         day  +500
    20 Oct  -1200 (past mid-day), +300                   day  -900  recovered: not past
    21 Oct  -500, -700 (running -1200), -300, and one
            fill never closed (open: ignored)            day -1500  PAST   after the line -300

Counted days: 15, 16, 19, 20, 21. Past: 15 Oct and 21 Oct. Two days. Ended at -1300 + -1500 =
-2800 between them. After the line: -200 + -300 = -500.

A second limit of Rs 1,500 declared on 21 Oct leaves 15 Oct on Rs 1,000 and puts 21 Oct on
Rs 1,500, which -1500 does not go past: one day, -1300, after the line -200.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from services.production.api.routes_budget import _today
from services.production.db import models as m
from services.production.db.session import make_session
from tests.helpers.upload import CSRF, DUPES, upload

ROWS = [
    ("2026-10-13", "09:30:00", 5000, "BUY", "20.00"), ("2026-10-13", "10:00:00", 5000, "SELL", "5.00"),
    ("2026-10-15", "09:30:00", 5101, "BUY", "10.00"), ("2026-10-15", "10:00:00", 5101, "SELL", "6.00"),
    ("2026-10-15", "10:30:00", 5102, "BUY", "8.00"), ("2026-10-15", "11:00:00", 5102, "SELL", "1.00"),
    ("2026-10-15", "11:30:00", 5103, "BUY", "3.00"), ("2026-10-15", "12:00:00", 5103, "SELL", "5.00"),
    ("2026-10-15", "12:30:00", 5104, "SELL", "10.00"), ("2026-10-15", "13:00:00", 5104, "BUY", "14.00"),
    ("2026-10-16", "09:30:00", 5201, "BUY", "9.00"), ("2026-10-16", "10:00:00", 5201, "SELL", "5.00"),
    ("2026-10-16", "10:30:00", 5202, "BUY", "8.00"), ("2026-10-16", "11:00:00", 5202, "SELL", "2.00"),
    ("2026-10-19", "09:30:00", 5301, "BUY", "5.00"), ("2026-10-19", "10:00:00", 5301, "SELL", "10.00"),
    ("2026-10-20", "09:30:00", 5401, "BUY", "14.00"), ("2026-10-20", "10:00:00", 5401, "SELL", "2.00"),
    ("2026-10-20", "10:30:00", 5402, "BUY", "6.00"), ("2026-10-20", "11:00:00", 5402, "SELL", "9.00"),
    ("2026-10-21", "09:30:00", 5501, "BUY", "10.00"), ("2026-10-21", "10:00:00", 5501, "SELL", "5.00"),
    ("2026-10-21", "10:30:00", 5502, "BUY", "9.00"), ("2026-10-21", "11:00:00", 5502, "SELL", "2.00"),
    ("2026-10-21", "11:30:00", 5503, "BUY", "6.00"), ("2026-10-21", "12:00:00", 5503, "SELL", "3.00"),
    ("2026-10-21", "14:00:00", 5504, "BUY", "4.00"),  # never closed: an open position
]


def tradebook() -> bytes:
    header = (DUPES / "clean.csv").read_text().splitlines()[0]
    lines = [
        f"{day},{time},WIDGETOIL 19 NOV {strike} CALL,{side},INTRADAY,MCX,Commodity,100,"
        f"{price},{Decimal(price) * 100:.2f},Traded"
        for day, time, strike, side, price in ROWS
    ]
    return ("\n".join([header, *lines]) + "\n").encode()


def text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).replace("&#39;", "'").split())


def section(html: str) -> str:
    """The day-limit block of /budget, as words. Missing is an empty string, which fails."""
    found = re.search(r'<section[^>]*id="day-limit".*?</section>', html, re.DOTALL)
    return text(found.group(0)) if found else ""


def declare(engine, amount: str, day: str) -> None:
    """A declaration made on `day` at 09:00 India time, counted from that day."""
    model = getattr(m, "DayLimitDeclaration", None)
    assert model is not None, "there is no day-limit declaration to store yet"
    year, month, dom = (int(p) for p in day.split("-"))
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        sess.add(model(trader_id=trader.id, value=Decimal(amount), effective_from=day,
                       declared_at=datetime(year, month, dom, 3, 30, tzinfo=UTC)))
        sess.commit()


@pytest.fixture()
def loaded(client):
    assert upload(client, content=tradebook()).status_code == 303
    return client


@pytest.fixture()
def limited(loaded, engine):
    declare(engine, "1000", "2026-10-15")
    return loaded


# ---------- gate 3: the three counts, from the fixture worked by hand ----------


def test_the_three_counts_read_off_the_trades_that_happened(limited):
    block = section(limited.get("/budget").text)
    assert "2 days went past your day limit." in block
    assert "Those days ended at −₹2,800 between them." in block
    assert "The trades after the line came to −₹500." in block


def test_the_page_says_where_the_counting_starts(limited):
    assert "Counted from 15 Oct 2026, the day you set it." in section(limited.get("/budget").text)


def test_a_day_that_ends_exactly_on_the_limit_is_not_past_it(limited):
    # 16 Oct ends at -1000. If it were counted the page would read 3 days.
    assert "3 days went past" not in section(limited.get("/budget").text)


def test_a_day_that_fell_past_it_and_came_back_is_not_counted(limited):
    # 20 Oct touched -1200 and ended at -900: the day is measured on its net.
    assert "3 days went past" not in section(limited.get("/budget").text)
    assert "−₹3,700" not in section(limited.get("/budget").text)


def test_trades_before_the_declared_day_are_not_counted_or_shown(limited):
    block = section(limited.get("/budget").text)
    assert "13 Oct" not in block
    assert "−₹1,500" not in block  # 13 Oct's day, which no limit covered


def test_the_open_position_is_not_a_trade_here(limited, engine):
    with make_session(engine) as sess:
        assert len(sess.scalars(select(m.OpenPosition)).all()) == 1
    assert "−₹500." in section(limited.get("/budget").text)  # 21 Oct's after-the-line, unchanged


def test_the_limit_in_force_is_the_one_declared_at_that_trading_day(limited, engine):
    declare(engine, "1500", "2026-10-21")
    block = section(limited.get("/budget").text)
    assert "1 day went past your day limit." in block
    assert "Those days ended at −₹1,300 between them." in block
    assert "The trades after the line came to −₹200." in block
    assert "Counted from 15 Oct 2026, the day you set it." in block


# ---------- the states: never a zero ----------


def test_with_no_limit_each_count_says_why_it_has_no_figure(loaded):
    block = section(loaded.get("/budget").text)
    assert "No day limit is set" in block
    assert not re.search(r"(?<![\d,.])0 days|₹0\b", block)
    assert "went past your day limit" not in block
    assert "Counted from" not in block


def test_a_limit_with_no_day_counted_yet_says_so(loaded, engine):
    declare(engine, "1000", "2026-10-22")
    block = section(loaded.get("/budget").text)
    assert "No trading day on or after 22 Oct 2026 is in your file yet" in block
    assert "Counted from 22 Oct 2026, the day you set it." in block
    assert not re.search(r"(?<![\d,.])0 days|₹0\b", block)


def test_a_limit_with_days_counted_and_none_past_says_no_day(loaded, engine):
    declare(engine, "5000", "2026-10-15")
    block = section(loaded.get("/budget").text)
    assert "No day went past your day limit." in block
    assert not re.search(r"(?<![\d,.])0 days|₹0\b", block)


# ---------- gate 2: declared and stored, with its history ----------


def post_limit(client, value, **extra):
    token = CSRF.search(client.get("/budget").text).group(1)
    return client.post("/budget/day-limit", data={"value": value, "csrf_token": token, **extra},
                       follow_redirects=False)


def rows(engine):
    model = getattr(m, "DayLimitDeclaration", None)
    assert model is not None, "there is no day-limit declaration to store yet"
    with make_session(engine) as sess:
        return sess.scalars(select(model).order_by(model.id)).all()


def test_a_day_limit_can_be_declared_and_is_stored(loaded, engine):
    assert post_limit(loaded, "1000").status_code == 303
    [row] = rows(engine)
    assert row.value == Decimal(1000)
    assert row.effective_from == _today().isoformat()
    assert row.declared_at.date() >= datetime.now(UTC).date()


def test_it_can_never_take_an_effective_date_before_the_day_it_was_declared(loaded, engine):
    post_limit(loaded, "1000", effective_from="2026-10-01")
    [row] = rows(engine)
    assert row.effective_from == _today().isoformat()


def test_a_new_limit_is_a_new_line_and_the_old_one_stays(loaded, engine):
    post_limit(loaded, "1000")
    post_limit(loaded, "2000")
    assert [r.value for r in rows(engine)] == [Decimal(1000), Decimal(2000)]
    assert "Nothing here is overwritten" in text(loaded.get("/budget").text)


@pytest.mark.parametrize("bad", ["abc", "0", "-5", ""])
def test_a_number_that_is_not_one_above_zero_is_refused(loaded, engine, bad):
    assert post_limit(loaded, bad).status_code == 400
    assert rows(engine) == []


def test_declaring_needs_the_form_token(loaded, engine):
    assert loaded.post("/budget/day-limit", data={"value": "1000"}).status_code == 403
    assert rows(engine) == []


def test_the_form_works_with_no_script(loaded):
    html = loaded.get("/budget").text
    assert re.search(r'<form[^>]*method="post"[^>]*action="/budget/day-limit"', html)


# ---------- never a replay ----------

REPLAY = ("saved", "avoided", "kept", "would have", "if you had", "stopped", "had you")


def test_no_word_of_a_replay_anywhere_in_the_day_limit_block(loaded, limited):
    block = section(limited.get("/budget").text).lower()
    assert block, "the day-limit block is on the page"
    assert not [w for w in REPLAY if w in block]


def test_no_replay_words_in_the_no_limit_state_either(loaded):
    block = section(loaded.get("/budget").text).lower()
    assert block, "the day-limit block is on the page"
    assert not [w for w in REPLAY if w in block]
