"""The Scope's map (api/scope_map.py): the chapters, the links, the trades behind each fact.

Run on the Mirror's 40-trade contract fixture, through the same _mirror_context the
pages read, so a list here is the list a page will show.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from services.production.api import formatting
from services.production.api import scope_map as S
from services.production.mirror import metrics as mx
from tests.unit.api.templating import template_env

TRIPS = mx.load_trips(json.loads(Path("tests/fixtures/mirror_contract/main.json").read_text()))


def context(trips=TRIPS) -> dict:
    """routes_mirror._mirror_context, without importing the app (no database here)."""
    return {
        "worst_days": mx.five_worst_days(trips),
        "share": mx.share_of_total(trips),
        "days": mx.day_counts(trips),
        "best": mx.best_five(trips),
        "worst": mx.worst_five(trips),
        "two_losses": mx.two_straight_losses(trips),
        "strike": mx.strike_rate(trips),
        "holding": mx.holding_time(trips),
        "hours": mx.result_by_hour(trips),
        "run": mx.longest_losing_run(trips),
        "risk": mx.risk_figure_counts(trips),
        "trips": trips,
    }


CTX = context()


# ---------- The map ----------


def test_the_chapters_and_facts_are_the_handoffs():
    """Handoff section 4: four chapters, twelve facts, in slice order, with their keys."""
    assert [(c.number, c.name, [f.key for f in c.facts]) for c in S.CHAPTERS] == [
        (1, "Where your results came from", ["worst-days", "share", "money"]),
        (2, "Your patterns", ["hold", "strike", "run", "clock"]),
        (3, "Your behaviour", ["down", "busiest"]),
        (4, "What we couldn't read", ["unread", "risk", "not-told"]),
    ]
    assert [c.feedback for c in S.CHAPTERS] == [True, True, True, False]  # 4 is the honest close


def test_every_fact_has_a_chart_the_geometry_draws():
    from services.production.api import scope_geometry as G

    assert {f.chart for f in S.FACTS.values()} == set(G.CHARTS)


def test_every_fact_title_is_a_heading_the_mirror_already_uses():
    """Handoff 6: the Mirror's own headings, word for word."""
    mirror = Path("services/production/api/templates/mirror.html").read_text()
    for f in S.FACTS.values():
        if f.key in ("share", "strike", "run", "busiest"):
            continue  # facts the long page told inside another section's sentences
        assert f.title in mirror, f.key


def test_a_fact_knows_its_chapter_and_place():
    assert S.chapter_of("clock") == (S.CHAPTERS[1], 3)
    with pytest.raises(KeyError):
        S.chapter_of("nope")
    with pytest.raises(KeyError):
        S.chapter(5)


def test_every_old_dwell_key_maps_to_a_fact():
    assert set(S.OLD_DWELL_LINES.values()) <= set(S.FACTS)


# ---------- Links ----------


def test_the_links_carry_the_transition_that_brought_the_page():
    assert S.home_href() == "/mirror"
    assert S.home_href(tap=2) == "/mirror?enter=out&tap=2"
    assert S.chapter_href(2, from_home=True) == "/mirror/chapter/2?enter=in&tap=2"
    assert S.chapter_href(2, fact=3) == "/mirror/chapter/2?enter=back&fact=3"
    assert S.chapter_href(2) == "/mirror/chapter/2"
    assert S.fact_href("run") == "/mirror/fact/run?enter=lens"
    assert S.fact_href("run", lens=False) == "/mirror/fact/run"


# ---------- The trades behind each fact ----------


@pytest.mark.parametrize("key", list(S.FACTS))
def test_the_trades_behind_a_fact_are_in_the_order_they_were_opened(key):
    shown = S.trades_behind(key, CTX)
    assert shown == sorted(shown, key=lambda t: TRIPS.index(t))


def test_the_worst_days_and_their_share_list_every_trade_on_those_five_days():
    days = {d.trading_day for d in CTX["worst_days"].days}
    shown = S.trades_behind("worst-days", CTX)
    assert {t.trading_day for t in shown} == days
    assert len(shown) == sum(d.trips for d in CTX["worst_days"].days)
    assert S.trades_behind("share", CTX) == shown


