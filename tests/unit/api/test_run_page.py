"""The longest losing run reads as a story, on its page and its card [TICKET-820].

Rendered with the hand-worked history in tests/unit/mirror/test_run_story.py, and once
through a real upload for a position of two legs.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from services.production.api import scope_facts as SF
from services.production.api import scope_geometry as G
from tests.unit.api.test_scope_chapters import IMP, chapter_page, readable, trips_from
from tests.unit.api.test_scope_facts import fact_page
from tests.unit.api.test_upload import (  # noqa: F401 - fixtures used by name
    DUPES,
    client,
    engine,
    upload,
)
from tests.unit.mirror.test_run_story import DAY, EVENING, spread, trip


def page_of(trips=EVENING) -> str:
    return readable(fact_page("run", trips=trips))


def chart_parts(trips=EVENING) -> dict[str, str]:
    figs = SF.facts(SF.record_context(trips), IMP)
    return {p["role"]: p["d"] for p in figs["run"]["timeline"]["parts"]}


# ---------- The headline ----------


def test_the_headline_says_when_in_what_and_what_it_cost_with_the_year():
    html = fact_page("run", trips=EVENING)
    title = re.search(r'<h1 class="title fact__title">(.*?)</h1>', html, re.DOTALL)[1]
    assert readable(title) == "6 losses in a row, in one hour: 03 Mar 2026, WIDGETOIL options, −₹1,000."


def test_a_run_across_days_reads_true():
    trips = [
        trip("w", DAY, "09:00:00", "09:05:00", 10),
        trip("a", "2026-03-04", "15:00:00", "15:10:00", -800),
        trip("b", "2026-03-05", "09:20:00", "09:30:00", -900),
    ]
    page = page_of(trips)
    assert (
        "2 losses in a row, across 2 days: 04 Mar 2026 to 05 Mar 2026, WIDGETOIL options, −₹1,700."
        in page
    )
    assert "hours:" not in page


def test_a_run_in_a_mixed_book_reads_true():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -100),
        trip("b", DAY, "09:10:30", "09:20:00", -200, symbol="WIDGETIDX"),
        trip("c", DAY, "09:21:00", "09:30:00", -300, segment="FUT"),
    ]
    assert (
        "3 losses in a row, in 30 minutes: 03 Mar 2026, "
        "WIDGETOIL options, WIDGETIDX options and futures, −₹600."
    ) in page_of(trips)


def test_a_book_with_a_common_name_reads_in_lower_case():
    trips = [trip("a", DAY, "09:00:00", "09:10:00", -100, symbol="CRUDEOIL")]
    assert "1 loss, in 10 minutes: 03 Mar 2026, crude options, −₹100." in page_of(trips)


def test_a_span_some_way_off_a_whole_hour_says_about():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -100),
        trip("b", DAY, "10:00:00", "11:40:00", -100),
    ]
    assert "2 losses in a row, in about three hours:" in page_of(trips)


def test_a_position_held_past_the_day_claims_no_span():
    trips = [trip("a", DAY, "15:00:00", "10:00:00", -100, closed_day="2026-03-04")]
    assert "1 loss: 03 Mar 2026, WIDGETOIL options, −₹100." in page_of(trips)


def test_the_mirrors_sentence_stays_true_and_word_for_word():
    assert "Your longest run of consecutive losers was 6 trades." in page_of()


def test_a_fact_in_a_state_keeps_its_plain_title():
    page = fact_page("run", trips_from([100, 200]))
    assert '<h1 class="title fact__title">Longest losing run</h1>' in page


# ---------- Longest and costliest ----------


def test_longest_and_costliest_both_show_when_they_differ():
    page = page_of()
    assert "Your longest run: 6 losses, 03 Mar 2026, WIDGETOIL options, −₹1,000." in page
    assert (
        "Your costliest run: 2 losses, 04 Mar 2026 to 05 Mar 2026, WIDGETIDX options, −₹1,700."
        in page
    )


def test_one_run_that_is_both_reads_one_line():
    trips = [t for t in EVENING if t.symbol == "WIDGETOIL"]
    page = page_of(trips)
    assert (
        "Your longest run is also your costliest: 6 losses, 03 Mar 2026, WIDGETOIL options, −₹1,000."
        in page
    )
    assert "Your longest run:" not in page and "Your costliest run:" not in page


# ---------- The three plain lines ----------


def test_the_three_plain_lines_are_said_as_ruled():
    page = page_of()
    assert "You switched between calls and puts 3 times. Both lost." in page
    assert "After two losses you doubled your size, then tripled it (50 → 100 → 150)." in page
    assert "4 of 5 times, you were back in within 2 minutes." in page


def test_a_run_with_no_switch_or_rise_or_quick_return_says_none_of_them():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -100),
        trip("b", DAY, "09:30:00", "09:40:00", -100),
    ]
    page = page_of(trips)
    assert "You switched" not in page
    assert "your size" not in page
    assert "back in within" not in page


def test_one_switch_reads_once():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -100),
        trip("b", DAY, "09:30:00", "09:40:00", -100, kind="PE"),
    ]
    assert "You switched between calls and puts once. Both lost." in page_of(trips)


@pytest.mark.parametrize(
    ("sizes", "line"),
    [
        ((50, 100), "After one loss you doubled your size (50 → 100)."),
        ((50, 150), "After one loss you tripled your size (50 → 150)."),
        ((50, 75), "After one loss you raised your size (50 → 75)."),
        ((50, 100, 400), "After one loss you raised your size (50 → 100 → 400)."),
    ],
)
def test_the_size_line_says_only_what_the_steps_are(sizes, line):
    trips = [
        trip(f"t{i}", DAY, f"09:{i:02d}:00", f"09:{i:02d}:30", -100, qty=qty)
        for i, qty in enumerate(sizes)
    ]
    assert line in page_of(trips)


def test_a_run_across_days_says_no_count_of_returns_but_its_rows_keep_their_gaps():
    trips = [
        trip("a", "2026-03-04", "15:00:00", "15:10:00", -100),
        trip("b", "2026-03-04", "15:10:12", "15:20:00", -100),
        trip("c", "2026-03-05", "09:00:00", "09:10:00", -100),
    ]
    page = page_of(trips)
    assert "back in within" not in page
    assert "Back in after 0:12" in page


# ---------- What must stay out ----------


@pytest.mark.parametrize(
    "words",
    ["worst hour", "best hour", "streaks of", "21%", "Stopping for the day", "Test your own stop"],
)
def test_what_was_ruled_out_is_on_neither_the_page_nor_the_card(words):
    assert words not in page_of()
    assert words not in readable(chapter_page(2, trips=EVENING))


def test_the_old_figure_and_its_day_labels_are_gone():
    page = page_of()
    assert "Day 1" not in page
    assert "one square per trade" not in page


# ---------- The rows ----------


def test_each_day_of_a_run_is_named_by_its_date_alone():
    trips = [
        trip("a", "2026-03-04", "15:00:00", "15:10:00", -100),
        trip("b", "2026-03-05", "09:00:00", "09:10:00", -100),
    ]
    html = fact_page("run", trips=trips)
    assert re.findall(r'<span class="trades__day">(.*?)</span>', html) == ["04 Mar 2026", "05 Mar 2026"]
    assert "Day " not in readable(html)


def test_a_row_shows_the_gap_as_minutes_and_seconds():
    page = fact_page("run", trips=EVENING)
    rows = re.findall(r'<article class="trade">.*?</article>', page, re.DOTALL)
    assert len(rows) == 6  # the trade after the run is not one of the trades behind it
    assert "Back in after" not in rows[0]
    assert "Back in after 0:12" in readable(rows[1])
    assert "Back in after 1:30" in readable(rows[2])
    assert "5000 CE" in rows[1] and "Qty 50" in rows[1] and "10.00 → 9.00" in rows[1]


def test_a_trade_opened_before_the_last_closed_says_so_with_no_gap():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -100),
        trip("b", DAY, "09:05:00", "09:20:00", -100),
    ]
    page = page_of(trips)
    assert "Opened before the last trade closed" in page
    assert "Back in after" not in page


def test_a_row_on_another_fact_has_no_gap():
    assert "Back in after" not in readable(fact_page("worst-days", trips=EVENING))


# ---------- After the run ----------


def test_the_first_trade_after_the_run_and_the_days_close_show():
    page = page_of()
    after = page.split("The first trade after the run")[1]
    assert "Back in after 1:00" in after
    assert "+₹400" in after
    assert "That day closed at −₹400." in after


def test_a_run_across_days_names_the_day_that_closed():
    trips = [
        trip("a", "2026-03-04", "15:00:00", "15:10:00", -800),
        trip("b", "2026-03-05", "09:20:00", "09:30:00", -900),
        trip("e", "2026-03-05", "10:00:00", "10:05:00", 50),
    ]
    assert "05 Mar 2026 closed at −₹850." in page_of(trips)


def test_a_first_trade_on_a_later_day_names_the_day_that_closed():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -100),
        trip("e", "2026-03-04", "10:00:00", "10:05:00", 50),
    ]
    assert "03 Mar 2026 closed at −₹100." in page_of(trips)


def test_a_run_at_the_end_of_the_file_has_no_after_section_and_keeps_its_close():
    page = page_of([trip("a", DAY, "09:00:00", "09:10:00", -100)])
    assert "The first trade after the run" not in page
    assert "That day closed at −₹100." in page


# ---------- The next button ----------


def test_the_page_ends_with_a_link_to_the_clock_and_what_happened_at_that_hour():
    html = fact_page("run", trips=EVENING)
    assert (
        "This run started at 18:00. Your trades in WIDGETOIL options opened in the 18:00 hour "
        "came to −₹1,000, over 6 trades."
    ) in readable(html)
    assert re.search(
        r'<a class="btn btn--primary btn--block" href="/mirror/fact/clock[^"]*">See the clock</a>',
        html,
    )
    assert html.rindex("See the clock") > html.rindex("The trades behind this")


def test_a_run_across_days_says_the_date_it_started():
    trips = [
        trip("a", "2026-03-04", "15:00:00", "15:10:00", -800),
        trip("b", "2026-03-05", "09:20:00", "09:30:00", -900),
    ]
    assert "This run started on 04 Mar 2026 at 15:00." in page_of(trips)


# ---------- The timeline ----------


def test_figure_one_is_the_run_as_a_timeline_not_the_strip():
    html = fact_page("run", trips=EVENING)
    assert "Figure 1 · The run, trade by trade" in readable(html)
    assert "chart__put" in html and "chart__ink" in html and "chart__stroke" in html


def test_each_option_is_a_call_or_put_marker_and_the_trade_after_the_run_is_on_it():
    parts = chart_parts()
    # r1, r2, r5 and the trade after are calls; r3, r4, r6 are puts.
    assert parts["ink"].count("M") == 4
    assert parts["put"].count("M") == 3
    assert "faint" not in parts


def test_a_bigger_size_draws_a_bigger_marker():
    radii = {float(a) for a in re.findall(r"a([\d.]+) ", chart_parts()["put"])}
    assert len(radii) == 2  # puts at 100 and 150; r3 and r6 share a size


def test_a_trade_that_is_not_an_option_draws_a_plain_marker():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -100, segment="FUT"),
        trip("b", DAY, "09:11:00", "09:20:00", -100, segment="FUT", qty=500),
    ]
    parts = chart_parts(trips)
    assert parts["faint"].count("M") == 2
    assert "ink" not in parts and "put" not in parts
    assert len(set(re.findall(r"h([\d.]+)v", parts["faint"]))) == 1  # no size on a plain marker


def test_a_position_of_two_legs_draws_one_plain_marker():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -100),
        spread("b", DAY, "09:11:00", "09:20:00", -100),
    ]
    parts = chart_parts(trips)
    assert parts["ink"].count("M") == 1
    assert parts["faint"].count("M") == 1


def test_a_run_across_days_breaks_the_axis_instead_of_drawing_the_night():
    trips = [
        trip("a", "2026-03-04", "15:00:00", "15:10:00", -800),
        trip("b", "2026-03-05", "09:20:00", "09:30:00", -900),
    ]
    assert chart_parts(trips)["dash"].count("M") == 1
    page = page_of(trips)
    assert "04 Mar 2026 15:00" in page and "05 Mar 2026 09:30" in page


def test_the_axis_says_when_and_the_line_says_where_it_went():
    page = page_of()
    assert "18:00" in page and "19:30" in page
    assert "Running result from the run's first trade: lowest −₹1,000, last −₹600." in page


def test_a_marker_legend_appears_only_for_what_is_drawn():
    def legend(trips):
        return page_of(trips).split("Figure 1")[1].split("trades behind")[0]

    assert "call" in legend(EVENING)
    assert "call" not in legend([trip("a", DAY, "09:00:00", "09:10:00", -100, segment="FUT")])


def test_the_chart_is_laid_out_as_worked_by_hand():
    """100 x 50, inset 8: x runs 8 to 92, and y puts 0 at 8 and -100 at 42."""
    got = G.chart_run_timeline(
        start_x=0,
        points=[
            {"x": 0.5, "y": -100, "kind": "call", "size": 1},
            {"x": 1, "y": 0, "kind": "plain", "size": None},
        ],
        band=(0, 0.5),
        breaks=[],
        hours=[0.25],
        w=100,
        h=50,
    )
    parts = {p["role"]: p["d"] for p in got["parts"]}
    assert (got["w"], got["h"]) == (100, 50)
    assert parts["stroke"] == "M8 8L50 42L92 8"
    assert parts["band"] == "M8 0h42v50h-42Z"
    assert parts["axis"] == "M0 8H100M29 46V50"
    assert parts["ink"] == G.circle(50, 42, 5.5)
    assert parts["faint"] == "M89.5 5.5h5v5h-5Z"


def test_the_kits_strip_is_still_the_dials_chart():
    assert "run" in G.CHARTS
    assert "run_timeline" not in G.CHARTS  # parity-tested charts are the kit's alone


# ---------- The card ----------


def test_the_card_says_when_in_what_and_what_it_cost_and_keeps_the_mirrors_sentence():
    page = readable(chapter_page(2, trips=EVENING))
    assert "03 Mar 2026, WIDGETOIL options, −₹1,000." in page
    assert "Your longest run of consecutive losers was 6 trades." in page
    assert "one square per trade" not in page


def test_the_card_draws_the_timeline():
    assert "chart__put" in chapter_page(2, trips=EVENING)


# ---------- A position of several legs, through a real upload ----------


LOSING_SPREAD = [
    ("10:00:00", 5000, "CALL", "BUY", "20.00"),
    ("10:10:00", 5000, "CALL", "SELL", "15.00"),  # -500
    ("10:11:00", 5100, "CALL", "BUY", "10.00"),
    ("10:11:05", 5000, "CALL", "SELL", "30.00"),
    ("11:00:00", 5100, "CALL", "SELL", "4.00"),  # -600
    ("11:00:05", 5000, "CALL", "BUY", "31.00"),  # -100, so the position is -700
    ("11:30:00", 5000, "PUT", "BUY", "20.00"),
    ("11:40:00", 5000, "PUT", "SELL", "18.00"),  # -200
    ("11:41:00", 5000, "PUT", "BUY", "10.00"),
    ("11:50:00", 5000, "PUT", "SELL", "12.00"),  # +200, the first trade after
]


def spread_file() -> bytes:
    header = (DUPES / "clean.csv").read_text().splitlines()[0]
    rows = [
        f"2026-10-14,{time},WIDGETOIL 19 NOV {strike} {kind},{side},INTRADAY,MCX,Commodity,100,"
        f"{price},{Decimal(price) * 100:.2f},Traded"
        for time, strike, kind, side, price in LOSING_SPREAD
    ]
    return ("\n".join([header, *rows]) + "\n").encode()


def test_a_position_of_several_legs_reads_as_one_trade(client, engine):  # noqa: F811
    assert upload(client, content=spread_file()).status_code == 303
    html = client.get("/mirror/fact/run").text
    page = readable(html)
    assert "3 losses in a row" in page
    assert "WIDGETOIL options, −₹1,400." in page
    assert html.count('<article class="trade">') == 3
    assert "WIDGETOIL · 2 legs" in page
    assert "Back in after 1:00" in page  # 10:10:00 to 10:11:00, the position's one gap
    assert "You switched" not in page  # the position is neither, so call and put never meet
    assert "your size" not in page
