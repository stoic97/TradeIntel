"""The Python dial and charts draw exactly what the design kit's JavaScript draws.

Every case in tests/fixtures/scope_geometry/cases.json was recorded from
docs/design/scope-kit/static/js/scope-geometry.js by record.js in the same folder. A
case that fails here is a pixel the server would draw differently from the kit.
"""

import json
from pathlib import Path

import pytest

from services.production.api import scope_geometry as G

CASES = json.loads(
    (Path(__file__).parents[2] / "fixtures" / "scope_geometry" / "cases.json").read_text()
)
THREE = {"threeLineNames": G.THREE_LINE_NAMES}


@pytest.mark.parametrize(("n", "want"), CASES["fmt"])
def test_fmt_prints_a_number_as_the_kit_does(n, want):
    assert G.fmt(n) == want


@pytest.mark.parametrize(("n", "want"), [(0.5, 1), (-0.5, 0), (2.5, 3), (-2.5, -2), (1.4, 1)])
def test_js_round_sends_a_half_up_like_math_round(n, want):
    assert G.js_round(n) == want


@pytest.mark.parametrize(
    ("n", "want"), [(179.0, "179"), (-0.0, "0"), (0.1 + 0.2, "0.30000000000000004")]
)
def test_js_str_prints_a_number_as_javascript_does(n, want):
    assert G.js_str(n) == want


@pytest.mark.parametrize(("n", "is_home", "want"), CASES["sectors"])
def test_sectors(n, is_home, want):
    assert G.sectors(n, is_home) == want


@pytest.mark.parametrize(("size", "n", "is_home", "rotation", "want"), CASES["ticks"])
def test_ticks(size, n, is_home, rotation, want):
    s = G.SIZES[size]
    sec = G.sectors(n, is_home)
    assert (
        G.ticks(s["stageW"] / 2, s["stageH"] / 2, G.radii(s["R"]), sec["dividers"], rotation)
        == want
    )


@pytest.mark.parametrize(("fig", "want"), CASES["stacked_split"])
def test_stacked_split(fig, want):
    assert G.stacked_split(fig) == want


@pytest.mark.parametrize(("text", "want"), CASES["sans_width"])
def test_sans_width(text, want):
    assert G.sans_width(text, 11) == want


@pytest.mark.parametrize(("size", "mid", "name", "want"), CASES["name_labels"])
def test_name_label(size, mid, name, want):
    s = G.SIZES[size]
    got = G.name_label(name, mid, s["stageW"] / 2, s["stageH"] / 2, G.radii(s["R"]), s, THREE)
    # x and top are raw floats. JavaScript's Math.sin and the C library's sin may differ
    # in the last bit (at 240 degrees they do), so these two are held to a billionth of a
    # pixel; everything that is drawn - the leader path, the lines - is held exactly.
    assert {k: v for k, v in got.items() if k not in {"x", "top"}} == (
        {k: v for k, v in want.items() if k not in {"x", "top"}}
    )
    assert got["x"] == pytest.approx(want["x"], abs=1e-9)
    assert got["top"] == pytest.approx(want["top"], abs=1e-9)


@pytest.mark.parametrize("key", sorted(CASES["dials"]))
def test_dial_lays_out_and_draws_as_the_kit_does(key):
    case = CASES["dials"][key]
    d = G.build_dial(case["view"], case["size"], THREE)
    assert d["figSize"] == case["fig_size"]
    assert [bool(s["contents"]["tail"]) for s in d["slices"]] == case["stacked"]
    assert [[G.fmt(s["contents"]["x"]), G.fmt(s["contents"]["numberY"])] for s in d["slices"]] == (
        case["radii_contents"]
    )
    assert G.render_dial_svg(d) == case["svg"]
    if case["svg_with_minis"] is not None:
        mini = {"worst": '<path d="M0 0"/>', "share": '<path d="M1 1"/>'}
        assert G.render_dial_svg(d, mini) == case["svg_with_minis"]


@pytest.mark.parametrize(("n", "i", "want"), CASES["lenses"])
def test_lens(n, i, want):
    assert G.build_lens(n, i) == want


CHART_IDS = [f"{c['kind']}-{c['w']}x{c['h']}-{j}" for j, c in enumerate(CASES["charts"])]


@pytest.mark.parametrize("case", CASES["charts"], ids=CHART_IDS)
def test_chart(case):
    args = [*case["args"], case["w"], case["h"]]
    if case["kind"] in {"share", "hold", "strike", "run", "down", "read", "risk", "notold"}:
        args.append(case["mini"])
    got = G.CHARTS[case["kind"]](*args)
    assert got == case["out"]
    assert G.render_chart(got, "chart--page", wrap=True) == case["svg"]
    assert G.render_chart(got) == case["inner"]


@pytest.mark.parametrize(("times", "width", "height", "want"), CASES["trade_strips"])
def test_trade_strip(times, width, height, want):
    assert G.trade_strip(times, width, height) == want


def test_every_recorded_dial_view_is_checked():
    # A view added to record.js without a test above would pass silently; this one would not.
    assert len(CASES["dials"]) == 13
    assert len(CASES["charts"]) == 52
