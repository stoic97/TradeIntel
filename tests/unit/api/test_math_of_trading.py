"""The math of your trading: strike rate and hold time as one fact, per book (TICKET-819).

Synthetic, every expected value worked by hand here, none from anyone's record.

WIDGET, year one, 30 same-day trades, all 2 lots:
  12 winners: 20 x 6, 60 x 3, 120 x 2, 480. Total 1,020, average 85.
      Sorted, places 6 and 7 are 20 and 60: median 40.
      Minutes open: 2, 2, 5, 10, 10, 10, 20, 20, 20, 20, 30, 30. Places 6 and 7 are 10 and
      20: median 15. Within 5 minutes (5 itself counts): 3 of 12, 25%.
      Biggest tenth: 12 / 10 rounds up to 2 trades, 480 + 120 = 600 of 1,020, 58.8%: 59%.
  18 losers: 30 x 9, 50 x 8, 1,130. Total 1,800, average 100.
      Sorted, places 9 and 10 are 30 and 50: median 40.
      Minutes open: 4 x 5, 5 x 4, 6 x 8, and 30 on the 1,130. Places 9 and 10 are 5 and 6:
      median 5.5, 330 seconds, written 5 min. Within 5 minutes: 9 of 18, 50%.
      More than 1,000: the 1,130 alone. 1 of 30 trades, 3.3%: 3%. 1,130 of 1,800, 62.8%: 63%.
      It was open 30 min; the other 17 sorted, place 9 is 5 min. Lots 2 and 2.
  Win rate 12 / 30 = 40%.
  Break-even 100 / (85 + 100) = 54.054...%: 54.1%.
  Average winner needed 100 x 18 / 12 = 150, 65 over the 85.
  More winners: 0.54054 x 30 - 12 = 4.2, about 4 more in 30.
  The identity checks: at 16 winners and 14 losers, 16 x 85 = 1,360 against 1,400, still short.

WIDGET, year two, 30 same-day trades, 10 min winners and 2 min losers:
  15 winners of 100, 15 losers of 50. Win rate 50%. Break-even 50 / 150 = 33.3%.
  Average winner needed 50 x 15 / 15 = 50, 50 under the 100. Above break-even: no more winners.

WIDGET, both years, 60 trades: 27 winners total 2,520, 33 losers total 2,550.
  Win rate 45%. Break-even (2550/33) / (2520/27 + 2550/33) = 45.294...%: 45.3%.
  Average winner needed 2550 / 27 = 94.44. Short by 0.176 of a winner, which still says 1.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from services.production.api import scope_facts as SF
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_scope_chapters import IMP, chapter_page, readable
from tests.unit.api.test_scope_facts import fact_page

INSUFFICIENT = s.ResultState.INSUFFICIENT_SAMPLE
COUNTED = s.ResultState.COUNTED_FACT
NOT_ENOUGH = "not enough trades to say"

Y1_NETS = [20] * 6 + [60] * 3 + [120] * 2 + [480] + [-30] * 9 + [-50] * 8 + [-1130]
Y1_MINUTES = [2, 2, 5, 10, 10, 10, 20, 20, 20, 20, 30, 30] + [4] * 5 + [5] * 4 + [6] * 8 + [30]
Y2_NETS = [100] * 15 + [-50] * 15
Y2_MINUTES = [10] * 15 + [2] * 15


def make(nets, minutes=None, year=2025, symbol="WIDGET", lots=2, start_id=0, is_option=True,
         days_held=0, segment=None):
    """One trade a day, from 1 Jan of the year, closed the same day unless days_held says not."""
    minutes = minutes or [10] * len(nets)
    start = datetime.fromisoformat(f"{year}-01-01T09:15:00+05:30")
    trips = []
    for i, (net, held) in enumerate(zip(nets, minutes, strict=True)):
        entry = start + timedelta(days=i)
        exit_ts = entry + timedelta(days=days_held, minutes=held)
        lines = ()
        if segment:
            lines = (mx.TradeLine(symbol, segment, "Buy", 1, Decimal(1), Decimal(1), Decimal(net)),)
        trips.append(mx.Trip(
            f"{symbol}-{year}-{start_id + i}", symbol, entry.date().isoformat(), entry, exit_ts,
            int((exit_ts - entry).total_seconds()), Decimal(net), lots,
            s.RiskUnitSourceV1.DECLARED_BUDGET, is_option=is_option, lines=lines,
        ))
    return trips


YEAR_ONE = make(Y1_NETS, Y1_MINUTES)
YEAR_TWO = make(Y2_NETS, Y2_MINUTES, year=2026)
BOTH = YEAR_ONE + YEAR_TWO


def only_book(trips) -> mx.BookMath:
    books = mx.math_by_book(trips)
    assert len(books) == 1
    return books[0]


# ---------- The two ways to break even, by hand ----------


def test_the_win_rate_and_the_averages():
    row = only_book(YEAR_ONE).whole
    assert row.state is COUNTED
    assert (row.trades, row.wins, row.losses) == (30, 12, 18)
    assert row.win_percent == Decimal(40)
    assert (row.average_winner, row.average_loser) == (Decimal(85), Decimal(100))


def test_break_even_is_the_average_loser_over_both_averages():
    assert only_book(YEAR_ONE).whole.break_even_percent == Decimal("54.1")


def test_the_average_winner_needed_is_the_same_identity_solved_the_other_way():
    row = only_book(YEAR_ONE).whole
    assert row.winner_needed == Decimal(150)
    assert row.winner_gap == Decimal(65)


def test_at_the_winner_needed_the_break_even_is_the_win_rate():
    """The identity itself: put the needed winner in the ruling's formula, get his win rate."""
    row = only_book(YEAR_ONE).whole
    assert row.average_loser / (row.winner_needed + row.average_loser) == Decimal("0.4")


