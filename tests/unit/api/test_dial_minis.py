"""TICKET-1036: a dial's mini chart is one a trader can read.

At 36 x 14 the worst-days mini was a hairline, the losing run blank and the clock a dash. Each
fact on a dial now draws one of a few straight forms at 72 x 20 or more, from the figures its own
page is built from, and says those figures aloud. A fact none of them fits draws nothing.
All of it on the made-up 40-trip fixture and the demo file.
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.production.api import dial as D
from services.production.api import formatting
from services.production.api import scope_geometry as G
from services.production.api.app import create_app
from tests.helpers.scope_chapters import CTX, FIGS, IMP, TRIPS
from tests.unit.api import figure_pages as P

KIT_CSS = Path("docs/design/scope-kit/static/css/components.css")
KIT_JS = Path("docs/design/scope-kit/static/js/scope-geometry.js")


def test_a_mini_is_at_least_72_by_20():
    assert D.MINI_W >= 72 and D.MINI_H >= 20


def test_the_block_a_wedge_lays_out_leaves_room_for_the_mini():
    block = G.slice_block({"figure": "13 trades", "chart": "run"}, 18, False)
    assert block["rowB"] == G.MINI["h"] and block["w"] >= G.MINI["w"]
    assert (G.MINI["w"], G.MINI["h"]) == (D.MINI_W, D.MINI_H)


@pytest.mark.parametrize("form", ["meter", "split", "pair", "steps", "counts", "hours"])
def test_the_kit_and_the_port_both_have_each_form(form):
    assert form in G.CHARTS
    assert f"    {form}(" in KIT_JS.read_text()


# ---------- Each fact's form, from its own figures ----------


def test_wins_and_losses_is_a_meter_with_the_break_even_tick():
    st, be = CTX["strike"], CTX["break_even"]
    assert FIGS["math"]["mini"] == G.chart_meter(
        float(st.rate_percent) / 100, float(be.percent) / 100, D.MINI_W, D.MINI_H
    )


def test_worst_days_is_the_five_days_against_the_others():
    sh = CTX["share"]
    assert FIGS["worst-days"]["mini"] == G.chart_split(
        float(sh.five_day_sum), float(sh.other_days_net), D.MINI_W, D.MINI_H
    )


def test_money_is_the_best_trade_against_the_worst():
    assert FIGS["money"]["mini"] == G.chart_pair(
        float(CTX["best"][0].net), float(CTX["worst"][0].net), D.MINI_W, D.MINI_H
    )


def test_after_two_losses_is_the_two_averages_from_one_zero_line():
    tl = CTX["two_losses"]
    assert FIGS["down"]["mini"] == G.chart_pair(
        float(tl.condition_mean), float(tl.comparison_mean), D.MINI_W, D.MINI_H
    )


def test_the_run_steps_down_one_loss_at_a_time():
    ids = set(CTX["run"].trip_ids)
    nets = [float(t.net) for t in TRIPS if t.trip_id in ids]
    assert len(nets) == CTX["run"].length
    assert FIGS["run"]["mini"] == G.chart_steps(nets, D.MINI_W, D.MINI_H)


def test_busiest_day_is_two_counts_with_their_numbers():
    days = CTX["days"]
    mini = FIGS["busiest"]["mini"]
    assert mini == G.chart_counts(days.busiest_trips, float(days.normal_day), D.MINI_W, D.MINI_H)
    assert [lb["t"] for lb in mini["labels"]] == [
        formatting.count(days.busiest_trips), formatting.count(days.normal_day)
    ]


def test_the_clock_marks_the_hour_its_figure_names():
    from services.production.mirror import metrics as mx

    lead = mx.lead_clock(CTX["clocks"])
    mark = [h.hour for h in lead.hours].index(lead.largest.hour)
    assert FIGS["clock"]["mini"] == G.chart_hours(
        [float(h.net) for h in lead.hours], mark, D.MINI_W, D.MINI_H
    )


@pytest.mark.parametrize("key", ["risk", "not-told"])
def test_a_fact_no_form_fits_draws_no_mini(key):
    assert FIGS[key]["mini"] is None


# ---------- The forms ----------


def test_the_meter_fills_to_the_rate_and_ticks_the_target():
    m = G.chart_meter(0.46, 0.51, 72, 20)
    roles = {p["role"] for p in m["parts"]}
    assert roles == {"faint", "ink", "stroke"}
    assert G.chart_meter(0.46, None, 72, 20)["parts"][-1]["role"] != "stroke"


def test_a_pair_draws_a_gain_up_and_a_loss_down_from_one_line():
    m = G.chart_pair(1500.0, -2000.0, 72, 20)
    roles = [p["role"] for p in m["parts"]]
    assert "green" in roles and "red" in roles and "axis" in roles


def test_the_hours_dim_every_hour_but_the_one_marked():
    m = G.chart_hours([100.0, -500.0, 40.0], 1, 72, 20)
    roles = {p["role"]: p["d"] for p in m["parts"]}
    assert roles["red"].count("M") == 1  # the marked hour alone in full
    assert roles["faint"].count("M") == 2


def test_a_chart_with_labels_draws_them_as_text():
    svg = G.render_chart(G.chart_counts(9, 4.0, 72, 20))
    assert '<text class="chart__label"' in svg and ">9</text>" in svg and ">4</text>" in svg


def test_the_label_class_is_the_kits():
    assert ".chart__label" in KIT_CSS.read_text()


# ---------- Read aloud, on the demo file ----------


@pytest.fixture()
def chapters():
    app = create_app()
    client = TestClient(app)
    P._sign_up(client, app.state.engine, "visitor")
    P._consent(client)
    client.post("/upload/demo", data={"csrf_token": P._token(client, "/upload")},
                follow_redirects=False)
    return [client.get(f"/mirror/chapter/{n}").text for n in (1, 2, 3, 4)]


def wedges(html: str) -> list[tuple[str, bool]]:
    """Each wedge's spoken name and whether it draws a mini."""
    out = []
    for block in re.findall(r'<a class="scope__slice.*?</a>', html, flags=re.DOTALL):
        label = unescape(re.search(r'aria-label="([^"]*)"', block).group(1))
        out.append((label, "scope__mini" in block))
    return out


def test_every_wedge_with_a_mini_says_its_two_figures(chapters):
    said = [(label, mini) for html in chapters for label, mini in wedges(html)]
    with_mini = [label for label, mini in said if mini]
    assert len(with_mini) >= 6
    for label in with_mini:
        assert len(re.findall(r"\d", label)) >= 2, label
        assert label.count(".") >= 2, label  # the name, then what the chart shows
