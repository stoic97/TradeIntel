"""The count behind "the minute before you bought had already moved your way", and its control.

Every bar here is made up: a seeded random walk, so nothing in this file is anyone's market
data or anyone's trades, and nothing reaches a network.
"""

from __future__ import annotations

import ast
import dataclasses
import socket
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from services.production.mirror import prior_minute as pm

IST = ZoneInfo("Asia/Kolkata")
DAYS = [date(2026, 6, 1) + timedelta(days=i) for i in range(40)]
SESSION = (9 * 60 + 15, 15 * 60 + 30)  # minutes since midnight


def walk(seed: int = 7, days=DAYS) -> pm.BarTable:
    """A market with no memory: each minute's move is independent of the last."""
    rng = np.random.default_rng(seed)
    bars: dict[datetime, pm.Bar] = {}
    price = 20000.0
    for d in days:
        for minute in range(*SESSION):
            start = datetime(d.year, d.month, d.day, minute // 60, minute % 60, tzinfo=IST)
            close = price + float(rng.choice([-2.0, -1.0, 1.0, 2.0]))
            bars[start] = pm.Bar(open=price, close=close)
            price = close
    return pm.BarTable(bars=bars, first_day=days[0], last_day=days[-1])


def chaser(table: pm.BarTable, n: int = 600, seed: int = 11) -> list[pm.Entry]:
    """A trader with no edge who buys in the direction of the minute that just closed."""
    rng = np.random.default_rng(seed)
    hour = timedelta(minutes=max(pm.HORIZONS))
    starts = [t for t in sorted(table.bars)
              if t - timedelta(minutes=1) in table.bars and t + hour in table.bars]
    entries = []
    for k in rng.choice(len(starts), size=n, replace=False):
        minute = starts[int(k)]
        before = table.bars[minute - timedelta(minutes=1)]
        direction = 1 if before.close > before.open else -1
        entries.append(pm.Entry(trip_id=f"t{k}", underlying="NIFTY",
                                entry_ts=minute + timedelta(seconds=int(rng.integers(0, 60))),
                                direction=direction))
    return entries


@pytest.fixture(scope="module")
def table():
    return walk()


@pytest.fixture(scope="module")
def chased(table):
    return pm.count(chaser(table), {"NIFTY": table})


def test_a_trader_who_follows_the_last_minute_reads_all_of_them_agreeing(chased):
    assert chased.before.agreed == chased.before.measured == 600


def test_from_the_close_of_the_entry_minute_he_is_about_a_coin_flip(chased):
    """The build note's own test: anything measured from earlier than the entry minute's close
    would read the chase as skill."""
    for horizon in pm.HORIZONS:
        c = chased.after[horizon]
        assert 0.43 < c.agreed / c.measured < 0.57, horizon


def test_the_before_count_clears_its_control_and_so_may_be_said(chased):
    assert chased.before.above_band
    assert chased.ships


def test_a_count_inside_its_band_does_not_ship(table):
    """A trader who picks a side at random: the minute before agrees about half the time."""
    rng = np.random.default_rng(3)
    entries = [dataclasses.replace(e, direction=int(rng.choice([-1, 1]))) for e in chaser(table)]
    result = pm.count(entries, {"NIFTY": table})
    assert result.before.inside_band
    assert not result.ships


def test_a_trader_who_only_ever_buys_one_way_gets_no_claim(table):
    """Shuffling one direction changes nothing, so the control can't tell him from chance."""
    entries = [dataclasses.replace(e, direction=1) for e in chaser(table)]
    result = pm.count(entries, {"NIFTY": table})
    assert result.before.band == (result.before.agreed, result.before.agreed)
    assert not result.ships


def test_before_reads_only_the_minute_that_closed_before_the_entry_minute(table):
    minute = datetime(2026, 6, 2, 11, 0, tzinfo=IST)
    entry = pm.Entry("x", "NIFTY", minute + timedelta(seconds=40), 1)
    bars = dict(table.bars)
    bars[minute - timedelta(minutes=1)] = pm.Bar(open=100.0, close=101.0)
    first = pm.count([entry], {"NIFTY": dataclasses.replace(table, bars=bars)})
    bars[minute] = pm.Bar(open=101.0, close=50.0)  # the entry minute itself falls hard
    second = pm.count([entry], {"NIFTY": dataclasses.replace(table, bars=bars)})
    assert first.before.agreed == second.before.agreed == 1


def test_after_is_measured_from_the_close_of_the_entry_minute(table):
    minute = datetime(2026, 6, 2, 11, 0, tzinfo=IST)
    bars = dict(table.bars)
    bars[minute] = pm.Bar(open=100.0, close=200.0)
    bars[minute + timedelta(minutes=5)] = pm.Bar(open=150.0, close=150.0)
    result = pm.count([pm.Entry("x", "NIFTY", minute, 1)],
                      {"NIFTY": dataclasses.replace(table, bars=bars)})
    assert (result.after[5].agreed, result.after[5].measured) == (0, 1)  # 200 to 150: against him


def test_a_flat_minute_does_not_agree_with_either_side(table):
    minute = datetime(2026, 6, 2, 11, 0, tzinfo=IST)
    bars = dict(table.bars)
    bars[minute - timedelta(minutes=1)] = pm.Bar(open=100.0, close=100.0)
    series = {"NIFTY": dataclasses.replace(table, bars=bars)}
    for direction in (1, -1):
        result = pm.count([pm.Entry("x", "NIFTY", minute, direction)], series)
        assert (result.before.agreed, result.before.measured) == (0, 1)


def test_no_trip_is_dropped_and_each_one_left_out_says_why(table):
    on_day = datetime(2026, 6, 2, 11, 0, tzinfo=IST)
    entries = [
        pm.Entry("measured", "NIFTY", on_day, 1),
        pm.Entry("no series", "GOLD", on_day, 1),
        pm.Entry("not covered", "NIFTY", datetime(2025, 1, 6, 11, 0, tzinfo=IST), 1),
        pm.Entry("no bar", "NIFTY", datetime(2026, 6, 2, 8, 0, tzinfo=IST), 1),
        pm.Entry("no direction", "NIFTY", on_day, None),
        pm.Entry("no underlying", None, on_day, 1),
    ]
    result = pm.count(entries, {"NIFTY": table})
    assert result.total == 6
    left_out = len(result.unmeasured) + len(result.unmeasured_before)
    assert result.before.measured + left_out == 6
    assert {u.trip_id: u.reason for u in result.unmeasured} == {
        "no series": pm.Reason.NO_SERIES,
        "not covered": pm.Reason.NOT_COVERED,
        "no direction": pm.Reason.NO_DIRECTION,
        "no underlying": pm.Reason.NO_SERIES,
    }
    # No bar at or before 08:00: the before count and every after count each name the bar.
    assert {u.trip_id: u.reason for u in result.unmeasured_before} == {
        "no bar": pm.Reason.NO_PRIOR_BAR,
    }
    for h in pm.HORIZONS:
        assert {u.trip_id: u.reason for u in result.unmeasured_after[h]} == {
            "no bar": pm.Reason.NO_ENTRY_BAR,
        }
        out = len(result.unmeasured) + len(result.unmeasured_after[h])
        assert result.after[h].measured + out == 6
    assert result.unmeasured_by_reason() == {
        pm.Reason.NO_SERIES: 2, pm.Reason.NOT_COVERED: 1, pm.Reason.NO_DIRECTION: 1}


def test_a_horizon_past_the_last_bar_is_counted_out_with_its_reason(table):
    close = datetime(2026, 6, 2, 15, 29, tzinfo=IST)  # the session's last minute
    result = pm.count([pm.Entry("late", "NIFTY", close, 1)], {"NIFTY": table})
    assert result.before.measured == 1
    assert result.after[5].measured == 0
    assert [(u.trip_id, u.reason) for u in result.unmeasured_after[5]] == [
        ("late", pm.Reason.NO_HORIZON_BAR)
    ]


def test_the_same_history_gives_the_same_band_and_the_seed_is_recorded(table):
    entries = chaser(table)
    one, two = pm.count(entries, {"NIFTY": table}), pm.count(entries, {"NIFTY": table})
    assert one.before.band == two.before.band
    assert [one.after[h].band for h in pm.HORIZONS] == [two.after[h].band for h in pm.HORIZONS]
    assert (one.seed, one.draws) == (pm.SEED, pm.DRAWS) == (20261112, 2000)


def test_the_band_is_returned_beside_every_count(chased):
    for c in (chased.before, *chased.after.values()):
        low, high = c.band
        assert 0 <= low <= high <= c.measured


def test_nothing_measured_has_no_band_and_no_claim():
    result = pm.count([], {})
    assert result.before.band is None
    assert result.before.inside_band
    assert not result.ships


def test_it_counts_and_never_prices():
    """No saving, no avoided cost, no rupee effect: the result has nowhere to put one."""
    for cls in (pm.PriorMinute, pm.Count, pm.Unmeasured, pm.Entry):
        for f in dataclasses.fields(cls):
            assert f.type not in (Decimal, "Decimal"), (cls.__name__, f.name)
            assert not any(w in f.name for w in ("rupee", "net", "cost", "saving", "pnl")), f.name


def test_production_imports_nothing_from_research():
    tree = ast.parse(Path(pm.__file__).read_text(encoding="utf-8"))
    names = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    names += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not [n for n in names if n.startswith("services.research")]


def test_it_runs_on_the_demo_file_with_no_network(monkeypatch):
    """Every demo position is counted or counted out. Directions here are a stand-in for the
    option direction rule, for this test only: a bought call is long, a bought put short.
    A share has no option type and no series here, so it is counted out as having none."""
    from services.production.ctr.intake import pipeline as pl

    def refuse(*_a, **_k):
        raise AssertionError("no network")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)

    plan = pl.plan_import(
        Path("data/fixtures/demo/scope_demo_tradebook.csv").read_text(encoding="utf-8"),
        context=pl.ImportContext(trader_id="demo", source_account="DEMO", code_version="test",
                                 export_date="2026-09-01", export_date_source="trader"),
        production=True)
    entries = []
    for p in plan.positions:
        leg = p.legs[0]
        one_way = len(p.legs) == 1 and leg.direction.value == "LONG" and leg.option_type
        direction = (1 if leg.option_type.value == "CE" else -1) if one_way else None
        entries.append(pm.Entry(p.position_id, leg.symbol, p.entry_ts, direction))
    days = sorted({p.entry_ts.astimezone(IST).date() for p in plan.positions})
    crude = walk(2, days)  # one series for crude and its mini
    result = pm.count(entries, {"NIFTY": walk(1, days), "CRUDEOIL": crude, "CRUDEOILM": crude})
    assert result.total == len(plan.positions) > 0
    left_out = len(result.unmeasured) + len(result.unmeasured_before)
    assert result.before.measured + left_out == result.total
    for h in pm.HORIZONS:
        out = len(result.unmeasured) + len(result.unmeasured_after[h])
        assert result.after[h].measured + out == result.total
    assert any(len(p.legs) > 1 for p in plan.positions)  # a spread, which has no single direction
    assert result.unmeasured_by_reason().get(pm.Reason.NO_DIRECTION, 0) >= 1
    assert result.before.measured > 0


