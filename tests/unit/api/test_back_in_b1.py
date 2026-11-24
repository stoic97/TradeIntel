"""TICKET-1006, the founder's ruling of 24 Nov 2026: "back in" is built to match the registered
B1 row (post_loss_latency) exactly.

* Condition: the trade before it lost. Comparison: the trade before it won or finished level.
  Outcome: the minutes from that trade's exit to this one's entry.
* At least 30 trades in each group. Below that the page says how many there are and "too few",
  and draws no comparison: no medians, no chart.
* The sentence names exactly these two groups.

Every trade here is made up; each expected figure is worked by hand in the comments, from the
ruling's words, not from the program's output.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from services.production.api import scope_facts as SF
from services.production.api import trade_list as TL
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.scope_chapters import IMP

D = Decimal
IST = ZoneInfo("Asia/Kolkata")


# The same made-up trades as test_what_you_do_next's PAIRS, written out here: a test file does
# not import another test file.
def leg(kind: str | None, side: str, net) -> mx.TradeLine:
    seg = "OPT" if kind else "FUT"
    return mx.TradeLine("NIFTY", seg, side, 1, None, None, D(str(net)),
                        strike=D("24000") if kind else None, option_type=kind)


def trip(tid, day, opened, closed, net, *legs, lots=1):
    entry = datetime.fromisoformat(f"{day}T{opened}:00").replace(tzinfo=IST)
    leave = datetime.fromisoformat(f"{day}T{closed}:00").replace(tzinfo=IST)
    lines = legs or (leg("CE", "Buy", net),)
    return mx.Trip(trip_id=tid, symbol="NIFTY", trading_day=day, entry_ts=entry, exit_ts=leave,
                   holding_seconds=int((leave - entry).total_seconds()), net=D(str(net)), lots=lots,
                   risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True, lines=lines)


PAIRS = [
    trip("a1", "2026-03-02", "09:15", "09:30", -100),
    trip("a2", "2026-03-02", "09:34", "09:50", 200),
    trip("a3", "2026-03-02", "10:01", "10:20", 0, leg("PE", "Buy", 0)),
    trip("a4", "2026-03-02", "10:25", "10:40", -50, leg("PE", "Buy", -50)),
    trip("a5", "2026-03-02", "10:35", "10:45", 30),
    trip("a6", "2026-03-02", "10:50", "11:00", -20, leg("CE", "Buy", -60), leg("CE", "Sell", 40)),
    trip("b1", "2026-03-03", "09:20", "09:40", -300, leg("PE", "Sell", -300)),
    trip("b2", "2026-03-03", "09:46", "10:00", 100, leg("CE", "Sell", 100)),
]


def facts_of(record):
    return SF.facts(SF.record_context(record), IMP)


def words(markup) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", str(markup)).split()).replace(" ,", ",").replace(" .", ".").replace(" ;", ";")


# ---------- the level trade lands in the comparison group (PAIRS) ----------
# a3 finished level (0) and closed at 10:20. a4 opened 10:25 and a5 10:35, each with a3 as the
# last trade closed before it opened, so both come after a level trade: 5 and 15 minutes.
# After a loss:                a2 (4), b2 (6)                         -> 2 trades, median 5
# After a win or a level trade: a3 (11), a6 (5), a4 (5), a5 (15)       -> 4 trades, median 8
#   sorted 5, 5, 11, 15: the middle two are 5 and 11, so the median is 8.


def test_a_trade_after_a_level_trade_is_in_the_comparison_group():
    nt = SF.record_context(PAIRS)["next_trades"]
    assert sorted(t.trip_id for t in nt.after_loss) == ["a2", "b2"]
    assert sorted(t.trip_id for t in nt.comparison) == ["a3", "a4", "a5", "a6"]
    assert nt.comparison_median == D(8)
    assert nt.back_in_group_of == {"a2": "loss", "b2": "loss", "a3": "win-or-level",
                                   "a4": "win-or-level", "a5": "win-or-level", "a6": "win-or-level"}


def test_the_back_in_list_holds_both_groups_and_each_opens():
    ctx = SF.record_context(PAIRS)
    every = TL.listing("back-in", ctx, {}, {})["shown"]
    after_loss = TL.listing("back-in", ctx, {"after": "loss"}, {})["shown"]
    comparison = TL.listing("back-in", ctx, {"after": "win-or-level"}, {})["shown"]
    assert (every, after_loss, comparison) == (6, 2, 4)


def test_under_thirty_a_group_the_page_says_too_few_and_compares_nothing():
    f = facts_of(PAIRS)["back-in"]
    assert words(f["line"]) == (
        "2 trades came next after a loss and 4 after a win or a level trade: too few to set "
        "side by side. Each needs 30.")
    assert [g["label"] for g in f["groups"]] == ["After a loss", "After a win or a level trade"]
    assert [g["trades"] for g in f["groups"]] == [2, 4]
    assert all(g["median"] is None for g in f["groups"])
    assert not f.get("page_chart")


# ---------- 29 against 30, and 30 against 30 ----------
# One pair a day, each on its own day, so each next trade has exactly one trade before it:
#   the trade before 09:15-09:30, the next one opening a set number of minutes after 09:30.
# After a loss: 30 days, each 10 minutes later              -> 30 trades, median 10
# After a win:  20 days, each 20 minutes later
# After level:  10 days (or 9), each 30 minutes later
#   30 in the comparison group: twenty 20s then ten 30s; the 15th and 16th are both 20 -> 20.
#   29 in the comparison group: one level day fewer -> too few, nothing compared.


def paired(n_loss: int, n_win: int, n_level: int) -> list:
    out, day = [], date(2026, 1, 5)
    for prior_net, gap, n in ((-100, 10, n_loss), (100, 20, n_win), (0, 30, n_level)):
        for _ in range(n):
            iso = day.isoformat()
            opens = f"09:{30 + gap:02d}" if 30 + gap < 60 else f"10:{30 + gap - 60:02d}"
            closes = f"10:{30 + gap - 60 + 5:02d}" if 30 + gap >= 60 else f"09:{30 + gap + 5:02d}"
            out += [trip(f"p{iso}", iso, "09:15", "09:30", prior_net),
                    trip(f"n{iso}", iso, opens, closes, 50)]
            day += timedelta(days=1)
    return out


def test_twenty_nine_in_one_group_is_too_few():
    f = facts_of(paired(30, 20, 9))["back-in"]
    assert words(f["line"]) == (
        "30 trades came next after a loss and 29 after a win or a level trade: too few to set "
        "side by side. Each needs 30.")
    assert all(g["median"] is None for g in f["groups"])
    assert not f.get("page_chart")


def test_thirty_in_each_group_sets_them_side_by_side():
    record = paired(30, 20, 10)
    nt = SF.record_context(record)["next_trades"]
    assert (len(nt.after_loss), len(nt.comparison)) == (30, 30)
    assert (nt.loss_median, nt.comparison_median) == (D(10), D(20))
    f = facts_of(record)["back-in"]
    assert words(f["line"]) == (
        "After a loss your next trade came a median 10 minutes later; after a win or a level "
        "trade, 20.")
    assert [(g["trades"], g["median"]) for g in f["groups"]] == [(30, 10), (30, 20)]
    assert f.get("page_chart")


def test_same_way_again_still_reads_loss_and_win_and_its_list_is_whole():
    # Carried from test_what_you_do_next's after-filter test, whose back-in half the ruling
    # superseded: Same way again is not changed by it, and keeps the after filter's loss and win.
    ctx = SF.record_context(PAIRS)
    every = TL.listing("same-way", ctx, {}, {})["shown"]
    by_loss = TL.listing("same-way", ctx, {"after": "loss"}, {})["shown"]
    by_win = TL.listing("same-way", ctx, {"after": "win"}, {})["shown"]
    assert every == 3  # a6 has no single direction
    assert 0 < by_loss < 3 and 0 < by_win < 3 and by_loss + by_win == 3
