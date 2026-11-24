"""TICKET-1035: a dial's wedge says its figure against what it should be compared with.

"46 of 100" means nothing to a trader until it says "needs 40". Each wedge's line under its
figure names that reference, worked out in one place, and the first wedge in reading order
whose figure is worse than its own reference is marked with a quiet fill: one per dial at most.

Worked by hand (made-up trades, one ten-minute trade a day):
  30 trades: 12 winners of 300, 18 losers of 200. Average winner 300, average loser 200,
  break even at 200 / (300 + 200) = 40%: "needs 40". Strike 12 of 30 = 40%: "40 of 100", not
  worse than 40, so not marked.
  30 trades: 11 winners of 300, 19 losers of 200. Strike 11 of 30 = 36.7%: "37 of 100";
  break even still 40%: "needs 40". 37 is under 40: the wedge is marked.
  29 trades (11 winners, 18 losers): under 30, so no "needs" at all.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.production.api import formatting
from services.production.api import scope_facts as SF
from services.production.api import scope_geometry as G
from services.production.api.app import create_app
from services.production.mirror import metrics as mx
from tests.helpers.scope_chapters import IMP, TRIPS, trips_from
from tests.unit.api import figure_pages as P

KIT_JS = "docs/design/scope-kit/static/js/scope-geometry.js"
CSS = "services/production/api/static/css/components.css"

EVEN = [300] * 12 + [-200] * 18
UNDER = [300] * 11 + [-200] * 19
TOO_FEW = [300] * 11 + [-200] * 18


def chapter(n: int, trips) -> dict:
    ctx = SF.record_context(trips)
    view = SF.chapter_view(n, SF.facts(ctx, IMP))
    return {i["name"]: i for i in view.get("desktop_items") or view["items"]}


def said(item: dict, phone: bool = False) -> str:
    words = item.get("phone_label", item["label"]) if phone else item["label"]
    return " ".join(words.replace("\xa0", " ").split())


def marked(items) -> list[str]:
    return [i["name"] for i in (items.values() if isinstance(items, dict) else items) if i.get("marked")]


# ---------- the break-even reference: worked by hand ----------

def test_the_break_even_is_worked_by_hand():
    be = mx.break_even(mx.same_day_trips(trips_from(EVEN)))
    assert (be.average_winner, be.average_loser, be.percent) == (Decimal(300), Decimal(200), Decimal(40))


@pytest.mark.parametrize("phone", [False, True])
def test_wins_say_what_they_need(phone):
    math = chapter(2, trips_from(EVEN))["Your wins and losses"]
    assert math["figure"] == "40 of 100"
    assert "break-even 40" in said(math, phone)


def test_under_thirty_trades_no_rate_is_needed():
    for item in chapter(2, trips_from(TOO_FEW)).values():
        assert "needs" not in said(item) and "needs" not in said(item, phone=True)


def test_a_rate_level_with_what_it_needs_is_not_marked():
    assert "Your wins and losses" not in marked(chapter(2, trips_from(EVEN)))


def test_a_rate_under_what_it_needs_is_marked_and_alone():
    got = chapter(2, trips_from(UNDER))
    assert got["Your wins and losses"]["figure"] == "37 of 100"
    assert marked(got) == ["Your wins and losses"]


# ---------- each wedge's reference, on the forty-trade file ----------

CTX = SF.record_context(TRIPS)
ONE, TWO, THREE = chapter(1, TRIPS), chapter(2, TRIPS), chapter(3, TRIPS)


def test_the_worst_days_say_what_the_other_days_came_to():
    worst = CTX["worst_days"]
    days = len({t.trading_day for t in TRIPS})
    other = sum((t.net for t in TRIPS), Decimal(0)) - worst.sum
    words = said(ONE["Your worst trading days"])
    assert formatting.rupees(worst.sum) in words
    assert f"the other {days - len(worst.days)} days {formatting.rupees(other)}" in words


def test_the_best_trade_says_the_worst():
    words = said(ONE["Where the money came from"])
    assert f"worst {formatting.rupees(CTX['worst'][0].net)}" in words


def test_the_losing_run_says_what_it_lost():
    ids = set(CTX["run"].trip_ids)
    lost = sum((t.net for t in TRIPS if t.trip_id in ids), Decimal(0))
    assert formatting.rupees(lost) in said(TWO["Longest losing run"])


def test_the_clock_says_its_hour_against_its_book():
    lead = mx.lead_clock(CTX["clocks"])
    words = said(TWO["The clock"])
    assert formatting.rupees(lead.largest.net) in words
    worse = lead.largest.net < 0 and lead.largest.net < lead.net
    assert ("more than the whole book lost" in words) is worse
    if not worse:
        assert f"the whole book {formatting.rupees(lead.net)}" in words


def test_the_busiest_day_says_the_usual_day():
    words = said(THREE["Your busiest day"])
    assert f"usually {CTX['days'].normal_day}" in words


def test_after_two_losses_says_other_times_only_where_the_file_allows_a_direction():
    figs = SF.facts(CTX, IMP)
    words = said(THREE["After two straight losses"])
    tl = CTX["two_losses"]
    if figs["down"]["post_loss_sentence"]:
        assert formatting.rupees(tl.condition_mean) in words
        assert f"other times {formatting.rupees(tl.comparison_mean)}" in words
    else:
        assert "other times" not in words


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_one_wedge_at_most_is_marked_on_a_chapter(n):
    assert len(marked(chapter(n, TRIPS))) <= 1


# ---------- the hub ----------

def hub_items(trips) -> list[dict]:
    return SF.home_view(SF.record_context(trips), IMP)["items"]


def test_the_hub_wins_wedge_says_what_it_needs():
    """The hub's phone wedge has one line of room (test_hub_answers' fit), so there the mark and
    the chapter's own dial carry it; the desktop hub says it."""
    items = hub_items(trips_from(EVEN))
    assert "break-even 40" in said(items[1])
    assert said(items[1], phone=True) == "made money"


