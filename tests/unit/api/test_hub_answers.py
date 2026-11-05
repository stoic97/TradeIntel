"""Scope home answers: each chapter's row and wedge carry its leading sentence [TICKET-846].

Counts move to one foot line. Every value on the hub is the same object the chapter renders, so
the hub can't disagree with the page it opens. All trades here are synthetic.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal

import pytest

from services.production.api import formatting
from services.production.api import scope_facts as SF
from services.production.mirror import metrics as mx
from tests.unit.api.templating import template_env
from tests.unit.api.test_scope_chapters import IMP, chapter_page, readable
from tests.unit.api.test_scope_chapters import TRIPS as FORTY
from tests.unit.api.test_scope_home_verdict import t
from tests.unit.mirror.test_page import NEVER_USED

CTX = SF.record_context(FORTY)
FIGS = SF.facts(CTX, IMP)


def hub(trips=FORTY, imp=IMP, opened=frozenset(), number=None) -> str:
    ctx = SF.record_context(trips)
    return template_env().get_template("scope/home.html").render(
        title="Scope", imp=imp, trade_count=len(trips), trading_day_count=len(ctx["days"].counts),
        **SF.home_context(ctx, imp, opened, number=number),
    )


def rows(html: str) -> dict[str, str]:
    blocks = re.findall(r'<li class="home__chapter.*?</li>', html, flags=re.DOTALL)
    out = {}
    for block in blocks:
        label = re.sub(r"<[^>]+>", "", re.search(r'<span class="label">(.*?)</span>', block).group(1))
        out[label.split(" · ")[1]] = readable(block)
    return out


def wedges(trips=FORTY, opened=frozenset(), number=None) -> list[dict]:
    ctx = SF.record_context(trips)
    return SF.home_view(ctx, IMP, opened=opened, number=number)["items"]


def days_from(start: date, n: int) -> list[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range(n)]


def busy_file(per_worst_day: int, normal_days: int = 40):
    """Forty quiet days of one small trade, then five worst days of many small losses."""
    trips = [t(d, 10) for d in days_from(date(2026, 1, 1), normal_days)]
    for d in days_from(date(2026, 3, 1), 5):
        for k in range(per_worst_day):
            trips.append(t(d, -100, at=f"{9 + k // 6:02d}:{(k % 6) * 10:02d}"))
    return trips


# ---------- Row 1: where your results came from ----------


def test_row_one_says_the_share_of_losses_with_its_denominators():
    share = CTX["share"]
    row = rows(hub())["Where your results came from"]
    want = (f"Five of your {share.trading_day_count} trading days carried {share.share_percent}% of your "
            f"losses — {formatting.rupees(CTX['worst_days'].sum, signed=False)}.")
    assert want in row


def test_row_one_says_how_much_busier_when_every_day_was_at_least_twice_normal():
    row = rows(hub(busy_file(3)))["Where your results came from"]
    assert "On each of them you traded at least 3× your normal day." in row


def test_row_one_rounds_the_multiple_down():
    trips = busy_file(3)
    trips += [t(d, 10, at="11:00") for d in days_from(date(2026, 1, 1), 15)]  # normal stays 1
    assert "at least 3×" in rows(hub(trips))["Where your results came from"]


def test_row_one_drops_the_clause_when_a_day_was_under_twice_normal():
    assert "your normal day" not in rows(hub(busy_file(1)))["Where your results came from"]


def test_row_one_with_too_few_days_says_so():
    assert "Not enough trades yet." in rows(hub([t("2026-01-02", -100)]))["Where your results came from"]


def test_row_one_when_the_share_is_not_a_percentage_says_the_sum():
    trips = [t(d, 100) for d in days_from(date(2026, 1, 1), 10)]
    assert not SF.record_context(trips)["share"].shown_as_percentage
    assert "carried" not in rows(hub(trips))["Where your results came from"]


# ---------- Row 2: your patterns ----------


def test_row_two_says_the_strike_rate_and_break_even():
    row = rows(hub())["Your patterns"]
    assert f"Strike rate on same-day trades: {CTX['strike'].rate_percent}%." in row
    assert f"Break-even at your average winner and loser: {CTX['break_even'].percent}%." in row


def test_row_two_doesnt_use_hold_times_or_the_word_won():
    row = rows(hub())["Your patterns"].lower()
    assert "median" not in row
    assert " won" not in row


def test_row_two_under_thirty_same_day_trades_says_not_enough():
    trips = [t(d, 10 if i % 2 else -10) for i, d in enumerate(days_from(date(2026, 1, 1), 29))]
    assert "Not enough trades yet." in rows(hub(trips))["Your patterns"]
    assert wedges(trips)[1]["state"] == "not-enough"


def test_row_two_is_never_hidden():
    assert "Your patterns" in rows(hub([t("2026-01-02", -100)]))


# ---------- Row 3: your behaviour ----------


def test_row_three_says_the_busiest_day():
    story = FIGS["busiest"]["story"]
    row = rows(hub())["Your behaviour"]
    assert f"Your busiest day: {story['trades']} trades on {story['day']}, {formatting.rupees(story['net'])}." in row


def test_row_three_counts_the_trades_that_actually_followed_two_losses():
    """The condition, not the population: the population needn't have followed any loss."""
    tl = CTX["two_losses"]
    assert tl.population != tl.condition
    assert f"After two straight losses you opened {tl.condition} trades." in rows(hub())["Your behaviour"]


