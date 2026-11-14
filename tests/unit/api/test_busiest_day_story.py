"""Chapter 3: the busiest day told as a story, and fact pages that add something [TICKET-827].

Synthetic trades, worked by hand. The busiest day is 02 Sep 2026, six trades:

    09:20-09:23  WIDGETIDX 5000 CE  one lot    +50
    09:30-09:33  WIDGETIDX 5000 PE  one lot   -300
    09:40-09:43  WIDGETIDX 5000 PE  one lot   -100
    09:50-09:53  WIDGETIDX 5000 CE  one lot   +200
    10:00-10:03  WIDGETIDX 5000 PE  one lot    -70
    18:30-18:33  WIDGETOIL 5100 CE  one lot  +1000

Five of the six are WIDGETIDX options. Call to put, put to call, call to put: 3 switches.
WIDGETIDX options: 50 - 300 - 100 + 200 - 70 = -220. The whole day: -220 + 1000 = +780.
One trade each on 01 Sep and 03 Sep, so the normal day is 1.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from services.production.api import scope_facts as SF
from services.production.api import scope_geometry as G
from services.production.api import scope_map as S
from services.production.api import trade_list as TL
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_chapter_three_describes import CLOSED, DOWN, card_of, one_day
from tests.unit.api.test_scope_chapters import IMP, chapter_page, readable
from tests.unit.api.test_scope_facts import fact_page


def option(when, kind, net, *, day="2026-09-02", strike=5000, lots=1, held=180, symbol="WIDGETIDX"):
    entry = datetime.fromisoformat(f"{day}T{when}:00+05:30")
    line = mx.TradeLine(symbol, "OPT", "Buy", lots * 50, Decimal(10), Decimal(11), Decimal(net),
                        Decimal(strike), kind, entry)
    return mx.Trip(f"{day}-{when}", symbol, day, entry, entry + timedelta(seconds=held), held,
                   Decimal(net), lots, s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True, lines=(line,))


def share(when, net, *, day="2026-09-02", symbol="WIDGETETF"):
    entry = datetime.fromisoformat(f"{day}T{when}:00+05:30")
    line = mx.TradeLine(symbol, "EQ", "Buy", 10, Decimal(100), Decimal(101), Decimal(net),
                        entry_ts=entry)
    return mx.Trip(f"{day}-{when}", symbol, day, entry, entry + timedelta(minutes=3), 180,
                   Decimal(net), 1, s.RiskUnitSourceV1.UNAVAILABLE, is_option=False, lines=(line,))


QUIET = [option("09:20", "CE", 10, day="2026-09-01"), option("09:20", "CE", 10, day="2026-09-03")]
"""One trade on each of two other days: they make the normal day, and tell no story."""

BOOK = [
    option("09:20", "CE", 50),
    option("09:30", "PE", -300),
    option("09:40", "PE", -100),
    option("09:50", "CE", 200),
    option("10:00", "PE", -70),
]
DAY = [*QUIET[:1], *BOOK, option("18:30", "CE", 1000, strike=5100, symbol="WIDGETOIL"), *QUIET[1:]]
"""The day the module docstring works by hand, among its two quiet days."""


def story_of(trips) -> str:
    """What the busiest-day page says before its figures: the story."""
    page = fact_page("busiest", trips)
    head = page.split('<h1 class="title fact__title">')[1].split("</h1>", 1)[1]
    head = head.split("The trades behind this")[0].split('<figure class="figure">')[0]
    return readable(head)


# ---------- The story ----------


def test_the_story_of_the_day_the_docstring_works():
    assert (
        "02 Sep 2026: 6 trades. 5 were WIDGETIDX options, all on the 5000 strike, one lot each. "
        "You switched between the call and the put 3 times between 9:20 am and 10:03 am, "
        "holding each about 3 minutes. "
        "WIDGETIDX options that day: −₹220. All 6 trades that day, every book: +₹780."
    ) in story_of(DAY)


def test_the_page_opens_with_the_story_straight_under_the_title():
    page = fact_page("busiest", DAY)
    found = re.search(r'</h1>\s*<p class="mirror">(.*?)</p>', page, re.DOTALL)
    assert readable(found[1]).startswith("02 Sep 2026: 6 trades.")


def test_a_minus_and_a_clock_time_stay_on_one_line():
    """Found at 390 px on the real file: a minus ended one line and its rupees began the next,
    and a time split from its am or pm."""
    page = fact_page("busiest", DAY)
    assert page.count('<span class="opening-figure">') == 4  # two times, two results
    assert fact_page("down", DOWN).count('<span class="opening-figure">') == 2


def test_the_story_is_three_short_paragraphs_on_a_phone():
    """Found at 390 px: as one paragraph it ran to a whole screen."""
    head = fact_page("busiest", DAY).split("</h1>")[1].split('<figure class="figure">')[0]
    assert head.count('<p class="mirror">') == 3


def test_the_metric_counts_what_the_docstring_counts():
    story = mx.busiest_day_story(DAY, "2026-09-02")
    assert (story.trades, story.net) == (6, Decimal(780))
    assert (story.book, story.book_trades, story.book_net) == ("WIDGETIDX options", 5, Decimal(-220))
    assert (story.strike, story.lots, story.switches) == (Decimal(5000), 1, 3)
    assert (story.median_hold_seconds, story.longest_hold_seconds, story.holds_alike) == (180, 180, True)
    assert [t.side for t in story.strip] == ["CE", "PE", "PE", "CE", "PE"]


# ---------- Each part shows only when it is true ----------


def test_no_book_with_more_than_half_of_the_day_says_so_and_names_none():
    day = [option("09:20", "CE", 50), option("09:30", "PE", 50),
           option("09:40", "CE", 50, symbol="WIDGETOIL"), option("09:50", "PE", 50, symbol="WIDGETOIL"),
           *QUIET]
    story = story_of(day)
    assert "02 Sep 2026: 4 trades. No one book made up more than half of them." in story
    assert " were " not in story
    assert "switched" not in story
    assert "All 4 trades that day: +₹200." in story


def test_half_is_not_more_than_half():
    day = [option("09:20", "CE", 50), share("09:30", 50), *QUIET]
    assert "No one book made up more than half of them." in story_of(day)


def test_a_book_with_every_trade_says_all_and_has_one_figure():
    day = [option("09:20", "CE", 50), option("09:30", "CE", -80), *QUIET]
    story = story_of(day)
    assert "02 Sep 2026: 2 trades. All 2 were WIDGETIDX options, all on the 5000 strike, one lot each." in story
    assert "All 2 trades that day: −₹30." in story
    assert "WIDGETIDX options that day" not in story
    assert "every book" not in story


def test_two_strikes_are_said_as_two_and_the_switches_are_between_calls_and_puts():
    day = [option("09:20", "CE", 50), option("09:30", "PE", 50, strike=5100),
           option("09:40", "CE", 50), *QUIET]
    story = story_of(day)
    assert "All 3 were WIDGETIDX options, on 2 strikes, one lot each." in story
    assert "You switched between calls and puts 2 times between" in story
    assert "the call and the put" not in story


def test_different_sizes_are_said_as_a_range_not_as_one_lot_each():
    day = [option("09:20", "CE", 50), option("09:30", "CE", 50, lots=3), *QUIET]
    story = story_of(day)
    assert "all on the 5000 strike, 1 to 3 lots each." in story
    assert "one lot" not in story


def test_the_same_larger_size_is_said_with_its_count():
    day = [option("09:20", "CE", 50, lots=2), option("09:30", "CE", 50, lots=2), *QUIET]
    assert "all on the 5000 strike, 2 lots each." in story_of(day)


def test_one_switch_is_one_time():
    day = [option("09:20", "CE", 50), option("09:30", "PE", 50), *QUIET]
    assert "You switched between the call and the put 1 time between" in story_of(day)


def test_no_switch_says_they_were_all_one_side():
    day = [option("09:20", "PE", 50), option("09:30", "PE", 50), *QUIET]
    story = story_of(day)
    assert "switched" not in story
    assert "All 2 were puts, between 9:20 am and 9:33 am, holding each about 3 minutes." in story


def test_holds_that_differ_are_not_said_as_each_about_one_figure():
    """Holds of 1, 3 and 60 minutes: the middle one is 3, and "each about 3" would be false."""
    day = [option("09:20", "CE", 50, held=60), option("09:30", "PE", 50, held=180),
           option("09:40", "CE", 50, held=3600), *QUIET]
    story = story_of(day)
    assert "holding each" not in story
    assert "You held them about 3 minutes at the median, and 60 minutes at the longest." in story


def test_a_hold_under_a_minute_is_not_called_zero_minutes():
    day = [option("09:20", "CE", 50, held=20), option("09:30", "PE", 50, held=25), *QUIET]
    story = story_of(day)
    assert "holding each under a minute." in story
    assert "0 minutes" not in story


def test_a_trade_held_past_the_day_is_not_in_the_story():
    """TICKET-855: Chapter 3 reads same-day trades, so the page is what it is without it."""
    held_over = option("09:30", "PE", 50)
    held_over = replace(held_over, exit_ts=held_over.entry_ts + timedelta(days=2), holding_seconds=172800)
    same_day = [option("09:20", "CE", 50), *QUIET]
    assert story_of([same_day[0], held_over, *QUIET]) == story_of(same_day)


def test_a_day_of_shares_tells_no_strike_lots_or_switches_and_draws_no_strip():
    day = [share("09:20", 50), share("09:30", -20), *QUIET]
    page = fact_page("busiest", day)
    story = story_of(day)
    assert "All 2 were Stocks and ETFs. You traded them between 9:20 am and 9:33 am, holding each about 3 minutes." in story
    for word in ("strike", " lot", "switched", "call", "put"):
        assert word not in story, word
    assert "chart__call" not in page
    assert "chart__put" not in page


def test_a_day_of_one_trade_says_only_that():
    day = [option("09:20", "CE", 50)]
    story = story_of(day)
    assert "02 Sep 2026: 1 trade. That was the only trade that day." in story
    assert "switched" not in story
    assert "All 1 trade that day: +₹50." not in story
    assert "That trade: +₹50." in story


def test_a_position_of_several_legs_is_not_a_switch():
    """Call, position, call: the position holds both sides, so it sits in neither row and the
    calls either side of it did not switch."""
    entry = datetime.fromisoformat("2026-09-02T09:30:00+05:30")
    legs = tuple(
        mx.TradeLine("WIDGETIDX", "OPT", side, 50, Decimal(10), Decimal(11), Decimal(25),
                     Decimal(strike), kind, entry)
        for side, strike, kind in (("Buy", 5000, "CE"), ("Sell", 5100, "PE"))
    )
    position = mx.Trip("spread", "WIDGETIDX", "2026-09-02", entry, entry + timedelta(minutes=3), 180,
                       Decimal(50), 1, s.RiskUnitSourceV1.STRUCTURE_MAX_LOSS, is_option=True, lines=legs)
    day = [option("09:20", "CE", 50), position, option("09:40", "CE", 50), *QUIET]
    story = mx.busiest_day_story(day, "2026-09-02")
    assert story.switches == 0
    assert [t.side for t in story.strip] == ["CE", "both", "CE"]
    assert story.lots is None and story.lots_low is None
    assert "one lot" not in story_of(day)


def test_a_position_alone_says_there_is_no_call_or_put_to_follow():
    entry = datetime.fromisoformat("2026-09-02T09:30:00+05:30")
    legs = tuple(
        mx.TradeLine("WIDGETIDX", "OPT", side, 50, Decimal(10), Decimal(11), Decimal(25),
                     Decimal(strike), kind, entry)
        for side, strike, kind in (("Buy", 5000, "CE"), ("Sell", 5100, "PE"))
    )
    positions = [
        mx.Trip(f"p{i}", "WIDGETIDX", "2026-09-02", entry + timedelta(hours=i),
                entry + timedelta(hours=i, minutes=3), 180, Decimal(50), 1,
                s.RiskUnitSourceV1.STRUCTURE_MAX_LOSS, is_option=True, lines=legs)
        for i in range(2)
    ]
    assert "These were positions of several legs, so there is no call or put to follow." in story_of(
        [*positions, *QUIET]
    )


def test_a_trade_with_no_stored_legs_is_named_only_as_far_as_is_known():
    """Old fixtures and old rows have no lines: nothing about a strike or a side is said."""
    trips = one_day([10, 10, 10, 10], "2026-09-01") + one_day([10], "2026-09-02")
    story = story_of(trips)
    assert "01 Sep 2026: 4 trades. All 4 were WIDGETOIL options." in story
    assert "strike" not in story
    assert "switched" not in story
    assert "chart__call" not in fact_page("busiest", trips)


def test_it_follows_whatever_day_was_busiest_not_one_file():
    later = [option("09:20", "CE", 1, day="2026-10-05", symbol="WIDGETOIL"),
             option("09:30", "PE", 1, day="2026-10-05", symbol="WIDGETOIL"),
             option("09:40", "PE", 1, day="2026-10-05", symbol="WIDGETOIL")]
    story = story_of([*later, *BOOK[:2]])
    assert story.startswith("05 Oct 2026: 3 trades. All 3 were WIDGETOIL options")


# ---------- The story's figure and the list's figure each say what they cover ----------


def test_the_list_says_it_covers_every_book_and_its_total_is_the_whole_day():
    page = fact_page("busiest", DAY)
    assert "Every trade on 02 Sep 2026, in every book." in readable(page)
    head = re.search(r'class="trades__title">(.*?)</div>', page, re.DOTALL)[1]
    assert "6 trades · +₹780" in readable(head)


# ---------- The call/put strip ----------


def test_the_strip_draws_each_trade_in_its_row_and_outlines_those_that_made_money():
    """100 wide, two trades, so each has 50: the bar is 35 wide, 7.5 in from its edge.
    The call is the bigger result, so 40 high on the top row's baseline at 44. The put is half
    that on the bottom row's baseline at 96."""
    chart = G.chart_call_put([("CE", 100.0), ("PE", -50.0)], 100, 96)
    parts = {p["role"]: p["d"] for p in chart["parts"]}
    assert (chart["w"], chart["h"]) == (100, 96)
    assert parts == {
        "axis": "M0 44H100M0 96H100",
        "call": "M7.5 4h35v40h-35Z",
        "put": "M57.5 76h35v20h-35Z",
        "won": "M7.5 4h35v40h-35Z",
    }