MINUTE = datetime(2026, 6, 2, 11, 0, tzinfo=IST)


def _with_bars(table, *, drop=(), put=None):
    # A copy of the walk with some bars replaced and some removed; keys are minutes from 11:00.
    bars = dict(table.bars)
    for k, bar in (put or {}).items():
        bars[MINUTE + timedelta(minutes=k)] = bar
    for k in drop:
        del bars[MINUTE + timedelta(minutes=k)]
    return {"NIFTY": dataclasses.replace(table, bars=bars)}


def test_a_missing_entry_minute_bar_does_not_drop_the_before_count(table):
    entry = pm.Entry("x", "NIFTY", MINUTE + timedelta(seconds=40), 1)
    series = _with_bars(table, drop=(0,), put={-1: pm.Bar(open=100.0, close=101.0)})
    result = pm.count([entry], series)
    assert (result.before.agreed, result.before.measured) == (1, 1)
    assert result.unmeasured_before == ()
    for h in pm.HORIZONS:
        assert result.after[h].measured == 0
        assert result.unmeasured_after[h] == (pm.Unmeasured("x", pm.Reason.NO_ENTRY_BAR),)


def test_a_missing_prior_bar_does_not_drop_the_after_counts(table):
    entry = pm.Entry("x", "NIFTY", MINUTE + timedelta(seconds=40), 1)
    put = {0: pm.Bar(open=100.0, close=100.0), 5: pm.Bar(open=100.0, close=110.0)}
    result = pm.count([entry], _with_bars(table, drop=(-1,), put=put))
    assert result.before.measured == 0
    assert result.unmeasured_before == (pm.Unmeasured("x", pm.Reason.NO_PRIOR_BAR),)
    assert (result.after[5].agreed, result.after[5].measured) == (1, 1)  # 100 to 110: with him
    assert all(result.after[h].measured == 1 for h in pm.HORIZONS)


def test_a_missing_horizon_bar_drops_only_that_horizon(table):
    entry = pm.Entry("x", "NIFTY", MINUTE + timedelta(seconds=40), 1)
    result = pm.count([entry], _with_bars(table, drop=(15,)))
    assert result.before.measured == 1
    assert [result.after[h].measured for h in pm.HORIZONS] == [1, 0, 1, 1]
    assert result.unmeasured_after[15] == (pm.Unmeasured("x", pm.Reason.NO_HORIZON_BAR),)
    assert result.unmeasured_after[5] == result.unmeasured_after[30] == ()


def test_each_missing_bar_has_a_reason_that_names_it():
    reasons = {pm.Reason.NO_PRIOR_BAR, pm.Reason.NO_ENTRY_BAR, pm.Reason.NO_HORIZON_BAR}
    assert len({r.value for r in reasons}) == 3
    assert not hasattr(pm.Reason, "NO_BAR")  # the generic "no bar for that minute" is gone
