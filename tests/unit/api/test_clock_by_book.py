"""One clock per book, with ₹, trades, ₹ per trade and win rate per hour [TICKET-821].

Two markets with different hours were averaged into one row of bars. Ruled on the ticket: an
hour with fewer than 30 same-day trades shows ₹ and the count but no win rate; ₹ per trade
shows at any count; the headline says what happened, never "your best hour".

Worked by hand from clock_by_book.json, a made-up history. Same-day trades only:

  WIDGETOIL options, 132 trades, -13,850
    18:00  29 trades  10 x +100, 19 x -300            -4,700  -162.07 each  no win rate
    19:00  30 trades  12 x +200, 17 x -100, 1 level     +700   +23.33 each  12 / 29 = 41.4%
    20:00  40 trades  10 x +50,  30 x -200            -5,500  -137.50 each  10 / 40 = 25%
    21:00  30 trades   5 x +100, 25 x -200            -4,500  -150.00 each   5 / 30 = 16.7%
    22:00   3 trades   3 x +50                          +150   +50.00 each  no win rate, few
  WIDGETIDX options, 63 trades, +3,700
    09:00   4 trades   2 x +500, 2 x -100               +800  +200.00 each  no win rate, few
    10:00  30 trades  15 x +300, 15 x -100            +3,000  +100.00 each  15 / 30 = 50%
    18:00  29 trades   9 x +100, 20 x -50               -100    -3.45 each  no win rate
  WIDGETGOLD options, 2 trades, +40
    11:00   2 trades   1 x +60, 1 x -20                  +40   +20.00 each  no win rate, few

A WIDGETIDX position opened at 10:20 and held to the next day made +9,000. It is on no clock.

18:00 is in both of the big books at 29 trades: pooled it would be 58 and would show a rate.
21:00 is larger than 20:00 per trade, and 18:00 larger still, but on 29 trades.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from html import unescape
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from services.production.api import scope_facts as SF
from services.production.api import scope_geometry as G
from services.production.api import scope_map as S
from services.production.api import trade_list as TL
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_scope_chapters import IMP, chapter_page, readable, trips_from
from tests.unit.api.test_scope_facts import fact_page

TRIPS = mx.load_trips(
    json.loads(Path("tests/fixtures/mirror_contract/clock_by_book.json").read_text())
)
OIL, IDX, GOLD = "WIDGETOIL options", "WIDGETIDX options", "WIDGETGOLD options"
CTX = SF.record_context(TRIPS)
FIG = SF.facts(CTX, IMP)["clock"]
PAGE = readable(fact_page("clock", TRIPS))


def clock(book: str) -> mx.BookClock:
    return next(c for c in CTX["clocks"] if c.book == book)


def cell(book: str, hour: int) -> mx.ClockHour:
    return next(h for h in clock(book).hours if h.hour == hour)


# ---------- The figures ----------


def test_each_book_has_its_own_clock_most_trades_first():
    assert [(c.book, c.trips, c.net) for c in CTX["clocks"]] == [
        (OIL, 132, Decimal(-13850)),
        (IDX, 63, Decimal(3700)),
        (GOLD, 2, Decimal(40)),
    ]


@pytest.mark.parametrize(
    ("book", "hour", "net", "trips"),
    [
        (OIL, 18, -4700, 29),
        (OIL, 19, 700, 30),
        (OIL, 20, -5500, 40),
        (OIL, 21, -4500, 30),
        (OIL, 22, 150, 3),
        (IDX, 9, 800, 4),
        (IDX, 10, 3000, 30),
        (IDX, 18, -100, 29),
        (GOLD, 11, 40, 2),
    ],
)
def test_an_hour_has_its_result_its_trades_and_its_result_per_trade(book, hour, net, trips):
    h = cell(book, hour)
    assert (h.net, h.trips) == (Decimal(net), trips)
    assert h.per_trade == Decimal(net) / trips


def test_an_hour_in_two_books_stays_two_hours():
    assert (cell(OIL, 18).trips, cell(IDX, 18).trips) == (29, 29)


def test_thirds_of_a_fill_add_back_to_the_rupee_they_came_from():
    """A fill split across parcels is exact only to Decimal's precision. Three thirds of -100
    sum to -99.99...9, and the whole-rupee cut would print a rupee less than the broker's."""
    third = Decimal(-100) / 3
    base = [t for t in TRIPS if t.symbol == "WIDGETOIL" and t.entry_ts.hour == 18][:3]
    book = mx.clocks_by_book([replace(t, net=third) for t in base])[0]
    assert book.hours[0].net == Decimal(-100)
    assert book.net == Decimal(-100)
    assert book.hours[0].per_trade == Decimal(-100) / 3