def test_where_the_money_came_from_is_ten_trades():
    assert len(S.trades_behind("money", CTX)) == 10


def test_trading_on_while_down_lists_the_condition_trades():
    shown = S.trades_behind("down", CTX)
    assert [t.trip_id for t in shown] == CTX["two_losses"].condition_trip_ids
    assert len(shown) == CTX["two_losses"].condition


def test_the_longest_losing_run_lists_the_run():
    """B3: a new list. Every trade in it lost, and there are run.length of them."""
    shown = S.trades_behind("run", CTX)
    assert len(shown) == CTX["run"].length and all(t.is_loss for t in shown)


def test_the_busiest_day_lists_every_trade_on_it():
    """B3: a new list, as many trades as the busiest day had."""
    shown = S.trades_behind("busiest", CTX)
    assert {t.trading_day for t in shown} == {CTX["days"].busiest_day}
    assert len(shown) == CTX["days"].busiest_trips


@pytest.mark.parametrize("key", ["hold", "strike", "clock", "risk"])
def test_a_fact_about_every_trade_lists_every_trade(key):
    """B3 for strike rate: winners and losers are every trade, so all of them."""
    assert S.trades_behind(key, CTX) == TRIPS


@pytest.mark.parametrize("key", ["unread", "not-told"])
def test_the_close_lists_no_trades(key):
    assert S.trades_behind(key, CTX) == []


# ---------- Groups ----------


@pytest.mark.parametrize("key", [k for k in S.FACTS if k not in ("unread", "not-told")])
def test_the_groups_hold_every_trade_behind_the_fact_once(key):
    listed = [t["number"] for g in S.groups(key, CTX) for t in g["trades"]]
    assert sorted(listed) == sorted(TRIPS.index(t) + 1 for t in S.trades_behind(key, CTX))
    for g in S.groups(key, CTX):
        assert g["trade_count"] == len(g["trades"])
        assert g["net"] == sum(t["net"] for t in g["trades"])


def test_most_facts_group_by_trading_day():
    titles = [g["title"] for g in S.groups("worst-days", CTX)]
    days = sorted(d.trading_day for d in CTX["worst_days"].days)
    assert titles == [f"Day {i} · {formatting.day(d)}" for i, d in enumerate(days, start=1)]


def test_the_outcome_facts_group_by_how_a_trade_ended():
    got = {g["title"]: g["trade_count"] for g in S.groups("strike", CTX)}
    assert got == {
        k: v
        for k, v in {
            "Winners": CTX["strike"].wins,
            "Losers": CTX["strike"].losses,
            "Finished level": CTX["strike"].scratches,
        }.items()
        if v
    }


def test_the_clock_groups_by_the_hour_opened():
    got = [(g["title"], g["trade_count"]) for g in S.groups("clock", CTX)]
    assert got == [(f"{h.hour:02d}:00", h.trips) for h in CTX["hours"]]


def test_risk_groups_by_what_a_trade_was_measured_against():
    got = Counter({g["title"]: g["trade_count"] for g in S.groups("risk", CTX)})
    assert sum(got.values()) == len(TRIPS)
    assert set(got) <= {title for title, _ in S.RISK_SOURCES}


def test_a_trade_is_drawn_from_its_entry_to_its_exit():
    t = TRIPS[0]  # 09:30 to 10:00 on 01 Sep
    got = S.trade(t, 1)
    assert (got["day"], got["time_in"], got["time_out"], got["held_minutes"]) == (
        "01 Sep",
        "09:30",
        "10:00",
        30,
    )
    assert got["fill_minutes"] == [0, 30] and got["fills"] == []


def test_a_trade_without_fills_has_no_fills_table():
    env = template_env({"p.html": '{% from "_components.html" import trades %}{{ trades(g) }}'})
    html = env.get_template("p.html").render(g=S.groups("money", CTX))
    assert html.count('<article class="trade">') == 10
    assert "fills" not in html


def test_a_day_is_written_as_the_kit_writes_it():
    assert formatting.day("2026-09-07") == "07 Sep"
    assert formatting.day("2026-12-31") == "31 Dec"