def test_a_trade_that_finished_level_is_still_drawn_and_is_not_outlined():
    parts = {p["role"]: p["d"] for p in G.chart_call_put([("CE", 0.0)], 100, 96)["parts"]}
    assert parts["call"] == "M15 41h70v3h-70Z"
    assert "won" not in parts


def test_a_position_of_several_legs_is_drawn_in_both_rows():
    parts = {p["role"]: p["d"] for p in G.chart_call_put([("both", 10.0)], 100, 96)["parts"]}
    assert parts["light"] == "M15 4h70v40h-70ZM15 56h70v40h-70Z"
    assert "call" not in parts
    assert "put" not in parts


def test_the_strip_is_not_one_of_the_kits_charts():
    """The parity test holds every chart in G.CHARTS to the kit's JavaScript, which has no strip."""
    assert G.chart_call_put not in G.CHARTS.values()


def test_the_page_draws_the_strip_with_the_book_it_covers():
    page = fact_page("busiest", DAY)
    assert page.count('class="chart__call"') == 1
    assert page.count('class="chart__put"') == 1
    assert "The 5 WIDGETIDX options trades that day, in order." in readable(page)
    assert "Calls on the top row, puts on the bottom." in readable(page)
    assert "Outlined bars made money." in readable(page)
    assert "several legs" not in readable(page)