def test_row_three_becomes_the_comparison_only_when_the_test_passes(monkeypatch):
    monkeypatch.setattr(mx, "post_loss_sentence_may_show", lambda trips: True)
    row = rows(hub())["Your behaviour"]
    assert "After two straight losses, your next trades averaged" in row
    assert "Your busiest day" not in row


def test_row_three_stays_the_busiest_day_when_it_doesnt(monkeypatch):
    monkeypatch.setattr(mx, "post_loss_sentence_may_show", lambda trips: False)
    row = rows(hub())["Your behaviour"]
    assert "your next trades averaged" not in row
    assert "Your busiest day" in row


# ---------- Row 4: what we read ----------


def test_row_four_with_no_budget_says_there_is_no_risk_figure_yet():
    assert "No budget is set, so there is no risk figure yet." in rows(hub())["What we read"]


def test_row_four_names_the_sold_options_with_no_cap():
    trips = [mx.replace(x, uncapped=True) if i < 2 else x for i, x in enumerate(FORTY)]
    row = rows(hub(trips))["What we read"]
    assert "2 sold-option trades have no risk cap, and no budget is set, so there is no risk figure yet." in row


def test_row_four_with_one_uncapped_trade_says_it_in_the_singular():
    trips = [mx.replace(x, uncapped=True) if i < 1 else x for i, x in enumerate(FORTY)]
    assert "1 sold-option trade has no risk cap" in rows(hub(trips))["What we read"]


def test_row_four_with_a_number_says_it_and_what_lost_more():
    past = CTX["past_number"]
    row = rows(hub(number=Decimal(500)))["What we read"]
    assert f"Your number is ₹500; {past.count} trades lost more than it." in row


# ---------- The wedges ----------


def test_the_wedges_carry_the_short_form_of_the_four_answers():
    items = wedges()
    share, strike, be = CTX["share"], CTX["strike"], CTX["break_even"]
    assert (items[0]["figure"], items[0]["label"]) == (f"{share.share_percent}%", "of losses · 5 days")
    assert (items[1]["figure"], items[1]["label"]) == (f"{strike.rate_percent}% strike", f"{be.percent}% to break even")
    assert (items[2]["figure"].replace(chr(0xA0), " "), items[2]["label"]) == (
        f"{CTX['days'].busiest_trips} trades", "busiest day")
    assert items[3]["figure"] == "no budget"


def test_a_wedge_says_how_many_are_uncapped():
    trips = [mx.replace(x, uncapped=True) if i < 2 else x for i, x in enumerate(FORTY)]
    assert wedges(trips)[3]["label"] == "2 uncapped"


def test_a_wedge_with_a_number_says_it():
    item = wedges(number=Decimal(500))[3]
    assert item["figure"] == "₹500"
    assert item["label"] == f"{CTX['past_number'].count} past it"


def test_no_wedge_says_open_or_read():
    figures = [i["figure"] for i in wedges(opened=frozenset({1, 3}))]
    assert "Open" not in figures
    assert "Read" not in figures


def test_read_is_the_rim_dot():
    assert [i["opened"] for i in wedges(opened=frozenset({1, 3}))] == [True, False, True, False]


def test_the_centre_stays_the_result():
    centre = SF.home_view(CTX, IMP, gross=True)["centre"]
    assert centre["figure"] == formatting.rupees(CTX["share"].total)
    assert centre["captionLines"] == ["your result,", "before charges"]


# ---------- The foot line ----------


def test_the_counts_are_one_foot_line():
    html = hub()
    foot = readable(re.search(r'<p class="[^"]*home__foot.*?</p>', html, flags=re.DOTALL).group(0))
    assert (f"{IMP.rows_parsed} of {IMP.rows_in} rows read · {len(FORTY)} trades · "
            f"{len(CTX['days'].counts)} trading days · before charges") in foot
    assert "No buy or sell calls, ever." in foot


def test_with_charges_the_foot_line_doesnt_say_before_charges():
    with_fees = type(IMP)(**{**vars(IMP), "fees_available": True})
    foot = re.search(r'<p class="[^"]*home__foot.*?</p>', hub(imp=with_fees), flags=re.DOTALL).group(0)
    assert "before charges" not in readable(foot)


def test_those_counts_are_nowhere_else_on_the_rows():
    text = readable(hub())
    assert "What we read:" not in text
    assert f"{len(FORTY)} trades, " not in text


# ---------- One source, and the register ----------


def test_row_one_agrees_with_chapter_one():
    assert formatting.rupees(CTX["worst_days"].sum, signed=False) in readable(chapter_page(1))
    assert f"{CTX['share'].share_percent}%" in readable(chapter_page(1))


def test_row_two_agrees_with_chapter_two():
    page = readable(chapter_page(2))
    assert f"{CTX['strike'].rate_percent}%" in page
    assert f"{CTX['break_even'].percent}%" in page


def test_row_three_agrees_with_chapter_three():
    page = readable(chapter_page(3))
    assert f"{CTX['days'].busiest_trips} trades" in page
    assert str(CTX["two_losses"].condition) in page


def test_the_hub_says_none_of_the_never_use_words():
    text = readable(hub()).lower()
    for word in NEVER_USED:
        assert not re.search(rf"\b{re.escape(word.lower())}\b", text), word


@pytest.mark.parametrize("word", ["because", "caused", "due to", "leads to", "you should"])
def test_the_hub_names_no_cause(word):
    assert word not in readable(hub()).lower()