def test_more_winners_is_the_gap_in_trades():
    row = only_book(YEAR_ONE).whole
    assert (row.more_winners, row.decided) == (4, 30)


def test_a_book_above_break_even_needs_no_more_winners():
    row = only_book(YEAR_TWO).whole
    assert row.win_percent == Decimal(50)
    assert row.break_even_percent == Decimal("33.3")
    assert row.winner_needed == Decimal(50)
    assert row.winner_gap == Decimal(-50)
    assert row.more_winners is None


def test_a_book_exactly_at_break_even_needs_no_more_winners():
    row = only_book(make([100] * 15 + [-100] * 15)).whole
    assert row.break_even_percent == Decimal(50)
    assert row.winner_gap == Decimal(0)
    assert row.more_winners is None


def test_a_book_just_short_says_one_more_rather_than_none():
    row = only_book(BOTH).whole
    assert row.win_percent == Decimal(45)
    assert row.break_even_percent == Decimal("45.3")
    assert row.winner_needed.quantize(Decimal("0.01")) == Decimal("94.44")
    assert row.more_winners == 1


def test_a_level_trade_is_counted_in_the_book_and_in_neither_side():
    """30 trades, one level, so a counted row: 15 winners of 100, 14 losers of 50."""
    row = only_book(make([100] * 15 + [-50] * 14 + [0])).whole
    assert row.state is COUNTED
    assert (row.trades, row.wins, row.losses, row.scratches, row.decided) == (30, 15, 14, 1, 29)
    assert row.win_percent == Decimal("51.7")  # 15 / 29
    assert row.winner_needed == Decimal(50) * 14 / 15


# ---------- The medians, each its own ----------


def test_the_medians_of_rupees():
    row = only_book(YEAR_ONE).whole
    assert (row.median_winner, row.median_loser) == (Decimal(40), Decimal(40))


def test_the_medians_of_minutes():
    row = only_book(YEAR_ONE).whole
    assert (row.winners_median_seconds, row.losers_median_seconds) == (15 * 60, 330)


# ---------- The minimum: 29 and 30 ----------


def test_a_book_at_exactly_30_is_counted():
    assert only_book(make([100] * 12 + [-50] * 18)).whole.state is COUNTED


def test_a_book_at_29_is_not_enough():
    row = only_book(make([100] * 12 + [-50] * 17)).whole
    assert row.state is INSUFFICIENT
    assert row.trades == 29