def test_with_no_book_to_follow_the_strip_covers_every_option_that_day():
    day = [option("09:20", "CE", 50), option("09:30", "PE", 50, symbol="WIDGETOIL"), share("09:40", 5),
           share("09:50", 5, symbol="WIDGETTWO"), share("10:00", 5, symbol="WIDGETTWO"), *QUIET]
    # Shares are one book, with 3 of the 5 trades: the options are outside it, and still drawn.
    assert mx.busiest_day_story(day, "2026-09-02").book == "Stocks and ETFs"
    assert "The 2 option trades that day, in order." in readable(fact_page("busiest", day))


def test_the_list_keeps_strike_and_side_on_its_rows():
    assert "WIDGETIDX 5000 CE" in fact_page("busiest", DAY)
    assert "WIDGETIDX 5000 PE" in fact_page("busiest", DAY)


# ---------- The pages stop repeating their cards ----------


def card_sentences(page: str, number: int) -> list[str]:
    card = page.split(f'<span class="story-card__num">{number}</span>')[1].split("story-card__foot")[0]
    return [readable(x) for x in re.findall(r'<span class="mirror mirror--card">(.*?)</span>\s*\n', card, re.DOTALL)]


def test_the_busiest_page_says_none_of_its_cards_sentences():
    page = readable(fact_page("busiest", DAY))
    said = card_sentences(chapter_page(3, DAY), 2)
    assert len(said) == 2
    for sentence in said:
        assert sentence not in page, sentence
    assert "trades per day" not in page


