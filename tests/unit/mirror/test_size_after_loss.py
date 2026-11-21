"""TICKET-996: your size after a loss, against your size after a win.

The lots of the next trade after a loss and after a win, the same day, counted from one shared
rule beside B2's. A sentence that says he sizes up after losses is a finding: it shows only if
R2's shuffle, with the groups worked out again on every draw, clears the finding bar. Every
trade here is made up and the expected values are worked by hand in the comments.
"""
from __future__ import annotations

import importlib
import importlib.util
import re
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import numpy as np

from services.production.mirror import metrics as mx
from services.shared.conditions import b2_shuffle
from services.shared.schemas import scope_v1 as s

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def mod(name: str):
    assert importlib.util.find_spec(name), f"no {name}"
    return importlib.import_module(name)


def need(module, name: str):
    """A function the ticket adds, as an assertion rather than an AttributeError."""
    assert hasattr(module, name), f"{module.__name__} has no {name}"
    return getattr(module, name)


def rule():
    return mod("services.shared.conditions.r2_condition")


def shuffle():
    return mod("services.shared.conditions.r2_shuffle")


def at(day: str, hhmm: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=IST)


def trip(tid: str, day: str, opened: str, closed: str, net: str, lots: int = 1,
         segment: str = "OPT") -> mx.Trip:
    entry, leave = at(day, opened), at(day, closed)
    return mx.Trip(
        trip_id=tid, symbol="WIDGET", trading_day=day, entry_ts=entry, exit_ts=leave,
        holding_seconds=int((leave - entry).total_seconds()), net=D(net), lots=lots,
        risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=segment == "OPT",
        lines=(mx.TradeLine("WIDGET", segment, "Buy", lots, None, None, D(net)),),
    )


# Day A, five option trades. Trade 3 opens (09:40) before trade 2 closes (09:50), so trade 2
# is not "before" it: its last resolved trade is trade 1.
#   a1 09:15-09:20  -100  2 lots   first of the day: not in the population
#   a2 09:25-09:50  +200  2 lots   after a1, a loss          -> after a loss, 2 lots
#   a3 09:40-09:45   -50  4 lots   after a1 (a2 still open)  -> after a loss, 4 lots
#   a4 10:00-10:05     0  1 lot    last closed is a2 (09:50) -> after a win,  1 lot
#   a5 10:10-10:15   +80  3 lots   last closed is a4, level  -> neither: a scratch, counted
# Day B:
#   b1 09:15-09:20   +50  1 lot    first of the day
#   b2 09:30-09:40   +30  2 lots, a future: after b1, a win  -> after a win, 2 lots
#   b3 09:45-09:50   -40  shares (EQ): after b2, a win       -> left out, counted
#   b4 10:00-10:10   +10  1 lot    last closed is b3, a loss -> after a loss, 1 lot
# After a loss: a2 2, a3 4, b4 1 -> 3 trades, 7 lots, 2.333 -> 2.3 on average.
# After a win:  a4 1, b2 2       -> 2 trades, 3 lots, 1.5 on average.
DAY_A, DAY_B = "2026-03-02", "2026-03-03"


def fixture() -> list[mx.Trip]:
    return [
        trip("a1", DAY_A, "09:15", "09:20", "-100", 2),
        trip("a2", DAY_A, "09:25", "09:50", "200", 2),
        trip("a3", DAY_A, "09:40", "09:45", "-50", 4),
        trip("a4", DAY_A, "10:00", "10:05", "0", 1),
        trip("a5", DAY_A, "10:10", "10:15", "80", 3),
        trip("b1", DAY_B, "09:15", "09:20", "50", 1),
        trip("b2", DAY_B, "09:30", "09:40", "30", 2, segment="FUT"),
        trip("b3", DAY_B, "09:45", "09:50", "-40", 100, segment="EQ"),
        trip("b4", DAY_B, "10:00", "10:10", "10", 1),
    ]


# ---------- 1. one shared rule, beside B2's ----------

def test_the_rule_reads_the_last_trade_closed_before_this_one_opened_the_same_day():
    trips = fixture()
    in_pop, after_loss, after_win = rule().population_and_condition(mx.b2_observations(trips))
    ids = [t.trip_id for t in trips]
    assert [i for i, p in zip(ids, in_pop, strict=True) if p] == ["a2", "a3", "a4", "a5", "b2", "b3", "b4"]
    assert [i for i, f in zip(ids, after_loss, strict=True) if f] == ["a2", "a3", "b4"]
    assert [i for i, f in zip(ids, after_win, strict=True) if f] == ["a4", "b2", "b3"]


