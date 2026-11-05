""""Where the money came from" says what its lists found (TICKET-818).

Two ranked lists instead of days in date order; a headline and a hook that are computed,
and said only when they are true of this file; hold times over a day in days and months;
and a button that names the next chapter by its real title.

Every instrument is invented and every expected value below is worked by hand from WHOLE:

    Best five, same day, all WIDGETOIL options:
        +900 (21:00, 60 min)  +800 (19:00, 50 min)  +700 (15:00, 200 min)
        +600 (19:30, 4 min)   +500 (18:00, 110 min)
        sum +3,500; median 60 min; 4 of the 5 opened from 5 pm on.
    Worst five, same day, all WIDGETOIL options:
        -3,100 (20:00, 30 min)  -2,900 (20:10, 8 min)  -2,700 (20:20, 10 min)
        -2,300 (21:00, 11 min)  -2,100 (20:30, 90 min)
        sum -13,100; median 11 min; median loss 2,700; 5 of the 5 opened from 8 pm on.
    Three more same-day WIDGETIDX options at 10:00: +100, -100, -200.
        Same-day trades: 13, net 3,500 - 13,100 - 200 = -9,800.
    Held past the day, WIDGET ETF: +40,000 (400 days), +20,000 (200 days), +10,000 (45 days).
    Held past the day, WIDGETCO: +100 (3 days).
        Held: 4 positions, net 70,100. WIDGET ETF is 70,000 of it.
    The five biggest results of all: the three ETF positions, then +900 and +800.
"""

from __future__ import annotations

import dataclasses
import re
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from services.production.api import trade_list as TL
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_scope_chapters import IMP, chapter_page, readable
from tests.unit.api.test_scope_facts import fact_page
from tests.unit.api.test_trade_rows import articles, text, uploaded  # noqa: F401
from tests.unit.api.test_upload import client, engine  # noqa: F401

HEADLINE = "Your best trades weren't trades."
HOOK = "Your best and worst trades are in the same place."
CUT = ("This describes what happened, not advice to hold longer.",
       "A trade can lose fast simply by being wrong from the start.")
DAY = "2026-09-01"


def trip(
    tid: str,
    net: int,
    at: str = "10:00",
    minutes: int = 10,
    days: int = 0,
    symbol: str = "WIDGETOIL",
    segment: str = "OPT",
    day: str = DAY,
) -> mx.Trip:
    entry = datetime.fromisoformat(f"{day}T{at}:00+05:30")
    held = timedelta(days=days, minutes=minutes)
    return mx.Trip(
        trip_id=tid,
        symbol=symbol,
        trading_day=day,
        entry_ts=entry,
        exit_ts=entry + held,
        holding_seconds=int(held.total_seconds()),
        net=Decimal(net),
        lots=1,
        risk_unit_source=s.RiskUnitSourceV1.UNAVAILABLE,
        is_option=segment == "OPT",
        lines=(
            mx.TradeLine(
                symbol=symbol,
                segment=segment,
                side="Buy",
                quantity=100,
                entry_price=Decimal(100),
                exit_price=Decimal(110),
                net=Decimal(net),
            ),
        ),
    )


def share(tid: str, net: int, days: int, symbol: str = "WIDGETCO", day: str = "2025-05-05") -> mx.Trip:
    return trip(tid, net, minutes=0, days=days, symbol=symbol, segment="EQ", day=day)