def test_the_busiest_card_keeps_the_frozen_line_true():
    page = readable(chapter_page(3, DAY))
    assert "Your normal day is 1 trades. Your busiest was 02 Sep 2026, at 6 — 6.00× that." in page


def test_the_down_page_says_only_the_opening_sentence_of_its_card():
    page = readable(fact_page("down", DOWN))
    said = card_sentences(chapter_page(3, DOWN), 1)
    assert said[0] == CLOSED
    assert CLOSED in page
    assert len(said) == 2
    for sentence in said[1:]:
        assert sentence not in page, sentence
    for table_line in ("Table 1", "Table 2", "Your other trades after two had closed", "Every other trade",
                       "A scratch trade ends the run."):
        assert table_line not in page, table_line


def test_the_down_page_says_what_it_counts_and_gives_both_averages_with_no_comparison():
    """DOWN (test_chapter_three_describes): 4 qualify, 2 right after two losses in a row
    averaging +137.5, the other 2 averaging -100.5."""
    page = readable(fact_page("down", DOWN))
    assert ("These are the 4 trades you opened once at least two earlier trades that day had closed. "
            "2 came right after two losses in a row, and averaged +₹137.5. "
            "The other 2 came when the two most recent had not both lost, and averaged −₹100.5.") in page
    for word in ("better", "worse", "more than", "less than", "higher", "lower"):
        assert word not in page, word