def test_a_scratch_puts_the_next_trade_in_neither_group():
    trips = fixture()
    in_pop, after_loss, after_win = rule().population_and_condition(mx.b2_observations(trips))
    a5 = [t.trip_id for t in trips].index("a5")
    assert in_pop[a5] and not after_loss[a5] and not after_win[a5]


def test_nothing_carries_across_the_day():
    trips = fixture()
    in_pop, _, _ = rule().population_and_condition(mx.b2_observations(trips))
    assert not in_pop[[t.trip_id for t in trips].index("b1")]


# ---------- 2. options and futures at their lots; shares left out and counted ----------

def test_the_averages_and_counts_worked_by_hand():
    got = need(mx, "size_after_loss")(fixture())
    assert [t.trip_id for t in got.after_loss] == ["a2", "a3", "b4"]
    assert [t.trip_id for t in got.after_win] == ["a4", "b2"]  # the future is in, at 2 lots
    assert got.loss_mean == D("2.3") and got.win_mean == D("1.5")
    assert got.scratch == 1  # a5
    assert got.left_out == 1  # b3, shares: a share's "lot" is one share
    assert got.group_of == {"a2": "loss", "a3": "loss", "b4": "loss", "a4": "win", "b2": "win"}


# ---------- 4. the chart: two rows of dots, averages, hatched under 30 ----------

def test_the_chart_draws_a_dot_per_trade_and_hatches_a_thin_row():
    charts = mod("services.production.api.charts")
    c = need(charts, "dot_rows")([([2, 4, 1], D("2.3"), True), ([1, 2] * 20, D("1.5"), False)], 302, 84)
    roles = {p["role"]: p["d"] for p in c["parts"]}
    assert roles["ink"].count("a") == 2 * 3  # three dots after a loss, each two arcs
    assert roles["faint"].count("a") == 2 * 40
    assert "hatch" in roles  # the first row has under 30 trades
    assert roles["stroke"].count("M") == 1  # only the full row's average is drawn


def test_the_chart_is_registered_beside_the_kit_s_and_the_kit_is_untouched():
    from services.production.api import scope_geometry as G
    assert "size" in G.CHARTS
    assert {"worst", "share", "money", "hold", "strike", "run", "clock", "down", "busy", "read",
            "risk", "notold"} <= set(G.CHARTS)


# ---------- 5. a counted fact, unless R2's bar is passed ----------

def _planted(after_loss_lots: int, days: int = 44) -> list[mx.Trip]:
    """Each day: a loss, then a trade, a win, then a trade, a loss, then a trade. The trade after
    each loss takes ``after_loss_lots``; the one after each win takes 1."""
    out = []
    start = datetime(2026, 1, 5, tzinfo=IST)
    for n in range(days):
        day = (start + timedelta(days=n)).date().isoformat()
        seq = [("-60", 1), ("40", after_loss_lots), ("-30", 1), ("70", 1), ("-20", 1), ("15", after_loss_lots)]
        for k, (net, lots) in enumerate(seq):
            o = 9 * 60 + 15 + 12 * k
            out.append(trip(f"p{n:03d}{k}", day, f"{o // 60:02d}:{o % 60:02d}",
                            f"{(o + 5) // 60:02d}:{(o + 5) % 60:02d}", net, lots))
    return out


def test_sizing_up_after_losses_on_his_own_file_is_a_finding():
    trips = _planted(after_loss_lots=3)
    check = need(mx, "size_after_check")(trips)
    assert check.n_condition >= 30 and check.n_comparison >= 30
    assert check.passes, check
    assert need(mx, "size_sentence_may_show")(trips)


def test_with_no_difference_the_claim_stays_hidden():
    trips = _planted(after_loss_lots=1)
    check = need(mx, "size_after_check")(trips)
    assert not check.passes
    assert not need(mx, "size_sentence_may_show")(trips)


def test_under_thirty_in_a_group_there_is_no_test_at_all():
    check = need(mx, "size_after_check")(fixture())
    assert check.level == b2_shuffle.NOT_ENOUGH and not check.passes


def test_the_shuffle_works_the_groups_out_again_on_every_draw():
    """With fixed groups the number of trades after a loss could not move between draws."""
    trips = _planted(after_loss_lots=3)
    obs = mx.b2_observations(trips)
    sized = np.array([t.is_option for t in trips])
    lots = np.array([float(t.lots) for t in trips])
    _null, after_loss_counts = need(shuffle(), "null_draws")(obs, lots, sized, draws=200)
    assert len(set(after_loss_counts.tolist())) > 1


def test_r2_is_run_and_corrected_with_b2_on_one_shuffle():
    assert mx.CHECKS_RUN == ("B2", "R2")
    assert shuffle().CHECK == "R2"