BEST = [
    trip("b1", 900, "21:00", 60),
    trip("b2", 800, "19:00", 50),
    trip("b3", 700, "15:00", 200),
    trip("b4", 600, "19:30", 4),
    trip("b5", 500, "18:00", 110),
]
WORST = [
    trip("w1", -3100, "20:00", 30),
    trip("w2", -2900, "20:10", 8),
    trip("w3", -2700, "20:20", 10),
    trip("w4", -2300, "21:00", 11),
    trip("w5", -2100, "20:30", 90),
]
MIDDLE = [
    trip("m1", 100, symbol="WIDGETIDX"),
    trip("m2", -100, symbol="WIDGETIDX"),
    trip("m3", -200, symbol="WIDGETIDX"),
]
SAME_DAY = BEST + WORST + MIDDLE
ETF = [
    share("e1", 40000, 400, "WIDGET ETF", "2025-01-06"),
    share("e2", 20000, 200, "WIDGET ETF", "2025-02-03"),
    share("e3", 10000, 45, "WIDGET ETF", "2025-03-03"),
]
WHOLE = SAME_DAY + ETF + [share("s1", 100, 3, day="2025-04-07")]


def found(trips: list[mx.Trip]) -> mx.MoneyFound:
    return mx.money_found(trips)


def page_of(trips: list[mx.Trip]) -> str:
    return readable(fact_page("money", trips))


# ---------- The figures, by hand ----------


def test_the_same_day_result_is_counted():
    got = found(WHOLE)
    assert (got.same_day_count, got.same_day_net) == (13, Decimal(-9800))


def test_each_list_has_its_sum():
    got = found(WHOLE)
    assert (got.best_net, got.worst_net) == (Decimal(3500), Decimal(-13100))


def test_the_medians_of_the_two_lists():
    got = found(WHOLE)
    assert got.best_median_seconds == 3600
    assert got.worst_median_seconds == 660
    assert got.worst_median_loss == Decimal(2700)


def test_the_hours_are_counted_from_the_opening():
    got = found(WHOLE)
    assert (got.best_evening, got.worst_evening, got.worst_late) == (4, 5, 5)


def test_the_largest_holding_is_added_up_by_instrument():
    top = found(WHOLE).top_holding
    assert top.instrument == "WIDGET ETF"
    assert top.net == Decimal(70000)
    assert top.longest_seconds == 400 * 86400


# ---------- The headline is said only when it is true ----------


def test_three_of_the_five_biggest_results_being_long_holdings_makes_the_headline_true():
    got = found(WHOLE)
    assert got.holdings_in_best == 3
    assert got.best_were_holdings is True
    assert HEADLINE in page_of(WHOLE)


def test_two_of_the_five_is_not_enough():
    trips = [t for t in WHOLE if t.trip_id != "e3"]
    assert found(trips).holdings_in_best == 2
    assert found(trips).best_were_holdings is False
    assert HEADLINE not in page_of(trips)


def test_a_trader_with_no_holdings_reads_what_his_lists_came_to():
    page = page_of(SAME_DAY)
    assert HEADLINE not in page
    assert "Your best five came to +₹3,500. Your worst five came to −₹13,100." in page


def test_options_held_for_months_are_trades_so_the_headline_is_not_said():
    swings = [trip(f"o{i}", 9000 + i, minutes=0, days=40, day="2025-05-05") for i in range(3)]
    trips = SAME_DAY + swings
    assert found(trips).best_were_holdings is False
    assert HEADLINE not in page_of(trips)


def test_shares_held_for_days_are_trades_so_the_headline_is_not_said():
    trips = SAME_DAY + [share(f"q{i}", 9000 + i, 29) for i in range(3)]
    assert found(trips).best_were_holdings is False
    assert HEADLINE not in page_of(trips)


def test_shares_held_for_exactly_a_month_count_as_holdings():
    trips = SAME_DAY + [share(f"q{i}", 9000 + i, 30) for i in range(3)]
    assert found(trips).best_were_holdings is True


def test_losing_holdings_are_not_best_trades():
    trips = [*[share(f"l{i}", -100 - i, 40) for i in range(3)], trip("a", 10), trip("c", 20)]
    assert found(trips).holdings_in_best == 0
    assert HEADLINE not in page_of(trips)


def test_only_holdings_has_no_lists_to_set_them_against():
    page = page_of(ETF)
    assert found(ETF).best_were_holdings is False
    assert HEADLINE not in page
    assert "Every position in your file was held past the day." in page


