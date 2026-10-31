"""The twelve fact pages: the path, the Mirror's sentences, and every trade behind each.

Rendered through the app's templates with the Mirror's 40-trade fixture. Handoff 11:
each fact page lists every trade behind it, and the count matches the fact.
"""

from __future__ import annotations

import re

import pytest

from services.production.api import formatting
from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from services.shared.schemas import scope_v1 as s
from tests.unit.api.templating import template_env
from tests.unit.api.test_scope_chapters import IMP, TRIPS, readable, trips_from

UNREAD = {"excluded": [(3, "A header row repeated mid-file")], "rejected": [], "refused": []}


def fact_page(key: str, trips=TRIPS, imp=IMP, unread=UNREAD) -> str:
    """What routes_mirror.scope_fact renders, without the app."""
    ctx = SF.record_context(trips)
    figs = SF.facts(ctx, imp)
    chapter, index = S.chapter_of(key)
    return (
        template_env()
        .get_template(f"scope/facts/{key}.html")
        .render(
            title=S.FACTS[key].title,
            body_class="screen__body--fact",
            chapter=chapter,
            index=index,
            number=index + 1,
            fact=S.FACTS[key],
            back_href=S.chapter_href(chapter.number, fact=index + 1),
            f=figs[key],
            facts=figs,
            groups=S.groups(key, ctx),
            imp=imp,
            trading_day_count=len(ctx["days"].counts),
            sources=s.RiskUnitSourceV1,
            **(unread if key == "unread" else {}),
            **ctx,
        )
    )


CTX = SF.record_context(TRIPS)
TRADE_FACTS = [k for k in S.FACTS if k not in ("unread", "not-told")]


@pytest.mark.parametrize("key", list(S.FACTS))
def test_every_fact_page_renders_with_nothing_unwritten(key):
    page = fact_page(key)
    for leak in ("None", "{{", "{%", "[N]", "[X]"):
        assert leak not in page, leak


@pytest.mark.parametrize("key", list(S.FACTS))
def test_a_fact_page_has_its_path_and_no_bottom_nav(key):
    page = fact_page(key)
    chapter, index = S.chapter_of(key)
    assert '<nav class="path" aria-label="Scope path">' in page
    assert f'<span class="path__current" aria-current="page">{S.FACTS[key].title}</span>' in page
    back = S.chapter_href(chapter.number, fact=index + 1).replace("&", "&amp;")
    assert page.count(f'href="{back}"') == 2  # the lens and the chapter in the path
    assert '<nav class="bottom-nav"' not in page  # handoff 5: fact pages have no bottom nav
    assert '<main class="screen__body screen__body--fact">' in page
    assert (f"CHAPTER {chapter.number} · FACT {index + 1} OF {len(chapter.facts)}") in page


@pytest.mark.parametrize("key", TRADE_FACTS)
def test_every_trade_behind_a_fact_is_listed_and_the_count_matches(key):
    """Handoff 11: every trade, never a sample, and the count on the page is the fact's."""
    page = fact_page(key)
    behind = S.trades_behind(key, CTX)
    assert page.count('<article class="trade">') == len(behind)
    listed = [int(n) for n in re.findall(r'class="trade__label">Trade (\d+) ·', page)]
    assert sorted(listed) == sorted(TRIPS.index(t) + 1 for t in behind)
    caption = re.search(r'<p class="evidence__caption">(.*?)</p>', page, re.DOTALL)[1]
    assert readable(caption).endswith(f"{len(behind)} trades.")


def test_each_fact_says_what_its_trades_are():
    """The Mirror's drawer captions, where the Mirror had a drawer (routes_mirror.DRAWERS)."""
    assert "The five days, and every trade on them." in fact_page("worst-days")
    assert "Your best five and worst five, by result." in fact_page("money")
    assert "How long each trade was open, by how it ended." in fact_page("hold")
    assert "Every trade, by the hour you opened it." in fact_page("clock")
    assert "Every trade opened after two that had already closed at a loss." in fact_page("down")


def test_the_worst_days_table_says_each_day_against_the_normal_day_as_the_mirror_did():
    page = fact_page("worst-days")
    normal = float(CTX["days"].normal_day)
    for d in CTX["worst_days"].days:
        row = f"<td>{formatting.day(d.trading_day)}</td>"
        assert row in page
        assert f"{d.trips / normal:.1f}×" in page


def test_the_strike_rate_page_lists_winners_losers_and_level_apart():
    page = fact_page("strike")
    for title in ("Winners", "Losers"):
        assert f'<span class="trades__day">{title}</span>' in page


def test_what_we_could_not_read_lists_rows_not_trades():
    page = fact_page("unread")
    assert "The rows behind this" in page and "The trades behind this" not in page
    assert "A header row repeated mid-file" in page
    assert "Computed from import 7 by Scope version fixturesha" in page
    assert "Rows we could not read" not in page  # none here, so no empty table


def test_what_we_could_not_read_lists_rejected_rows_and_refused_trades_when_there_are_some():
    page = fact_page(
        "unread",
        unread={
            "excluded": [],
            "rejected": [(9, "No date")],
            "refused": ["A short option is not in v1"],
        },
    )
    assert "Rows we could not read. Kept, not discarded. Each one says why." in page
    assert "No date" in page and "A short option is not in v1" in page


def test_what_we_have_not_told_you_has_no_trades_and_carries_the_lineage():
    page = fact_page("not-told")
    assert "The trades behind this" not in page
    assert "Nothing recommends a change." in page
    assert "Computed from import 7" in page


@pytest.mark.parametrize("key", ["hold", "run"])
def test_a_fact_that_cannot_be_counted_says_so_in_place_of_its_figure(key):
    page = fact_page(key, trips_from([100, 200, 300, 50]))
    assert "result-state--not-enough" in page and "Not enough trades yet" in page
    assert "We tell you what your history can't yet show, instead of guessing." in page
    assert "fact__figure" not in page and '<figure class="figure">' not in page


def test_risk_with_nothing_to_measure_against_is_not_in_the_file():
    page = fact_page("risk", trips_from([100, -50], s.RiskUnitSourceV1.UNAVAILABLE))
    assert "result-state--not-in-file" in page
    assert "We do not estimate what is not in your file." in page


def test_a_share_that_is_not_a_percentage_is_told_as_the_mirror_tells_it():
    trips = trips_from([-100, -50, -20, -10, -5, 900])
    for key in ("worst-days", "share"):
        page = readable(fact_page(key, trips))
        assert "Your result for the whole period was" in page
        assert "% of your result" not in page