def test_the_held_position_is_on_no_clock():
    assert sum(c.trips for c in CTX["clocks"]) == len(mx.same_day_trips(TRIPS)) == 197
    assert cell(IDX, 10).net == Decimal(3000)


def test_29_trades_shows_no_win_rate():
    h = cell(OIL, 18)
    assert h.win_rate is None
    assert h.win_rate_state is s.ResultState.INSUFFICIENT_SAMPLE


def test_30_trades_shows_a_win_rate():
    h = cell(IDX, 10)
    assert h.win_rate == Decimal(50)
    assert h.win_rate_state is s.ResultState.COUNTED_FACT


def test_win_rate_leaves_out_a_trade_that_finished_level():
    """Thirty trades, so it shows; twelve wins over twenty-nine, as strike_rate reads them."""
    assert cell(OIL, 19).win_rate == mx.strike_rate(
        [t for t in TRIPS if t.symbol == "WIDGETOIL" and t.entry_ts.hour == 19]
    ).rate_percent == Decimal("41.4")


def test_the_minimum_counts_each_book_not_the_hour_across_books():
    assert cell(OIL, 18).win_rate is None
    assert cell(IDX, 18).win_rate is None


def test_thirty_level_trades_have_no_win_rate_to_show():
    level = [replace(t, net=Decimal(0)) for t in TRIPS if t.entry_ts.hour == 19]
    h = mx.clocks_by_book(level)[0].hours[0]
    assert (h.trips, h.win_rate) == (30, None)


def test_the_few_trades_flag_still_reads_under_five():
    assert cell(OIL, 22).small_sample
    assert not cell(OIL, 18).small_sample


def test_the_largest_hour_is_the_largest_by_size_whichever_way_it_went():
    assert clock(OIL).largest.hour == 20
    assert clock(IDX).largest.hour == 10


def test_two_hours_the_same_size_read_the_one_with_more_trades():
    day = [t for t in TRIPS if t.symbol == "WIDGETIDX" and t.entry_ts.hour == 10][:3]
    one = replace(day[0], net=Decimal(-300))
    two = [
        replace(day[1], net=Decimal(100), entry_ts=day[1].entry_ts.replace(hour=11)),
        replace(day[2], net=Decimal(200), entry_ts=day[2].entry_ts.replace(hour=11)),
    ]
    assert mx.clocks_by_book([one, *two])[0].largest.hour == 11


def test_per_trade_names_the_larger_hour_among_those_with_30_trades():
    """18:00 is larger still, at -162 a trade, but on 29 trades."""
    assert clock(OIL).larger_per_trade.hour == 21


def test_per_trade_names_nothing_when_the_largest_hour_is_also_largest_per_trade():
    assert clock(IDX).larger_per_trade is None


def test_per_trade_names_nothing_when_the_two_read_the_same_in_whole_rupees():
    """-137.50 and -137.20 both print as -₹137, and "larger" would read as a mistake."""
    base = [t for t in TRIPS if t.symbol == "WIDGETOIL" and t.entry_ts.hour == 20][:30]
    first = [replace(t, net=Decimal("-137.50")) for t in base]  # 30 trades, -4,125 at 20:00
    second = [
        replace(t, net=Decimal("-137.20"), entry_ts=t.entry_ts.replace(hour=21)) for t in base
    ]
    extra = [replace(t, trip_id=f"{t.trip_id}x") for t in second[:5]]  # 35 trades, -4,802 at 21:00
    book = mx.clocks_by_book(first + second + extra)[0]
    assert book.largest.hour == 21
    assert book.larger_per_trade is None