def test_b2_is_unchanged_when_r2_cannot_run():
    rng = np.random.default_rng(7)
    trips = []
    start = datetime(2026, 1, 5, tzinfo=IST)
    for n in range(70):
        day = (start + timedelta(days=n)).date().isoformat()
        for k in range(6):
            o = 9 * 60 + 15 + 12 * k
            net = str(int(rng.integers(-90, 91)))
            trips.append(trip(f"e{n:03d}{k}", day, f"{o // 60:02d}:{o % 60:02d}",
                              f"{(o + 5) // 60:02d}:{(o + 5) % 60:02d}", net, 5, segment="EQ"))
    obs = mx.b2_observations(trips)
    alone = b2_shuffle.shuffle_test(obs)
    together = mx.post_loss_check(trips)
    assert together == alone


# ---------- 3, 6, 7. on the report, through the app ----------

def test_the_fact_sits_in_chapter_three_after_two_straight_losses():
    from services.production.api import scope_map as SM
    keys = [f.key for f in SM.chapter(3).facts]
    assert keys[:2] == ["down", "size"]
    assert SM.FACTS["size"].title == "Your size after a loss"


def test_its_labels_and_its_factor():
    from services.production.api import factor_map, findings, trade_list
    assert findings.of("size")
    factor = next(f for f in factor_map.FACTORS if "R2" in f.checks)
    assert "size" in factor.facts and "after" in factor.filters
    assert "size" in trade_list.FACTS_WITH_TRADES
    assert any(f.name == "after" for f in trade_list.FILTERS)


def test_the_after_filter_narrows_the_size_list():
    """The after filter is shared with 1006's facts: only `only` differs. Unoffered, a filter fails
    nothing, so this opens size's own list by loss and by win: the two make the whole list."""
    from services.production.api import scope_facts as SF
    from services.production.api import trade_list as TL
    ctx = SF.record_context(_planted(after_loss_lots=2, days=2))

    def shown(**query):
        return TL.listing("size", ctx, query, {})["shown"]

    assert 0 < shown(after="loss") < shown() and 0 < shown(after="win") < shown()
    assert shown(after="loss") + shown(after="win") == shown()


def test_the_page_states_the_counted_line_and_no_claim(client):
    page = client.get("/mirror/fact/size")
    assert page.status_code == 200
    html = page.text
    assert "Your size after a loss" in html
    assert "After a loss" in html and "After a win" in html
    main = re.search(r"<main.*?</main>", html, re.DOTALL).group(0)  # the layout's own scripts aside
    assert "<script" not in main
    assert "you size up" not in html.lower()
    chapter = client.get("/mirror/chapter/3").text
    assert "Your size after a loss" in chapter


def test_a_row_opens_its_trades(client):
    listing = client.get("/mirror/fact/size/trades")
    assert listing.status_code == 200
    every = len(re.findall(r'<article class="trade">', listing.text))
    for side in ("loss", "win"):
        page = client.get(f"/mirror/fact/size/trades?after={side}")
        if page.status_code == 200 and f'value="{side}"' in page.text:
            assert len(re.findall(r'<article class="trade">', page.text)) <= every


def test_a_three_figure_count_still_fits_the_desktop_dial():
    """113 trades after a loss on the demo measured -13.8 on desktop, past the dial's -13; the
    dial test's own fixture has 27, so it couldn't see it. Here 132 follow a loss."""
    from services.production.api import scope_facts as SF
    from services.production.api import scope_geometry as G
    from tests.helpers.scope_chapters import IMP
    trips = _planted(after_loss_lots=3)
    figs = SF.facts(SF.record_context(trips), IMP)
    view = SF.chapter_view(3, figs)
    # Size is on the desktop dial only (on_phone_dial=False); the phone dial is main's.
    desktop, phone = view["desktop_items"], view["items"]
    size = next(i for i in desktop if i["name"] == "Your size after a loss")
    assert size["figure"] == "132" and "trades" in size["label"]
    assert all(i["name"] != "Your size after a loss" for i in phone)
    for which in ("desktop", "phone"):
        z = G.SIZES[which]
        rr = G.radii(z["R"])
        drawn = desktop if which == "desktop" else [
            {**i, "figure": i.get("phone_figure", i["figure"]),
             "label": i.get("phone_label", i.get("label", ""))} for i in phone]
        sec = G.sectors(len(drawn), False)
        lay = G.layout_contents(drawn, sec, rr, z["figSizesChapter"])
        for k, block in enumerate(lay["blocks"]):
            clear = G.block_clearance(sec["slices"][k], sec["span"], lay["radius"][k], block, rr)
            assert clear >= -13, (which, drawn[k]["name"], clear)
