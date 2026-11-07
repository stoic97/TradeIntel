"""Chapter 3 counts same-day trades only, as Chapter 2 does [TICKET-855].

Worked by hand. The history of test_not_down_row: 8 same-day trades over two days, of which
4 were not down, -240 net, -60 each. Added to it here:

    a position opened on day one after two straight losses, held for two days, +5000
    eight positions opened on day three, each held for two days

Counted as trades, the first would land "after two straight losses" and the eight would be
"not down", and day three would be the busiest day with 8 trades. None of them was closed
the day it opened, so none of them may move a Chapter 3 figure: not down stays 4 trades and
-240, and the busiest day stays day one with its 6 trades.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from services.production.mirror import metrics as mx
from tests.unit.api.test_chapter_three_describes import DOWN, one_day
from tests.unit.api.test_scope_chapters import IMP, chapter_page
from tests.unit.api.test_scope_facts import fact_page


def held(net: int, day: str, at: str) -> mx.Trip:
    entry = datetime.fromisoformat(f"{day}T{at}:00+05:30")
    return replace(one_day([net], day)[0], trip_id=f"held-{day}-{at}", entry_ts=entry,
                   exit_ts=entry + timedelta(days=2), holding_seconds=172800,
                   net=Decimal(net))


SAME_DAY = DOWN + one_day([40, 20], "2026-09-02")
HELD = [held(5000, "2026-09-01", "09:50"),
        *[held(100 + i, "2026-09-03", f"10:{i:02d}") for i in range(8)]]
FILE = sorted(SAME_DAY + HELD, key=lambda t: t.entry_ts)


def test_the_not_down_row_counts_same_day_trades_only():
    tl = SF.record_context(FILE)["two_losses"]
    assert (tl.outside, tl.outside_net, tl.outside_mean) == (4, Decimal(-240), Decimal(-60))


def test_held_positions_move_nothing_in_table_one():
    assert SF.record_context(FILE)["two_losses"] == SF.record_context(SAME_DAY)["two_losses"]


def test_held_positions_move_nothing_in_table_two():
    with_held, without = SF.record_context(FILE), SF.record_context(SAME_DAY)
    for key in ("after_strike", "after_lots", "rest_strike", "rest_lots",
                "days_with_the_condition"):
        assert with_held[key] == without[key], key


def test_chapter_two_and_chapter_three_describe_the_same_trades():
    ctx = SF.record_context(FILE)
    tl, strike = ctx["two_losses"], ctx["strike"]
    assert tl.population + tl.outside == len(mx.same_day_trips(FILE))
    assert tl.population + tl.outside == strike.wins + strike.losses + strike.scratches


def test_the_sentence_gate_is_asked_about_same_day_trades_only(monkeypatch):
    asked = []
    monkeypatch.setattr(mx, "post_loss_sentence_may_show",
                        lambda trips: asked.append(trips) or False)
    SF.facts(SF.record_context(FILE), IMP)
    assert asked, "the gate was not asked"
    assert all(t.closed_same_day for trips in asked for t in trips)


def test_held_positions_do_not_make_a_day_the_busiest():
    days = SF.record_context(FILE)["days"]
    assert (days.busiest_day, days.busiest_trips) == ("2026-09-01", 6)


def test_the_trades_behind_the_busiest_day_are_same_day():
    behind = S.trades_behind("busiest", SF.record_context(FILE))
    assert [t.trip_id for t in behind] == [t.trip_id for t in DOWN]


def test_chapter_three_renders_the_same_with_or_without_held_positions():
    assert chapter_page(3, FILE) == chapter_page(3, SAME_DAY)


def test_the_two_fact_pages_render_the_same_with_or_without_held_positions():
    for key in ("down", "busiest"):
        assert fact_page(key, FILE) == fact_page(key, SAME_DAY), key


def test_the_whole_file_still_counts_every_day_it_has_a_trade_on():
    """The Home footer says how many trades and trading days the file holds, held or not."""
    assert SF.record_context(FILE)["file_trading_days"] == 3
    assert SF.record_context(SAME_DAY)["file_trading_days"] == 2