def test_a_share_on_the_day_is_in_the_stocks_book_the_trade_list_names():
    """One definition of a book: the clock reads the trade list's, not one of its own."""
    line = mx.TradeLine("WIDGETCO", "EQ", "Buy", 10, Decimal(100), Decimal(101), Decimal(10))
    share = replace(TRIPS[0], is_option=False, lines=(line,))
    assert mx.clocks_by_book([share])[0].book == mx.trade_book(share) == "Stocks and ETFs"


def test_no_trades_is_no_clocks():
    assert mx.clocks_by_book([]) == []


# ---------- The page ----------


def test_the_page_names_each_book():
    for book in (OIL, IDX, GOLD):
        assert book in PAGE


def test_the_page_says_which_time_each_clock_is():
    assert "132 same-day trades, by the hour you opened, India time." in PAGE


def test_a_clock_in_another_zone_says_that_zone():
    """The loader gives each instrument's hours in its own zone, and the page reads that."""
    chicago = ZoneInfo("America/Chicago")
    trade = trips_from([100])[0]
    moved = replace(
        trade,
        entry_ts=datetime(2026, 9, 1, 9, 0, tzinfo=chicago),
        exit_ts=datetime(2026, 9, 1, 9, 5, tzinfo=chicago),
        trading_day="2026-09-01",
    )
    figs = SF.facts(SF.record_context([moved]), IMP)
    assert figs["clock"]["clocks"][0]["zone"] == "America/Chicago time"


def test_the_headline_names_the_hour_as_what_happened():
    assert "The largest result in any one hour: −₹5,500 at 20:00, in WIDGETOIL options." in PAGE
    assert "Its largest result in one hour: −₹5,500 at 20:00, over 40 trades, −₹137 per trade." in PAGE
    assert "Its largest result in one hour: +₹3,000 at 10:00, over 30 trades, +₹100 per trade." in PAGE


@pytest.mark.parametrize("words", ["worst hour", "best hour", "your worst", "your best"])
def test_the_headline_calls_no_hour_good_or_bad(words):
    assert words not in PAGE.lower()


def test_the_figure_is_an_hour_not_a_span():
    assert FIG["figure"] == "20:00 hour"
    assert "hours" not in FIG["figure"]


def test_a_table_row_has_all_its_figures():
    row = unescape(fact_page("clock", TRIPS))
    assert ">−₹5,500<" in row
    assert ">25%<" in row
    assert ">41.4%<" in row
    assert ">16.7%<" in row


def test_per_trade_shows_at_any_count_and_win_rate_does_not():
    gold = next(c for c in FIG["other_clocks"] if c["book"] == GOLD)
    assert gold["hours"][0]["per_trade"] == Decimal(20)
    assert gold["hours"][0]["win_rate"] is None
    assert "An hour with fewer than 30 trades shows no win rate." in PAGE


def test_an_hidden_win_rate_is_a_dash_not_a_zero():
    page = fact_page("clock", TRIPS)
    first = page.index("18:00</a>")
    assert ">—<" in page[first : page.index("</tr>", first)]


def test_the_arithmetic_is_said_where_a_large_total_is_not_largest_per_trade():
    assert (
        "Per trade, 21:00 is larger: −₹4,500 over 30 trades is −₹150 per trade. "
        "The 20:00 hour's −₹5,500 is spread over 40 trades, which is −₹137 per trade."
    ) in PAGE


def test_it_is_not_said_where_it_does_not_hold():
    assert PAGE.count("Per trade,") == 1


def test_each_hour_links_to_its_trades_by_book_and_hour():
    page = unescape(fact_page("clock", TRIPS))
    assert S.see_all_href("clock", book=OIL, hour=20) in page
    assert S.see_all_href("clock", book=IDX, hour=18) in page


def test_that_link_opens_the_trades_it_counts():
    listing = TL.listing("clock", CTX, {"book": IDX, "hour": "18"}, {})
    assert (listing["shown"], listing["total"]) == (29, 197)


def test_the_way_into_the_next_chapter_is_the_spines():
    """TICKET-903: no button of its own; Next says it crosses into chapter 3."""
    assert "Chapter 3: " not in unescape(fact_page("clock", TRIPS))
    assert S.next_step("clock")["label"] == f"Next, chapter 3: {S.FACTS['down'].title}"