def test_the_hub_busiest_wedge_says_the_usual_day():
    ctx = SF.record_context(TRIPS)
    assert f"usually {ctx['days'].normal_day}" in said(hub_items(TRIPS)[2])


def test_one_wedge_at_most_is_marked_on_the_hub():
    assert len(marked(hub_items(TRIPS))) <= 1
    under = hub_items(trips_from(UNDER))
    assert [i["name"] for i in under if i.get("worse")][:2] == ["Where your results came from", "Your patterns"]
    assert marked(under) == ["Where your results came from"], "the first in reading order, and only it"


# ---------- the fill: the kit and its port draw it alike ----------

def test_a_marked_slice_is_filled_quietly_and_an_unmarked_one_is_not():
    items = [{"name": n, "figure": "5 days", "href": "", "marked": i == 1}
             for i, n in enumerate(("One", "Two", "Three"))]
    d = G.build_dial({"kind": "chapter", "items": items, "centre": {"name": "C"}}, "phone")
    svg = G.render_dial_svg(d)
    rr, s = d["radii"], d["slices"][1]
    fill = G.wedge(d["cx"], d["cy"], s["start"], s["end"], rr["divStart"], rr["inner"])
    assert svg.count('class="scope__marked"') == 1
    assert f'<path class="scope__marked" d="{fill}"/>' in svg
    assert svg.index("scope__marked") < svg.index("scope__bezel"), "under the ticks and the words"


def test_the_kit_draws_the_same_fill():
    js = Path(KIT_JS).read_text(encoding="utf-8")
    assert "marked: it.marked ? wedge(cx, cy, sl.start, sl.end, rr.divStart, rr.inner) : ''" in js
    assert 'if (s.marked) o.push(`<path class="scope__marked" d="${s.marked}"/>`);' in js


def test_the_fill_has_its_class_in_components_css():
    assert re.search(r"^\.scope__marked \{[^}]*fill-opacity", Path(CSS).read_text(encoding="utf-8"), re.MULTILINE)


# ---------- the demo file, as a trader meets it ----------

@pytest.fixture()
def demo():
    app = create_app()
    client = TestClient(app)
    P._sign_up(client, app.state.engine, "visitor")
    P._consent(client)
    client.post("/upload/demo", data={"csrf_token": P._token(client, "/upload")}, follow_redirects=False)
    paths = ("/mirror", "/mirror/chapter/1", "/mirror/chapter/2", "/mirror/chapter/3", "/mirror/chapter/4")
    return {p: client.get(p).text for p in paths}


def test_the_demo_says_its_references_and_marks_one_wedge_at_most(demo):
    for path, html in demo.items():
        for svg in re.findall(r"<svg class=\"scope__svg\".*?</svg>", html, flags=re.DOTALL):
            assert svg.count('class="scope__marked"') <= 1, path
    assert "break-even" in demo["/mirror/chapter/2"]
    assert "the other" in demo["/mirror/chapter/1"]
    assert "usually" in demo["/mirror/chapter/3"]
    assert 'class="scope__marked"' in demo["/mirror/chapter/1"]