def test_the_headline_replaces_the_count():
    page = page_of(WHOLE).split("The trades behind this")[0]
    assert "10 trades" not in page and "14 trades" not in page


def test_the_figure_on_the_card_and_the_dial_is_the_same_day_result():
    assert SF.facts(SF.record_context(WHOLE), IMP)["money"]["figure"] == "−₹9,800"


def test_with_only_holdings_the_figure_is_what_they_came_to():
    assert SF.facts(SF.record_context(ETF), IMP)["money"]["figure"] == "+₹70,000"


def test_both_sides_are_on_the_page_above_the_lists():
    page = page_of(WHOLE).split("The trades behind this")[0]
    assert "Everything you closed the same day" in page and "−₹9,800" in page
    assert "Positions you held past the day" in page and "+₹70,100" in page


def test_the_page_says_how_many_of_the_five_were_holdings():
    assert (
        "Of the five biggest gains in your file, 3 were stocks or ETFs held for a month or more."
        in page_of(WHOLE)
    )


def test_the_largest_holding_is_named_with_its_longest_hold():
    assert "WIDGET ETF made +₹70,000 of it, the longest held 13 months 10 days." in page_of(WHOLE)


def test_no_instrument_is_named_when_none_made_most_of_what_was_held():
    spread_out = [share("x1", 100, 40), share("x2", 100, 40, "WIDGETPIPE")]
    assert found(SAME_DAY + spread_out).top_holding is None
    assert "of it, the longest held" not in page_of(SAME_DAY + spread_out)


def test_no_instrument_is_named_when_it_made_more_than_the_whole():
    trips = [*SAME_DAY, share("x1", 100, 40), share("x2", -50, 40, "WIDGETPIPE")]
    assert found(trips).top_holding is None


def test_no_instrument_is_named_when_holdings_lost_overall():
    assert found([*SAME_DAY, share("x1", -100, 40)]).top_holding is None


# ---------- Two ranked lists, not days ----------


def lists(page: str) -> list[str]:
    return re.findall(r'<ol class="ranked">.*?</ol>', page, re.DOTALL)


def test_there_are_two_lists_with_their_names():
    page = fact_page("money", WHOLE)
    assert len(lists(page)) == 2
    assert page.index(">Best five<") < page.index(">Worst five<")


def test_each_list_is_in_rank_order_not_date_order():
    best, worst = (articles(x) for x in lists(fact_page("money", WHOLE)))
    assert [re.search(r"[+−]₹[\d,]+", a)[0] for a in best] == [
        "+₹900", "+₹800", "+₹700", "+₹600", "+₹500",
    ]
    assert [re.search(r"[+−]₹[\d,]+", a)[0] for a in worst] == [
        "−₹3,100", "−₹2,900", "−₹2,700", "−₹2,300", "−₹2,100",
    ]


def test_each_row_carries_its_rank():
    best, _ = (articles(x) for x in lists(fact_page("money", WHOLE)))
    assert [a.split(" ")[0] for a in best] == ["1", "2", "3", "4", "5"]


def test_a_row_says_instrument_side_quantity_prices_hold_and_rupees():
    best, _ = (articles(x) for x in lists(fact_page("money", WHOLE)))
    for part in ("WIDGETOIL", "Buy", "Qty 100", "100.00 → 110.00", "60 min", "+₹900"):
        assert part in best[0], part


def test_no_day_grouping_is_left_on_the_page():
    assert not re.search(r"Day \d", page_of(WHOLE))


def test_the_see_all_list_is_grouped_by_list_not_by_day():
    groups = S.groups("money", SF.record_context(WHOLE))
    assert [g["title"] for g in groups] == ["Best five", "Worst five", "Held past the day"]
    assert [g["trade_count"] for g in groups] == [5, 5, 4]
    assert [t["net"] for t in groups[0]["trades"]] == [900, 800, 700, 600, 500]