def test_a_book_below_the_minimum_has_no_figure_to_show():
    """Never a percentage: there is nothing on the row for a page to print by mistake."""
    book = only_book(make([100] * 12 + [-50] * 17))
    row = book.whole
    for value in (row.win_percent, row.break_even_percent, row.average_winner, row.average_loser,
                  row.median_winner, row.median_loser, row.winner_needed, row.winner_gap,
                  row.more_winners, row.winners_median_seconds, row.losers_median_seconds):
        assert value is None
    assert book.years == ()
    assert book.quick_closes is None and book.biggest_losers is None and book.top_winners is None


def test_held_positions_do_not_count_towards_the_30():
    """Same-day only: 29 closed the day they opened and one held past it is still 29."""
    trips = make([100] * 12 + [-50] * 17) + make([100], year=2024, days_held=3)
    context = SF.record_context(trips)
    assert [b.whole.trades for b in context["book_math"]] == [29]
    assert context["book_math"][0].whole.state is INSUFFICIENT


def test_30_level_trades_have_no_win_rate_to_show():
    assert only_book(make([0] * 30)).whole.state is INSUFFICIENT


def test_30_winners_are_counted_with_no_break_even():
    row = only_book(make([100] * 30)).whole
    assert row.state is COUNTED
    assert row.win_percent == Decimal(100)
    assert row.break_even_percent is None and row.winner_needed is None
    assert row.median_loser is None and row.losers_median_seconds is None


def test_the_minimum_is_the_frameworks_n_min():
    """The ruling reuses the framework's standard n_min rather than inventing one."""
    framework = Path("services/research/prereg/framework_v1.yaml").read_text()
    b1 = re.search(r"id: B1,.*?n_min: (\d+)/", framework)
    assert mx.BOOK_ROW_MINIMUM == int(b1[1]) == 30


# ---------- Per book, one definition of a book ----------


def test_books_use_the_one_definition_of_a_book():
    """Crude's two contracts are one book, and a share is in with the shares."""
    trips = (make([100] * 30, symbol="CRUDEOIL") + make([100] * 2, symbol="CRUDEOILM", start_id=30)
             + make([100], symbol="WIDGETCO", is_option=False, segment="EQ"))
    assert [b.whole.label for b in mx.math_by_book(trips)] == ["Crude options", "Stocks and ETFs"]
    assert {b.whole.label for b in mx.math_by_book(trips)} == {mx.trade_book(t) for t in trips}


def test_the_biggest_book_comes_first():
    trips = make([100] * 2, symbol="SMALL") + make([100] * 5, symbol="LARGE")
    assert [b.whole.label for b in mx.math_by_book(trips)] == ["LARGE options", "SMALL options"]


def test_no_trades_means_no_books():
    assert mx.math_by_book([]) == []


# ---------- The year split ----------


def test_a_book_is_split_by_year_in_order():
    book = only_book(BOTH)
    assert [y.label for y in book.years] == ["2025", "2026"]
    assert book.years[0] == mx.math_row("2025", YEAR_ONE)
    assert book.years[1] == mx.math_row("2026", YEAR_TWO)


def test_the_year_rows_keep_their_own_figures():
    book = only_book(BOTH)
    assert book.years[0].break_even_percent == Decimal("54.1")
    assert book.years[1].break_even_percent == Decimal("33.3")


def test_a_year_below_the_minimum_says_so_while_the_book_is_counted():
    """A year is a smaller cut of a book row, so the same rule holds: 40 in all, 29 in 2026."""
    book = only_book(make([100] * 5 + [-50] * 6) + make([100] * 10 + [-50] * 19, year=2026))
    assert book.whole.state is COUNTED
    assert [y.state for y in book.years] == [INSUFFICIENT, INSUFFICIENT]
    assert book.years[1].win_percent is None


# ---------- The lines under a book ----------


def test_the_share_closed_within_five_minutes():
    closes = only_book(YEAR_ONE).quick_closes
    assert (closes.losers_percent, closes.winners_percent) == (50, 25)


def test_a_share_of_nothing_is_nought():
    assert only_book(make([100] * 30, [10] * 30)).quick_closes.winners_percent == 0


