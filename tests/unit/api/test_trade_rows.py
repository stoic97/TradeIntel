"""A trade row names the trade, and a long list sits behind "See all trades" [TICKET-822].

Through a real upload. Synthetic rows, worked by hand, a unit of 100 unless it says:

  A  19 Nov 2026 09:30-09:40  bought 5000 CE at 10, sold at 12.50. Paid 1,000, made +250,
     which is +25.0% of it. Expiry day (0 days). Entry price under 50.
  B  17 Nov 2026 14:00-14:20  bought 5000 PE at 120, sold at 114. Paid 12,000, lost -600,
     which is -5.0% of it. 2 days to expiry. Entry price 100-150.
  C  15 Oct 2026 10:00-11:00  sold 5200 CE at 20, bought back at 25: -500. Paid nothing.
     35 days to expiry.
  D  14 Oct 2026 09:30:00 bought 5100 CE at 10, 15:00:00 sold at 4: -600.
     14 Oct 2026 09:30:05 sold 5000 CE at 30, 15:00:05 bought at 11: +1,900.
     One position, +1,300. A spread's cost is not a premium.
  E  03 Nov 2025 11:00-11:30  bought 5400 CE at 60, sold at 70. Paid 6,000, made +1,000,
     which is +16.7% of it. 16 days to expiry. Entry price 50-100. The only 2025 trade.
  F  20 Oct 2026 10:00 to 28 Oct 2026 10:00  10 of Widget ETF at 100, sold at 110: +100.
     Held past the day, a share, no premium.

Six trades in the record's reading: A, D, E and F made money, B and C lost.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from services.production.api import formatting
from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import loader
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_scope_chapters import TRIPS, trips_from
from tests.unit.api.test_scope_facts import fact_page
from tests.unit.api.test_upload import (  # noqa: F401 - fixtures used by name
    DUPES,
    client,
    engine,
    upload,
)

OPENED = datetime.fromisoformat("2026-11-19T09:30:00+05:30")
CLOSED = datetime.fromisoformat("2026-11-19T09:40:00+05:30")

OPTION_ROWS = [
    ("2026-11-19", "09:30:00", 5000, "CALL", "BUY", "10.00"),
    ("2026-11-19", "09:40:00", 5000, "CALL", "SELL", "12.50"),
    ("2026-11-17", "14:00:00", 5000, "PUT", "BUY", "120.00"),
    ("2026-11-17", "14:20:00", 5000, "PUT", "SELL", "114.00"),
    ("2026-10-15", "10:00:00", 5200, "CALL", "SELL", "20.00"),
    ("2026-10-15", "11:00:00", 5200, "CALL", "BUY", "25.00"),
    ("2026-10-14", "09:30:00", 5100, "CALL", "BUY", "10.00"),
    ("2026-10-14", "09:30:05", 5000, "CALL", "SELL", "30.00"),
    ("2026-10-14", "15:00:00", 5100, "CALL", "SELL", "4.00"),
    ("2026-10-14", "15:00:05", 5000, "CALL", "BUY", "11.00"),
    ("2025-11-03", "11:00:00", 5400, "CALL", "BUY", "60.00"),
    ("2025-11-03", "11:30:00", 5400, "CALL", "SELL", "70.00"),
]
SHARE_ROWS = [
    ("2026-10-20", "10:00:00", "BUY", "100.00"),
    ("2026-10-28", "10:00:00", "SELL", "110.00"),
]


def tradebook(extra: tuple[str, ...] = ()) -> bytes:
    header = (DUPES / "clean.csv").read_text().splitlines()[0]
    options = [
        f"{day},{time},WIDGETOIL 19 NOV {strike} {kind},{side},INTRADAY,MCX,Commodity,100,"
        f"{price},{Decimal(price) * 100:.2f},Traded"
        for day, time, strike, kind, side, price in OPTION_ROWS
    ]
    shares = [
        f"{day},{time},Widget ETF,{side},DELIVERY,NSE,Equity,10,{price},"
        f"{Decimal(price) * 10:.2f},Traded"
        for day, time, side, price in SHARE_ROWS
    ]
    return ("\n".join([header, *options, *shares, *extra]) + "\n").encode()


@pytest.fixture()
def uploaded(client, engine):  # noqa: F811
    response = upload(client, content=tradebook())
    assert response.status_code == 303
    return client


def text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).replace("&#39;", "'").split())


def articles(html: str) -> list[str]:
    """Each trade on a page, as a reader reads it."""
    return [text(a) for a in re.findall(r'<article class="trade">.*?</article>', html, re.DOTALL)]


def row_for(html: str, instrument: str) -> str:
    return next(a for a in articles(html) if a.startswith(instrument))


def strike_list(client, query: str = "") -> str:  # noqa: F811
    got = client.get(f"/mirror/fact/strike/trades{query}")
    assert got.status_code == 200
    return got.text


# ---------- The row names the trade ----------


def test_a_row_says_instrument_side_quantity_prices_and_rupees(uploaded):
    row = row_for(strike_list(uploaded), "WIDGETOIL 5000 CE")
    assert row.startswith("WIDGETOIL 5000 CE · Buy · Qty 100")
    assert "09:30 09:40" in row
    assert "10.00 → 12.50" in row
    assert "+₹250" in row


def test_a_row_carries_the_day_with_or_without_its_year(uploaded):
    row = row_for(strike_list(uploaded), "WIDGETOIL 5000 CE")
    assert formatting.day("2026-11-19") in row


def test_a_bought_option_shows_what_was_paid_and_the_result_against_it(uploaded):
    page = strike_list(uploaded)
    winner = row_for(page, "WIDGETOIL 5000 CE")
    assert "Paid ₹1,000" in winner and "+25.0% of premium" in winner
    loser = row_for(page, "WIDGETOIL 5000 PE")
    assert "Paid ₹12,000" in loser and "−5.0% of premium" in loser


def test_a_sold_option_paid_no_premium(uploaded):
    row = row_for(strike_list(uploaded), "WIDGETOIL 5200 CE")
    assert row.startswith("WIDGETOIL 5200 CE · Sell · Qty 100")
    assert "20.00 → 25.00" in row
    assert "Paid" not in row and "premium" not in row


def test_a_spread_is_one_row_with_its_legs(uploaded):
    page = strike_list(uploaded)
    assert len(articles(page)) == 6  # seven legs would be seven rows
    row = row_for(page, "WIDGETOIL · 2 legs")
    assert "+₹1,300" in row
    assert "Bought 5100 CE −₹600" in row and "Qty 100 · 10.00 → 4.00" in row
    assert "Sold 5000 CE +₹1,900" in row and "Qty 100 · 30.00 → 11.00" in row
    assert "Paid" not in row  # a spread's cost is not a premium


def test_a_share_shows_side_quantity_and_prices_with_no_strike_or_premium(uploaded):
    row = row_for(strike_list(uploaded), "Widget ETF")
    assert row.startswith("Widget ETF · Buy · Qty 10")
    assert "100.00 → 110.00" in row
    assert "Paid" not in row


def test_a_row_with_no_detail_still_names_its_instrument():
    """A trip with no legs on record (the contract fixture) falls back to the symbol."""
    got = S.trade(trips_from([100])[0], 1)
    assert got["instrument"] == "WIDGETOIL"
    assert got["side"] is None and got["paid"] is None


def test_the_internal_trade_number_is_not_on_the_page(uploaded):
    page = strike_list(uploaded)
    assert not re.search(r"Trade \d+", text(page))


def test_the_unexplained_bar_is_gone(uploaded):
    assert "trade__strip" not in strike_list(uploaded)


def test_premium_is_recorded_and_never_a_denominator_for_a_stock():
    line = mx.TradeLine(symbol="Widget ETF", segment="EQ", side="Buy", quantity=10,
                        entry_price=Decimal(100), exit_price=Decimal(110), net=Decimal(100))
    assert line.paid is None
    assert line.instrument == "Widget ETF"


def test_the_paid_and_percent_are_worked_from_price_and_quantity():
    line = mx.TradeLine(symbol="WIDGETOIL", segment="OPT", side="Buy", quantity=100,
                        entry_price=Decimal("10.00"), exit_price=Decimal("12.50"),
                        net=Decimal(250), strike=Decimal("5000.00"), option_type="CE")
    assert line.instrument == "WIDGETOIL 5000 CE"
    assert line.paid == Decimal(1000)
    trip = mx.Trip("t", "WIDGETOIL", "2026-11-19", OPENED,
                   CLOSED, 600, Decimal(250), 1,
                   s.RiskUnitSourceV1.PREMIUM_PAID, lines=(line,))
    assert trip.paid == Decimal(1000)
    assert trip.result_percent == Decimal("25.0")


# ---------- How the new figures are written ----------


@pytest.mark.parametrize(
    ("value", "want"),
    [(Decimal(10), "10.00"), (Decimal("135.204"), "135.20"), (Decimal("2345.5"), "2,345.50")],
)
def test_a_price_is_written_with_its_paise(value, want):
    assert formatting.price(value) == want


@pytest.mark.parametrize(
    ("value", "want"),
    [(Decimal("25.0"), "+25.0%"), (Decimal("-5.0"), "−5.0%"), (Decimal("0.0"), "0.0%")],
)
def test_a_result_against_premium_carries_its_sign(value, want):
    assert formatting.signed_percent(value) == want


@pytest.mark.parametrize(
    ("value", "want"),
    [(Decimal("0.96"), "+₹0.96"), (Decimal("-0.40"), "−₹0.40"), (Decimal("250.75"), "+₹250"),
     (Decimal(0), "₹0")],
)
def test_a_result_under_a_rupee_on_one_trade_keeps_its_paise(value, want):
    assert formatting.rupees_on_a_trade(value) == want


# ---------- Long lists sit behind the link ----------


def test_a_long_list_is_not_on_the_fact_page():
    behind = S.trades_behind("strike", SF.record_context(TRIPS))
    assert len(behind) > S.INLINE_TRADES
    page = fact_page("strike")
    assert '<article class="trade">' not in page
    assert 'href="/mirror/fact/strike/trades"' in page
    assert "See all trades" in page


def test_the_fact_page_still_says_how_many_trades_are_behind_it():
    page = fact_page("strike")
    caption = re.search(r'<p class="evidence__caption">(.*?)</p>', page, re.DOTALL)[1]
    assert text(caption).endswith(f"{len(TRIPS)} trades.")


def test_a_short_list_stays_on_the_fact_page_with_no_link():
    trips = trips_from([100, -50, 25])
    page = fact_page("strike", trips=trips)
    assert page.count('<article class="trade">') == 3
    assert "See all trades" not in page


def test_a_list_of_exactly_the_limit_stays_on_the_page():
    trips = trips_from([100] * S.INLINE_TRADES)
    assert fact_page("strike", trips=trips).count('<article class="trade">') == S.INLINE_TRADES
    over = trips_from([100] * (S.INLINE_TRADES + 1))
    assert '<article class="trade">' not in fact_page("strike", trips=over)


def test_every_trade_behind_a_long_fact_is_reachable_through_the_link(client, engine):  # noqa: F811
    """Handoff: every trade, never a sample. The link takes nothing away."""
    contract = "WIDGETOIL 19 NOV 5000 CALL"
    tail = "INTRADAY,MCX,Commodity,100"
    many = tuple(
        line
        for i in range(S.INLINE_TRADES + 1)
        for line in (
            f"2026-09-{(i % 28) + 1:02d},10:{i:02d}:00,{contract},BUY,{tail},10.00,1000.00,Traded",
            f"2026-09-{(i % 28) + 1:02d},10:{i:02d}:30,{contract},SELL,{tail},11.00,1100.00,Traded",
        )
    )
    assert upload(client, content=tradebook(many)).status_code == 303
    fact = client.get("/mirror/fact/strike").text
    assert '<article class="trade">' not in fact
    assert len(articles(strike_list(client))) == S.INLINE_TRADES + 1 + 6


# ---------- The list's route ----------


@pytest.mark.parametrize("key", ["unread", "not-told", "nothing-here"])
def test_only_a_fact_with_trades_has_a_list(uploaded, key):
    assert uploaded.get(f"/mirror/fact/{key}/trades").status_code == 404


def test_the_list_is_signed_in_only(engine):  # noqa: F811
    from fastapi.testclient import TestClient

    from services.production.api.app import create_app

    anonymous = TestClient(create_app())
    got = anonymous.get("/mirror/fact/strike/trades", follow_redirects=False)
    assert got.status_code == 303 and got.headers["location"] == "/login"


def test_the_list_says_which_fact_it_belongs_to_and_goes_back_to_it(uploaded):
    page = strike_list(uploaded)
    assert "The trades behind this" in page
    assert 'href="/mirror/fact/strike"' in page
    assert "Strike rate" in page


def test_the_list_says_its_figures_are_gross_as_the_fact_page_does(uploaded):
    assert "every rupee figure below is gross" in strike_list(uploaded)


# ---------- The filters ----------

NAMES = ("5000 CE", "5000 PE", "5200 CE", "2 legs", "5400 CE", "ETF")


@pytest.mark.parametrize(
    ("query", "want"),
    [
        ("", {"5000 CE", "5000 PE", "5200 CE", "2 legs", "5400 CE", "ETF"}),
        ("?book=Crude+options", None),
        ("?book=WIDGETOIL+options", {"5000 CE", "5000 PE", "5200 CE", "2 legs", "5400 CE"}),
        ("?book=Stocks+and+ETFs", {"ETF"}),
        ("?result=winners", {"5000 CE", "2 legs", "5400 CE", "ETF"}),
        ("?result=losers", {"5000 PE", "5200 CE"}),
        ("?price=under-50", {"5000 CE", "5200 CE"}),  # C was opened at 20, by selling
        ("?price=50-100", {"5400 CE"}),
        ("?price=100-150", {"5000 PE"}),
        ("?dte=expiry-day", {"5000 CE"}),
        ("?dte=1-3", {"5000 PE"}),
        ("?dte=8-plus", {"5200 CE", "2 legs", "5400 CE"}),
        ("?hour=14", {"5000 PE"}),
        ("?hour=9", {"5000 CE", "2 legs"}),
        ("?year=2025", {"5400 CE"}),
        ("?year=2026&result=losers&hour=14", {"5000 PE"}),
    ],
)
def test_each_filter_narrows_the_list(uploaded, query, want):
    rows = articles(strike_list(uploaded, query))
    if want is None:  # a book this history doesn't have is ignored, not an empty page
        assert len(rows) == 6
        return
    names = {next(n for n in NAMES if n in row[:24]) for row in rows}
    assert names == want


def test_a_sold_option_is_in_the_price_band_of_what_it_was_sold_at(uploaded):
    """Entry price is the price the trade was opened at, bought or sold."""
    names = articles(strike_list(uploaded, "?price=under-50"))
    assert any(n.startswith("WIDGETOIL 5200 CE") for n in names)


def test_a_share_is_in_no_entry_price_band(uploaded):
    """A share's price says nothing about an option's: the bands are for options."""
    for band in ("under-50", "50-100", "100-150", "150-250", "250-plus"):
        assert not any(n.startswith("Widget ETF") for n in
                       articles(strike_list(uploaded, f"?price={band}")))


def test_a_spread_is_in_no_entry_price_band(uploaded):
    """Its legs have a price each; the position has none."""
    for band in ("under-50", "50-100", "100-150", "150-250", "250-plus"):
        assert not any("2 legs" in n for n in articles(strike_list(uploaded, f"?price={band}")))


def test_an_unknown_filter_value_is_ignored_rather_than_refused(uploaded):
    for query in ("?hour=99", "?hour=noon", "?price=free", "?dte=-1", "?result=maybe", "?year=1"):
        assert len(articles(strike_list(uploaded, query))) == 6


def test_no_match_says_so_and_offers_the_way_back(uploaded):
    page = strike_list(uploaded, "?year=2025&result=losers")
    assert articles(page) == []
    assert "No trades match these filters." in page
    assert 'href="/mirror/fact/strike/trades"' in page


def test_the_count_says_how_many_of_how_many(uploaded):
    assert "1 of 6 trades." in text(strike_list(uploaded, "?year=2025"))
    assert "6 trades." in text(strike_list(uploaded))


def test_the_form_keeps_what_was_chosen(uploaded):
    page = strike_list(uploaded, "?result=losers")
    assert '<option value="losers" selected>Losers</option>' in page


def test_the_form_offers_all_six_filters_when_each_has_a_choice(uploaded):
    page = strike_list(uploaded)
    for name in ("book", "result", "price", "dte", "hour", "year"):
        assert f'name="{name}"' in page


def test_a_filter_with_nothing_to_choose_between_is_left_off(client, engine):  # noqa: F811
    header = (DUPES / "clean.csv").read_text().splitlines()[0]
    rows = [
        "2026-11-17,09:30:00,WIDGETOIL 19 NOV 5000 CALL,BUY,INTRADAY,MCX,Commodity,100,10.00,1000.00,Traded",
        "2026-11-17,09:40:00,WIDGETOIL 19 NOV 5000 CALL,SELL,INTRADAY,MCX,Commodity,100,12.00,1200.00,Traded",
    ]
    assert upload(client, content=("\n".join([header, *rows]) + "\n").encode()).status_code == 303
    page = client.get("/mirror/fact/strike/trades").text
    assert 'name="year"' not in page and 'name="book"' not in page


def test_a_link_can_arrive_with_a_filter_already_chosen():
    """What the clock and Chapter 3 tickets link to."""
    assert S.see_all_href("clock", hour=18) == "/mirror/fact/clock/trades?hour=18"
    assert S.see_all_href("down", book="Crude options", year=2026) == (
        "/mirror/fact/down/trades?book=Crude+options&year=2026"
    )


# ---------- Which trades ----------


def test_a_holding_stays_out_of_the_same_day_lists(uploaded):
    for key in ("hold", "clock"):
        page = uploaded.get(f"/mirror/fact/{key}/trades").text
        assert not any(a.startswith("Widget ETF") for a in articles(page)), key


def test_a_holding_is_reachable_where_the_fact_counts_it(uploaded):
    page = uploaded.get("/mirror/fact/risk/trades").text
    assert any(a.startswith("Widget ETF") for a in articles(page))


# ---------- The book ----------


@pytest.mark.parametrize(
    ("symbol", "segment", "want"),
    [
        ("CRUDEOIL", "OPT", "Crude options"),
        ("CRUDEOILM", "OPT", "Crude options"),
        ("NIFTY", "OPT", "NIFTY options"),
        ("Widget ETF", "EQ", "Stocks and ETFs"),
        ("NIFTY", "FUT", "Futures"),
    ],
)
def test_one_definition_of_a_book(symbol, segment, want):
    line = mx.TradeLine(symbol=symbol, segment=segment, side="Buy", quantity=1,
                        entry_price=Decimal(1), exit_price=Decimal(1), net=Decimal(0))
    trip = mx.Trip("t", symbol, "2026-11-19", OPENED,
                   CLOSED, 600, Decimal(0), 1,
                   s.RiskUnitSourceV1.UNAVAILABLE, is_option=segment == "OPT", lines=(line,))
    assert mx.trade_book(trip) == want


# ---------- The expiry, with no new column ----------


def test_the_expiry_is_read_from_the_rows_already_stored(uploaded, engine):  # noqa: F811
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        trips, imp = loader.load_for(sess, trader)
        expiries = loader.expiries_for(sess, imp)
    first = next(t for t in trips if t.trading_day == "2026-11-19")
    assert expiries[loader.expiry_key(first.lines[0])] == date(2026, 11, 19)
    last_year = next(t for t in trips if t.trading_day == "2025-11-03")
    assert expiries[loader.expiry_key(last_year.lines[0])] == date(2025, 11, 19)