def test_a_trade_in_both_lists_is_counted_once_on_the_see_all_list():
    few = [trip("a", 300), trip("b", 200), trip("c", -100)]
    assert sum(g["trade_count"] for g in S.groups("money", SF.record_context(few))) == 3


def test_a_filter_narrows_the_lists_and_keeps_their_names():
    got = TL.listing("money", SF.record_context(SAME_DAY), {"result": "losers"}, {})
    assert [g["title"] for g in got["groups"]] == ["Worst five"]


def test_held_rows_stay_on_the_page_while_the_list_is_short():
    page = fact_page("money", WHOLE)
    assert page.count('<article class="trade">') == 14
    assert "13 months 10 days" in readable(page.split('class="evidence__caption"')[1])


def test_a_long_list_of_holdings_goes_behind_the_link_and_the_ranks_stay():
    many = [share(f"h{i}", 10 + i, 40) for i in range(S.INLINE_TRADES)]
    page = fact_page("money", SAME_DAY + many)
    assert page.count('<article class="trade">') == 10
    assert 'href="/mirror/fact/money/trades"' in page


# ---------- Side by side where there is room ----------


def test_the_lists_sit_side_by_side_on_a_wide_screen_and_stack_on_a_phone():
    css = Path("services/production/api/static/css/app.css").read_text()
    wide = re.search(
        r"@media \(min-width: (\d+)px\) \{(.*?)\n\}", css[css.index(".ranked-lists"):], re.DOTALL
    )
    assert wide, "no wide rule after .ranked-lists"
    assert int(wide[1]) > 430  # the phone column
    assert re.search(r"\.ranked-lists \{[^}]*grid-template-columns: repeat\(2", wide[2])
    assert ".screen--wide" in wide[2]


def test_only_this_fact_widens_its_screen():
    assert 'class="screen screen--wide"' in fact_page("money", WHOLE)
    assert "screen--wide" not in fact_page("worst-days", WHOLE)


# ---------- The hook is said only when it is true ----------


def test_all_ten_in_one_book_is_the_same_place():
    assert found(WHOLE).same_place == "WIDGETOIL options"
    page = page_of(WHOLE)
    assert HOOK in page
    assert "All 10 are in one book: WIDGETOIL options." in page


def test_a_list_in_two_books_is_not_the_same_place_and_is_told_as_counted():
    trips = [trip("n1", 5000, symbol="WIDGETIDX"), *SAME_DAY]
    assert found(trips).same_place is None
    page = page_of(trips)
    assert HOOK not in page
    assert "Best five: 4 in WIDGETOIL options, 1 in WIDGETIDX options." in page
    assert "Worst five: 5 in WIDGETOIL options." in page


def test_a_trade_in_both_lists_is_not_ten_trades():
    few = [trip(f"f{i}", 100 - i * 50) for i in range(6)]
    assert found(few).same_place is None
    assert HOOK not in page_of(few)


def test_the_hours_are_told_as_counted():
    assert (
        "4 of the 5 best were opened from 5 pm on, and 5 of the 5 worst from 8 pm on."
        in page_of(WHOLE)
    )


def test_worst_trades_mostly_before_eight_are_told_from_five():
    early = [dataclasses.replace(t, entry_ts=t.entry_ts.replace(hour=18)) for t in WORST]
    assert (
        "4 of the 5 best were opened from 5 pm on, and 5 of the 5 worst from 5 pm on."
        in page_of(BEST + early + MIDDLE)
    )


def test_a_morning_trader_reads_no_sentence_about_evenings():
    morning = [dataclasses.replace(t, entry_ts=t.entry_ts.replace(hour=10)) for t in BEST + WORST]
    page = page_of(morning + MIDDLE)
    assert "from 5 pm on" not in page and "from 8 pm on" not in page