def test_the_top_winners_carry_this_share():
    top = only_book(YEAR_ONE).top_winners
    assert (top.count, top.winners, top.percent) == (2, 12, 59)


def test_the_biggest_losers():
    big = only_book(YEAR_ONE).biggest_losers
    assert (big.count, big.trades_percent, big.losses_percent) == (1, 3, 63)
    assert (big.median_seconds, big.others_median_seconds) == (30 * 60, 5 * 60)
    assert (big.median_lots, big.others_median_lots) == (2, 2)
    assert big.above == Decimal(1000)


def test_a_loss_of_exactly_the_line_is_not_past_it():
    assert only_book(make([100] * 15 + [-50] * 14 + [-1000])).biggest_losers is None


def test_size_is_left_out_where_a_lot_is_not_a_size():
    trips = make([100] * 15 + [-50] * 14 + [-1130], is_option=False, segment="EQ")
    big = only_book(trips).biggest_losers
    assert big.count == 1
    assert big.median_lots is None and big.others_median_lots is None


# ---------- The page ----------


@pytest.fixture()
def page():
    return fact_page("math", BOTH)


@pytest.fixture()
def text(page):
    return readable(page)


def row_of(page: str, label: str) -> str:
    """The summary table's row for a book, as HTML."""
    found = re.search(rf'<tr[^>]*>\s*<td[^>]*>{re.escape(label)}</td>.*?</tr>', page, re.DOTALL)
    assert found, label
    return found[0]


def cells(html: str) -> str:
    """A table as a reader reads it: its cells apart, a figure under a figure on one line."""
    return readable(re.sub(r'</t[dh]>|<span class="math__under"', lambda m: f" {m[0]}", html))


def test_the_fact_has_its_new_name(text):
    assert "The math of your trading" in text


def test_a_book_row_shows_the_win_rate_and_both_ways_to_break_even(page):
    row = cells(row_of(page, "WIDGET options"))
    for figure in ("60", "45%", "45.3%", "₹94", "+₹1"):
        assert figure in row, row


def test_both_ways_are_said_in_words(text):
    assert "a win rate of 54.1%" not in text  # the year's figure is in the year's row, not here
    assert "a win rate of 45.3%, about 1 more winner in 60." in text
    assert "an average winner of ₹94, +₹1 on your ₹93." in text


def test_averages_and_medians_sit_side_by_side_per_year(page):
    table = re.search(r'data-table="sizes".*?</table>', page, re.DOTALL)[0]
    assert "Average" in table and "Typical (median)" in table and "Open" in table
    year_one = cells(table)
    assert "2025 Winners ₹85 ₹40 15 min" in year_one
    assert "2025 Losers ₹100 ₹40 5 min" in year_one
    assert "2026 Winners ₹100 ₹100 10 min" in year_one
    assert "2026 Losers ₹50 ₹50 2 min" in year_one


def test_the_year_table_gives_each_years_math(page):
    table = cells(re.search(r'data-table="years".*?</table>', page, re.DOTALL)[0])
    assert "2025 30 40% 54.1% ₹150 +₹65" in table
    assert "2026 30 50% 33.3% ₹50 −₹50" in table


def test_each_median_is_stated_separately():
    text = readable(fact_page("math", YEAR_ONE))
    assert "Losers were open a median 5 min and lost a median ₹40." in text
    assert "Winners were open a median 15 min and made a median ₹40." in text
    assert "Each median is worked out on its own" in text


def test_the_exit_line_says_nothing_about_entries():
    text = readable(fact_page("math", YEAR_ONE))
    assert "50% of losers closed within 5 minutes, against 25% of winners." in text
    assert "It says nothing about the entries." in text


def test_the_biggest_losers_are_a_secondary_line_that_explains_nothing():
    page = fact_page("math", YEAR_ONE)
    text = readable(page)
    assert "1 trade (3%) lost more than ₹1,000, 63% of this book's losses." in text
    assert "It was 2 lots, the other losers a median 2 lots." in text
    assert "It was open 30 min, the other losers a median 5 min." in text
    assert "Part of this is arithmetic" not in text
    assert "more time to lose" not in text
    assert re.search(r'<p class="[^"]*math__secondary[^"]*">[^\n]*lost more than', page)