def test_the_down_page_with_nothing_on_the_other_side_gives_one_average():
    """-100, -200, then -300 and -400 each right after two losses: averaging -350, none other."""
    page = readable(fact_page("down", one_day([-100, -200, -300, -400])))
    assert "2 came right after two losses in a row, and averaged −₹350." in page
    assert "None came when the two most recent had not both lost." in page
    assert "The other" not in page


def test_the_down_page_says_who_counts_as_the_shared_definition_counts():
    """-100 then +50 then +60, +70: the last two each have two earlier trades closed, one of
    them a win. They qualify (b2_condition reads closed trades, not losses), and neither came
    right after two losses."""
    page = readable(fact_page("down", one_day([-100, 50, 60, 70])))
    assert "These are the 2 trades you opened once at least two earlier trades" in page
    assert "None came right after two losses in a row." in page
    assert "The other 2 came when the two most recent had not both lost, and averaged +₹65." in page


def test_the_down_page_with_nothing_counted_says_so():
    page = readable(fact_page("down", one_day([-100, 50])))
    assert "No trade you opened had two earlier trades that day already closed." in page
    assert "averaged" not in page


def test_a_long_down_list_sits_behind_the_link_with_book_and_year_filters():
    """18 trades in a row that lose, on each of two days: the first two of a day have nothing
    before them, so 16 a day follow two straight losses. 32 in all, past the 30 a page draws."""
    def losing_day(day, symbol):
        start = datetime.fromisoformat(f"{day}T09:15:00+05:30")
        return [
            option((start + timedelta(minutes=10 * i)).strftime("%H:%M"), "CE", -5, day=day, symbol=symbol)
            for i in range(18)
        ]

    trips = [*losing_day("2025-03-03", "WIDGETIDX"), *losing_day("2026-03-03", "WIDGETOIL")]
    page = fact_page("down", trips)
    assert '<article class="trade">' not in page
    assert 'href="/mirror/fact/down/trades"' in page
    ctx = SF.record_context(trips)
    listing = TL.listing("down", ctx, {"year": "2025", "book": "WIDGETIDX options"}, {})
    choices = {f["name"]: [c["value"] for c in f["choices"]] for f in listing["filters"]}
    assert choices["book"] == ["WIDGETIDX options", "WIDGETOIL options"]
    assert choices["year"] == ["2025", "2026"]
    assert (listing["total"], listing["shown"]) == (32, 16)


# ---------- The dial shows findings ----------


def dial_figures(trips) -> dict:
    figs = SF.facts(SF.record_context(trips), IMP)
    return {i["name"]: i["figure"].replace("\xa0", " ") for i in SF.chapter_view(3, figs)["items"]}


def test_the_chapters_dial_says_the_busiest_days_trades_and_date():
    figs = SF.facts(SF.record_context(DAY), IMP)
    item = SF.chapter_view(3, figs)["items"][1]
    assert (item["figure"], item["label"].replace("\xa0", " ")) == (
        "6 trades", "on your\nbusiest day,\n02 Sep 2026")


