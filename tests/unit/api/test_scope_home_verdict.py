"""Scope home says what happened: the result, a row per book, a finding per chapter [TICKET-823].

Synthetic trades, expected values worked by hand:

  crude options   19 days at -100, one at -500 (05 Jan 2026)         20 trades  -2,400
  NIFTY options   ten at +50, nine at -50, one at -150 (02 Feb 2026) 20 trades    -100
  other options   SENSEX 3 at -10 (from 01 May), BANKNIFTY 2 at +5    5 trades     -20
  options                                                            45 trades  -2,520
  stocks          Shree Cement +1,300 held 300 days, INFY 2 at -100   3 trades  +1,100
  the whole file                                                     48 trades  -1,420
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from services.production.api import dial
from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as sc
from tests.unit.api.templating import template_env
from tests.unit.api.test_scope_chapters import IMP, readable
from tests.unit.api.test_scope_chapters import TRIPS as FORTY


def t(day, net, symbol="CRUDEOIL", is_option=True, held_days=0, at="10:00"):
    entry = datetime.fromisoformat(f"{day}T{at}:00+05:30")
    exit_ts = entry + timedelta(days=held_days, minutes=10)
    lines = () if is_option else (mx.TradeLine(symbol, "EQ", "Buy", 1, None, None, Decimal(net)),)
    return mx.Trip(
        f"{symbol}-{day}-{at}", symbol, day, entry, exit_ts, int((exit_ts - entry).total_seconds()),
        Decimal(net), 1, sc.RiskUnitSourceV1.PREMIUM_PAID, is_option=is_option, lines=lines,
    )


def days_from(start: date, n: int) -> list[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range(n)]


def options() -> list[mx.Trip]:
    crude = [t("2026-01-05", -500)] + [t(d, -100) for d in days_from(date(2026, 1, 6), 19)]
    nifty = (
        [t(d, 50, "NIFTY") for d in days_from(date(2026, 3, 1), 10)]
        + [t(d, -50, "NIFTY") for d in days_from(date(2026, 4, 1), 9)]
        + [t("2026-02-02", -150, "NIFTY")]
    )
    other = [t(d, -10, "SENSEX") for d in days_from(date(2026, 5, 1), 3)] + [
        t(d, 5, "BANKNIFTY") for d in days_from(date(2026, 5, 4), 2)
    ]
    return crude + nifty + other


def stocks() -> list[mx.Trip]:
    return [
        t("2025-01-01", 1300, "Shree Cement", is_option=False, held_days=300),
        t("2026-06-01", -100, "INFY", is_option=False),
        t("2026-06-02", -100, "INFY", is_option=False),
    ]


def page(trips=None, imp=IMP, opened=frozenset()) -> str:
    trips = options() + stocks() if trips is None else trips
    ctx = SF.record_context(trips)
    return template_env().get_template("scope/home.html").render(
        title="Scope", imp=imp, trade_count=len(trips),
        trading_day_count=len(ctx["days"].counts), **SF.home_context(ctx, imp, opened))


def text(**kw) -> str:
    return readable(page(**kw))


def view(trips=None, imp=IMP, opened=frozenset()) -> dict:
    ctx = SF.record_context(options() + stocks() if trips is None else trips)
    return SF.home_context(ctx, imp, opened)["view"]


# The per-book read ---------------------------------------------------------------------


def test_each_book_has_its_result_and_its_trades():
    books = mx.verdict(options() + stocks()).books
    assert [(b.label, b.net, b.trades) for b in books] == [
        ("Crude options", Decimal(-2400), 20),
        ("NIFTY options", Decimal(-100), 20),
        ("Other options", Decimal(-20), 5),
        ("Stocks and ETFs", Decimal(1100), 3),
    ]


def test_the_rows_add_up_to_the_whole_result():
    trips = options() + stocks()
    assert sum(b.net for b in mx.verdict(trips).books) == sum(t.net for t in trips) == Decimal(-1420)


def test_a_book_under_twenty_trades_goes_in_other_options():
    trips = [t(d, -10, "NIFTY") for d in days_from(date(2026, 1, 1), 19)]
    assert [(b.label, b.trades) for b in mx.verdict(trips).books] == [("Other options", 19)]


def test_crudeoil_and_its_mini_are_one_book():
    trips = [t(d, -10, "CRUDEOIL") for d in days_from(date(2026, 1, 1), 10)] + [
        t(d, -10, "CRUDEOILM") for d in days_from(date(2026, 2, 1), 10)
    ]
    assert [(b.label, b.trades) for b in mx.verdict(trips).books] == [("Crude options", 20)]


def test_a_book_names_the_day_it_lost_most():
    crude = mx.verdict(options()).books[0]
    assert (crude.worst_day, crude.worst_net) == ("2026-01-05", Decimal(-500))


def test_a_book_that_never_lost_a_day_names_no_worst_day():
    trips = [t(d, 10, "CRUDEOIL") for d in days_from(date(2026, 1, 1), 20)]
    assert mx.verdict(trips).books[0].worst_day is None


def test_the_one_holding_that_made_most_of_it_is_named():
    held = mx.verdict(options() + stocks()).standout
    assert (held.symbol, held.net, held.held_days) == ("Shree Cement", Decimal(1300), 300)


def test_no_holding_is_named_when_none_made_half_of_it():
    even = [t("2026-06-01", 100, "INFY", is_option=False), t("2026-06-02", 100, "TCS", is_option=False),
            t("2026-06-03", 100, "ITC", is_option=False)]
    assert mx.verdict(options() + even).standout is None


def test_no_holding_is_named_when_the_group_lost():
    lost = [t("2026-06-01", 50, "INFY", is_option=False), t("2026-06-02", -500, "TCS", is_option=False)]
    assert mx.verdict(options() + lost).standout is None


# The verdict sentence ------------------------------------------------------------------


def verdict_line(trips) -> str:
    html = page(trips=trips)
    h1 = html[html.index('<h1 class="title fact__title">'):]
    return readable(h1[: h1.index("</h1>")])


def test_the_page_opens_on_the_result():
    assert verdict_line(options() + stocks()) == (
        "Your option trades lost ₹2,520. Shree Cement, held up to 300 days, made back ₹1,300 of it.")


def test_counts_alone_no_longer_lead():
    assert "What your trades actually did." not in page()


def test_a_holding_closed_the_same_day_is_not_called_held():
    trips = options() + [t("2026-06-01", 700, "INFY", is_option=False)]
    assert verdict_line(trips) == "Your option trades lost ₹2,520. INFY made back ₹700 of it."


def test_one_day_reads_in_the_singular():
    trips = options() + [t("2026-06-01", 700, "INFY", is_option=False, held_days=1)]
    assert verdict_line(trips) == "Your option trades lost ₹2,520. INFY, held up to 1 day, made back ₹700 of it."


def test_made_back_is_only_said_of_less_than_was_lost():
    trips = options() + [t("2026-06-01", 9000, "INFY", is_option=False, held_days=30)]
    assert verdict_line(trips) == "Your option trades lost ₹2,520. Your stock, ETF and futures trades made ₹9,000."


def test_without_a_standout_the_group_is_told():
    lost = [t("2026-06-01", 50, "INFY", is_option=False), t("2026-06-02", -500, "TCS", is_option=False)]
    assert verdict_line(options() + lost) == "Your option trades lost ₹2,520. Your stock, ETF and futures trades lost ₹450."


def test_options_alone():
    assert verdict_line(options()) == "Your option trades lost ₹2,520."


def test_stocks_alone():
    assert verdict_line(stocks()) == "Your trades made ₹1,100."


def test_options_that_made_money_are_not_said_to_be_made_back():
    trips = [t("2026-01-05", 500), t("2026-06-01", 700, "INFY", is_option=False, held_days=30)]
    assert verdict_line(trips) == "Your option trades made ₹500. Your stock, ETF and futures trades made ₹700."


def test_a_level_result_reads_as_level():
    trips = [t("2026-01-05", 500), t("2026-01-06", -500)]
    assert verdict_line(trips) == "Your option trades came out level."


# The rows on the page ------------------------------------------------------------------


def test_each_book_has_a_row_with_one_line():
    body = text()
    assert "Crude options −₹2,400 20 trades. Worst day: 05 Jan 2026, −₹500." in body
    assert "NIFTY options −₹100 20 trades. Worst day: 02 Feb 2026, −₹150." in body
    assert "Other options −₹20 5 trades. Worst day: 01 May 2026, −₹10." in body
    assert "Stocks and ETFs +₹1,100 3 trades. Shree Cement made ₹1,300, held up to 300 days." in body


def test_a_single_trade_reads_in_the_singular():
    assert "Other options −₹500 1 trade. Worst day: 05 Jan 2026, −₹500." in text(trips=[t("2026-01-05", -500)])


def test_the_books_say_no_more_than_the_record():
    # About the books, so it stops before the chapters: "trades made money" is an agreed count.
    body = readable(re.sub(r"<svg\b.*?</svg>", " ", page(), flags=re.DOTALL)).lower()
    body = body.split("four chapters")[0]
    for word in ("your worst hour", "almost half", "made money", "every other price", "held about a year"):
        assert word not in body, word


# The dial ------------------------------------------------------------------------------


def test_the_centre_is_the_result_with_the_charges_beside_it():
    v = view()
    assert v["centre"]["figure"] == "−₹1,420"
    svg = str(dial.scope_dial(v))
    assert ">your result,</tspan>" in svg and ">before charges</tspan>" in svg


def test_a_file_with_charges_does_not_say_before_charges():
    imp = SimpleNamespace(**{**vars(IMP), "fees_available": True})
    svg = str(dial.scope_dial(view(imp=imp)))
    assert "before charges" not in svg
    assert ">your result for</tspan>" in svg and ">the whole period</tspan>" in svg


def test_the_charges_line_comes_right_after_the_verdict_not_in_the_footer():
    html = page()
    assert html.index("</h1>") < html.index("every rupee figure below is gross") < html.index("Your books")


def test_the_charges_line_promises_nothing_scope_cannot_do_yet():
    body = text().lower()
    assert "can be worked out" not in body and "brokerage plan" not in body


def test_a_chapter_opened_is_the_dot_on_the_rim():
    v = view(opened=frozenset({1, 3}))
    assert str(dial.scope_dial(v)).count('class="scope__opened"') == 2


# The chapters --------------------------------------------------------------------------


def test_every_chapter_is_listed_with_a_way_in():
    html = page(trips=FORTY)
    for c in S.CHAPTERS:
        assert c.name in html
        assert f">Open chapter {c.number}<" in html
        assert S.chapter_href(c.number, from_home=True).replace("&", "&amp;") in html


def test_a_chapter_with_too_few_trades_says_so():
    body = text(trips=[t("2026-01-05", 100), t("2026-01-06", 200)])
    assert body.count("Not enough trades yet.") == 2  # fewer than five days; no losers. Zero occasions is a count, so chapter 3 says it


def test_a_chapter_opened_shows_as_read_in_the_list():
    html = page(trips=FORTY, opened=frozenset({2}))
    assert html.count("home__chapter--read") == 1
    assert 'home__chapter--read"><span class="label">2 · ' in html


# Start here ----------------------------------------------------------------------------


def start_button(html: str) -> str:
    stage = html[html.index('<header class="stage'): html.index("</header>")]
    return readable(stage[stage.index('<a class="btn'):]) if '<a class="btn' in stage else ""


def test_there_is_a_way_to_start():
    """TICKET-903: Continue names the first page not yet read (scope_map.continue_step)."""
    assert S.continue_step(frozenset())["label"] == f"Continue: {S.PAGES[0].title}"
    assert "Start with chapter" not in page()


def test_once_started_it_points_at_the_next_unread_page():
    """TICKET-903: by page, not by chapter; read pages are skipped, in scope_map's order."""
    assert S.continue_step(frozenset({S.PAGES[0].key}))["label"] == f"Continue: {S.PAGES[1].title}"
    read = frozenset({S.PAGES[0].key, S.PAGES[1].key, S.PAGES[3].key})
    assert S.continue_step(read)["label"] == f"Continue: {S.PAGES[2].title}"
    assert S.continue_step(frozenset(f.key for f in S.PAGES)) is None