def test_the_durations_are_told_as_medians_with_no_sentence_about_them():
    page = page_of(WHOLE)
    assert "Your best five ran a median of 60 min." in page
    assert "Your worst five lost a median of ₹2,700 each, in a median of 11 min." in page
    for line in CUT:
        assert line not in page, "rule 3: the page describes, and explains nothing"


def test_a_list_with_a_loser_in_its_best_five_gets_no_durations():
    page = page_of([trip(f"y{i}", -10 * (i + 1)) for i in range(10)])
    assert "ran a median of" not in page


def test_fewer_than_five_trades_a_side_gets_no_durations():
    page = page_of([trip("a", 300), trip("b", -100)])
    assert "ran a median of" not in page


def test_nothing_on_the_page_says_to_hold_longer():
    page = page_of(WHOLE).lower()
    assert "hold longer" not in page
    assert "let your winners" not in page and "cut your losers" not in page


# ---------- The button ----------


def next_chapter(page: str) -> str:
    return re.search(r'<div class="next-chapter">.*?</div>', page, re.DOTALL)[0]


def test_the_button_names_the_next_chapter_by_its_real_title():
    block = next_chapter(fact_page("money", WHOLE))
    assert f">Chapter 2: {S.chapter(2).name}<" in block
    assert f'href="{S.chapter_href(2)}"' in block


def test_the_title_is_read_from_the_map(monkeypatch):
    renamed = tuple(
        dataclasses.replace(c, name="A title the map decided") if c.number == 2 else c
        for c in S.CHAPTERS
    )
    monkeypatch.setattr(S, "CHAPTERS", renamed)
    assert ">Chapter 2: A title the map decided<" in next_chapter(fact_page("money", WHOLE))


def test_the_page_ends_with_the_button():
    page = fact_page("money", WHOLE)
    assert page.index('class="next-chapter"') > page.rindex('<article class="trade">')


def test_the_figure_above_the_button_is_computed():
    block = readable(next_chapter(fact_page("money", WHOLE)))
    assert "Everything you closed the same day: −₹9,800. See where it went." in block


def test_a_same_day_gain_does_not_ask_where_it_went():
    block = readable(next_chapter(fact_page("money", [trip("a", 300), trip("b", -100)])))
    assert "See where it went" not in block
    assert "Everything you closed the same day: +₹200." in block


def test_with_nothing_closed_the_same_day_the_button_stands_alone():
    block = readable(next_chapter(fact_page("money", ETF)))
    assert "Everything you closed" not in block and "Chapter 2" in block


# ---------- The card ----------


def test_the_card_says_the_headline():
    assert HEADLINE in readable(chapter_page(1, WHOLE))


def test_the_card_of_another_trader_says_what_his_lists_came_to():
    page = readable(chapter_page(1, SAME_DAY))
    assert HEADLINE not in page
    assert "Your best five came to +₹3,500. Your worst five came to −₹13,100." in page


# ---------- Through the app ----------


def test_a_position_held_eight_days_reads_in_days_on_the_fact_page(uploaded):  # noqa: F811
    rows = articles(uploaded.get("/mirror/fact/money").text)
    assert any("Widget ETF" in a and "8 days" in a for a in rows)


def test_and_on_every_other_list_it_appears_in(uploaded):  # noqa: F811
    rows = articles(uploaded.get("/mirror/fact/risk/trades").text)
    assert any("Widget ETF" in a and "8 days" in a for a in rows)


def test_the_page_through_the_app_has_its_lists_and_its_button(uploaded):  # noqa: F811
    page = uploaded.get("/mirror/fact/money").text
    assert len(lists(page)) == 2
    assert not re.search(r"Day \d", text(page))
    assert f"Chapter 2: {S.chapter(2).name}" in text(page)


def test_no_trade_row_writes_its_hold_in_minutes_by_hand():
    for path in Path("services/production/api/templates").rglob("*.html"):
        assert "held_minutes" not in path.read_text(), path