def test_more_than_one_big_loser_reads_in_the_plural_and_one_lot_in_the_singular():
    """Winners 100 x 20. Losers 50 x 8 at 2 min, and 2,000 x 2 at 40 and 60 min: median 50."""
    nets = [100] * 20 + [-50] * 8 + [-2000] * 2
    text = readable(fact_page("math", make(nets, [10] * 20 + [2] * 8 + [40, 60], lots=1)))
    assert "2 trades (7%) lost more than ₹1,000 each, 91% of this book's losses." in text
    assert "They were a median 1 lot, the other losers a median 1 lot." in text
    assert "They were open a median 50 min, the other losers a median 2 min." in text


def test_the_top_winners_line_gives_the_number_and_no_verdict():
    text = readable(fact_page("math", YEAR_ONE))
    assert "The 2 biggest of your 12 winners made 59% of what your winners made in this book." in text


def test_both_ways_are_shown_and_neither_is_picked(text):
    assert "shows both and does not pick one" in text


@pytest.mark.parametrize("words", [
    "hold longer", "holding longer", "let winners run", "letting winners run", "a typical trade",
    "your entries", "entries got worse", "is the problem", "aren't the problem", "cut fast",
    "you'd have", "you would have", "broken even", "you should", "a ratio of", "winning",
])
def test_the_page_keeps_the_dont_list(words):
    for page in (fact_page("math", BOTH), chapter_page(2, BOTH)):
        assert words not in readable(page).lower(), words


def test_a_small_book_row_says_not_enough_and_shows_no_percentage():
    trips = BOTH + make([100] * 12 + [-50] * 17, symbol="SMALL")
    page = fact_page("math", trips)
    row = row_of(page, "SMALL options")
    assert NOT_ENOUGH in row
    assert 'data-state="INSUFFICIENT_SAMPLE"' in row
    assert ">29<" in row
    assert "%" not in row and "₹" not in row


def test_a_book_at_exactly_30_shows_its_percentage():
    page = fact_page("math", make([100] * 12 + [-50] * 18))
    row = row_of(page, "WIDGET options")
    assert NOT_ENOUGH not in row
    assert "40%" in row
    assert 'data-state="COUNTED_FACT"' in row


def test_a_small_book_gets_no_detail_on_the_page():
    trips = BOTH + make([100] * 12 + [-50] * 17, symbol="SMALL")
    assert '<h2 class="heading math__book">SMALL options</h2>' not in fact_page("math", trips)
    assert '<h2 class="heading math__book">WIDGET options</h2>' in fact_page("math", trips)


def test_a_small_year_says_not_enough_inside_a_counted_book():
    trips = make([100] * 25 + [-50] * 25) + make([100] * 10 + [-50] * 19, year=2026)
    table = re.search(r'data-table="years".*?</table>', fact_page("math", trips), re.DOTALL)[0]
    assert NOT_ENOUGH in table
    small = re.search(r"<tr[^>]*>\s*<td[^>]*>2026</td>.*?</tr>", table, re.DOTALL)[0]
    assert "%" not in small


def test_a_book_with_no_loser_renders_dashes_and_no_none():
    trips = make([100] * 30) + make([-50] * 2, symbol="SMALL")
    page = readable(fact_page("math", trips))
    assert "None" not in page
    assert "WIDGET options" in page


def test_the_card_gives_a_row_per_book():
    page = chapter_page(2, BOTH + make([100] * 2, symbol="SMALL"))
    assert "WIDGET options" in page and "SMALL options" in page
    assert NOT_ENOUGH in page


def test_the_chapter_reads_same_day_only():
    held = BOTH + make([5000], year=2024, days_held=30)
    assert only_book(mx.same_day_trips(held)).whole.trades == 60
    context = SF.record_context(held)
    assert [b.whole.trades for b in context["book_math"]] == [60]


def test_the_home_slice_leads_with_the_strike_rate():
    context = SF.record_context(BOTH)
    figs = SF.facts(context, IMP)
    assert figs["math"]["figure"] == f"{context['strike'].rate_percent}%"
    assert SF.home_view(figs, context)["items"][1]["figure"] == figs["math"]["figure"]