def test_with_everything_read_there_is_no_button():
    assert start_button(page(opened=frozenset({1, 2, 3, 4}))) == ""


def test_no_buy_or_sell_calls_stays():
    assert "<span>No buy or sell calls, ever.</span>" in page()


def _future(net):
    entry = datetime.fromisoformat("2026-06-01T10:00:00+05:30")
    return mx.Trip("f1", "NIFTY FUT", "2026-06-01", entry, entry + timedelta(minutes=5), 300,
                   Decimal(net), 1, sc.RiskUnitSourceV1.UNAVAILABLE, is_option=False,
                   lines=(mx.TradeLine("NIFTY FUT", "FUT", "Buy", 1, None, None, Decimal(net)),))


def test_the_books_are_the_ones_every_other_page_calls_them():
    """One definition, trade_book: a future isn't in with the stocks here and apart on the clock."""
    trips = [*options(), t("2026-06-02", 700, "INFY", is_option=False), _future(-250)]
    books = {row.label: row.net for row in mx.verdict(trips).books}
    assert books["Stocks and ETFs"] == Decimal(700)
    assert books["Futures"] == Decimal(-250)


def test_a_standout_sits_on_the_row_that_holds_it():
    trips = [*options(), t("2025-01-01", 900, "Shree Cement", is_option=False, held_days=30),
             _future(10)]
    rows = {row.label: row for row in mx.verdict(trips).books}
    assert rows["Stocks and ETFs"].standout.symbol == "Shree Cement"
    assert rows["Futures"].standout is None


def test_the_verdict_still_adds_stocks_and_futures_together():
    """The sentence and the card's split read the two as one group; the rows split it."""
    made = mx.verdict([*options(), t("2026-06-02", 700, "INFY", is_option=False), _future(-250)])
    assert (made.others_net, made.others_trades) == (Decimal(450), 2)