@pytest.mark.parametrize("opened", [False, True], ids=["gate closed", "gate open"])
def test_the_chapters_dial_says_a_count_after_two_straight_losses_and_no_direction(opened, monkeypatch):
    if opened:
        monkeypatch.setattr(mx, "post_loss_sentence_may_show", lambda trips: True)
    figure = dial_figures(DOWN)["After two straight losses"]
    assert figure == "2 trades"
    assert "₹" not in figure


def test_one_trade_after_two_straight_losses_is_one_trade():
    assert dial_figures(one_day([-1, -2, 3, 4]))["After two straight losses"] == "1 trade"


def test_a_fact_in_a_state_keeps_its_dash_on_the_dial():
    assert dial_figures([]) == {"After two straight losses": "—", "Your busiest day": "—"}


def test_the_card_and_home_keep_their_own_figures():
    """Only the chapter's dial changes: home's slice says the busiest day, and a card's figure
    sits beside the sentence that explains it."""
    figs = SF.facts(SF.record_context(DOWN), IMP)
    assert figs["down"]["figure"] == "4 trades"
    assert SF.home_view(SF.record_context(DOWN), IMP)["items"][2]["label"] == "on your\nbusiest day"
    assert ">4<" in chapter_page(3, DOWN)


# ---------- Where a page goes next ----------


NUMBER_LINE = "Chapter 4: What we read, and the one number only you can give us."


def buttons(html: str) -> list[tuple[str, str]]:
    return [(href, readable(label)) for href, label in
            re.findall(r'<a class="btn[^"]*" href="([^"]+)">(.*?)</a>', html, re.DOTALL)]


def test_the_way_into_chapter_four_uses_its_real_title():
    """TICKET-903: the spine's Next names the chapter it crosses into, from scope_map."""
    assert S.chapter(4).name == "What we read"
    assert S.next_step("busiest")["label"] == f"Next, chapter 4: {S.FACTS['unread'].title}"
    assert "Chapter 4: What we read" not in readable(fact_page("busiest", DAY))


def test_the_down_page_has_one_way_on():
    """TICKET-903: one next step, the spine's, and no jump to chapter 4 beside it."""
    assert S.next_step("down")["label"] == "Next: Your busiest day"
    assert "Chapter 4: What we read" not in readable(fact_page("down", DOWN))


def test_the_busiest_page_has_no_button_of_its_own():
    """TICKET-903: its way on is the spine's Next (test_report_spine)."""
    assert "Chapter 4: What we read" not in readable(fact_page("busiest", DAY))


def test_the_chapter_page_goes_on_to_its_first_page():
    """TICKET-903: a chapter goes on to its own first page, not to chapter 4."""
    assert "Chapter 4: What we read" not in readable(chapter_page(3, DAY))
    assert S.chapter_step(3)["label"] == f"Next: {S.FACTS['down'].title}"


@pytest.mark.parametrize("n", [1, 2, 4])
def test_no_other_chapter_gains_the_button(n):
    assert "/mirror/chapter/4\"" not in re.sub(r'<nav.*?</nav>', "", chapter_page(n, DAY), flags=re.DOTALL)


@pytest.mark.parametrize(
    "page",
    [lambda t: fact_page("busiest", t), lambda t: fact_page("down", t), lambda t: chapter_page(3, t)],
    ids=["busiest", "down", "chapter"],
)
def test_no_page_offers_the_number_on_the_way_to_chapter_four(page):
    """TICKET-903: Limits left the walk. The number is offered on the risk page and in Account,
    not on the way out of chapter 3, with a budget or without one."""
    assert "the one number" not in readable(page([*DAY]))
    declared = [replace(t, risk_unit_source=s.RiskUnitSourceV1.DECLARED_BUDGET) for t in DAY]
    assert "the one number" not in readable(page(declared))


def test_a_fact_in_a_state_still_goes_on():
    """TICKET-903: the way on is scope_map's, so a page in a state has it as surely as any."""
    assert S.next_step("busiest")["href"] == S.fact_href("unread")
    assert S.next_step("down")["href"] == S.fact_href("busiest")


def test_the_opening_card_sentence_is_untouched():
    assert card_of(chapter_page(3, DOWN), 1)[1] == CLOSED