def test_the_button_is_there_with_nothing_to_show_too():
    held = [t for t in TRIPS if t.trip_id == "held1"]
    assert f"Chapter 3: {S.chapter(3).name}" not in readable(fact_page("clock", held))  # TICKET-903


def test_the_button_takes_the_chapters_name_from_the_map(monkeypatch):
    changed = replace(S.CHAPTERS[2], name="A new name")
    monkeypatch.setattr(S, "CHAPTERS", (*S.CHAPTERS[:2], changed, S.CHAPTERS[3]))
    assert "next" not in SF.facts(CTX, IMP)["clock"]  # TICKET-903: scope_map decides it


@pytest.mark.parametrize(
    "line",
    ["New York", "5 to 7", "half hour", "half-hour", "After 3 losses", "losses in a row", "Wednesday"],
)
def test_what_the_research_seat_holds_is_not_on_the_page(line):
    assert line not in PAGE


def test_the_page_reads_no_cause_into_the_arithmetic():
    for word in ("because", "due to", "so you", "market"):
        assert word not in PAGE.lower()


# ---------- A book too small to chart ----------


def test_the_books_with_30_trades_lead_and_the_rest_sit_behind_a_toggle():
    assert [c["book"] for c in FIG["clocks"]] == [OIL, IDX]
    assert [c["book"] for c in FIG["other_clocks"]] == [GOLD]
    page = fact_page("clock", TRIPS)
    assert page.index("<details") < page.index(GOLD)


def test_a_small_book_still_counts_on_the_page():
    assert "1 more book, under 30 same-day trades." in PAGE
    assert "2 same-day trades, by the hour you opened, India time." in PAGE


def test_a_history_with_only_small_books_shows_the_largest_of_them():
    small = trips_from([100, -50, 25])
    fig = SF.facts(SF.record_context(small), IMP)["clock"]
    assert [c["book"] for c in fig["clocks"]] == ["WIDGETOIL options"]
    assert fig["other_clocks"] == []
    assert "<details" not in fact_page("clock", small)


# ---------- The charts and the card ----------


def test_each_book_draws_its_own_chart():
    c = clock(OIL)
    want = G.chart_clock(
        [float(h.net) for h in c.hours],
        [i for i, h in enumerate(c.hours) if h.small_sample],
        SF.PAGE_W,
        SF.PAGE_H,
    )
    assert FIG["clocks"][0]["page_chart"] == want


def test_the_two_books_draw_different_charts():
    assert FIG["clocks"][0]["page_chart"] != FIG["clocks"][1]["page_chart"]
    assert fact_page("clock", TRIPS).count('class="figure"') == 2


def test_the_axis_runs_from_the_books_first_hour_to_its_last():
    assert (FIG["clocks"][0]["first_hour"], FIG["clocks"][0]["last_hour"]) == ("18:00", "22:00")
    assert (FIG["clocks"][1]["first_hour"], FIG["clocks"][1]["last_hour"]) == ("09:00", "18:00")


def test_the_card_names_each_clock_and_its_largest_hour():
    page = readable(chapter_page(2, TRIPS))
    assert "WIDGETOIL options, India time" in page
    assert "WIDGETIDX options, India time" in page
    assert "Largest: −₹5,500 at 20:00" in page
    assert "Largest: +₹3,000 at 10:00" in page
    assert "1 more book on the page." in page


def test_the_dial_draws_the_book_its_figure_comes_from():
    assert SF.facts(CTX, IMP)["clock"]["mini"] == G.chart_clock(
        [float(h.net) for h in clock(OIL).hours],
        [i for i, h in enumerate(clock(OIL).hours) if h.small_sample],
        SF.dial.MINI_W,
        SF.dial.MINI_H,
    )


# ---------- The trades behind it ----------


def test_the_list_keeps_two_books_apart_at_the_same_hour():
    titles = [g["title"] for g in S.groups("clock", CTX)]
    assert f"{OIL} · 18:00" in titles
    assert f"{IDX} · 18:00" in titles


def test_one_book_keeps_the_plain_hour_as_its_title():
    ctx = SF.record_context(trips_from([100, -50]))
    assert [g["title"] for g in S.groups("clock", ctx)] == ["09:00"]
