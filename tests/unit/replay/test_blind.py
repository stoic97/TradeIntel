"""Blind replay's draw, reveal and score. Every bar is a seeded random walk; no one's data."""

from __future__ import annotations

import dataclasses
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal

import numpy as np

from services.production.mirror import metrics as mx
from services.production.mirror.prior_minute import IST, Bar, BarTable
from services.production.replay import blind as B

TODAY = date(2026, 11, 13)
DAYS = [date(2025, 3, 3) + timedelta(days=i) for i in range(120) if (date(2025, 3, 3) + timedelta(days=i)).weekday() < 5]


def walk(seed: int = 5, days=DAYS) -> BarTable:
    rng = np.random.default_rng(seed)
    bars, price = {}, 20000.0
    for d in days:
        for minute in range(9 * 60 + 15, 15 * 60 + 30):
            start = datetime(d.year, d.month, d.day, minute // 60, minute % 60, tzinfo=IST)
            close = price + float(rng.choice([-2.0, -1.0, 1.0, 2.0]))
            bars[start] = Bar(open=price, close=close)
            price = close
    return BarTable(bars=bars, first_day=days[0], last_day=days[-1])


def entries(table: BarTable, n: int = 12) -> list[B.Entry]:
    starts = sorted(table.bars)
    rng = np.random.default_rng(9)
    picks = sorted(rng.choice(np.arange(200, len(starts) - 200), size=n, replace=False))
    return [B.Entry(f"t{i}", "NIFTY", starts[int(k)] + timedelta(seconds=20), 1 if i % 3 else -1)
            for i, k in enumerate(picks)]


def deal(table, es, **kw):
    return B.deal(es, {"NIFTY": table}, TODAY, key="trader-1",
                  candidates={"NIFTY": sorted(table.bars)}, **kw)


def test_random_moments_match_real_entries_on_count_month_and_direction():
    table = walk()
    dealt = deal(table, entries(table))
    real = [d for d in dealt if d.real]
    rand = [d for d in dealt if not d.real]
    assert len(real) == len(rand) == B.CARDS // 2
    month = lambda d: (d.card.moment.year, d.card.moment.month)
    assert Counter(map(month, real)) == Counter(map(month, rand))
    assert Counter(d.card.direction for d in real) == Counter(d.card.direction for d in rand)
    assert {d.card.underlying for d in dealt} == {"NIFTY"}


def test_a_random_moment_keeps_away_from_his_entries():
    table = walk()
    es = entries(table)
    for d in deal(table, es):
        if not d.real:
            gaps = [abs((d.card.moment - B._minute(e.entry_ts)).total_seconds()) for e in es]
            assert min(gaps) >= B.KEEP_AWAY_MINUTES * 60


def test_only_old_trades_are_dealt():
    recent_days = [TODAY - timedelta(days=30) + timedelta(days=i) for i in range(5)]
    table = walk(days=[d for d in recent_days if d.weekday() < 5])
    assert deal(table, entries(table, 4)) == []
    assert B.OLD_AFTER_DAYS == 180


def test_nothing_on_a_card_depends_on_what_came_after_its_moment():
    table = walk()
    es = entries(table)
    first = deal(table, es)
    for d in first:
        bars = dict(table.bars)
        for k in range(120):
            t = d.card.moment + timedelta(minutes=k)
            if t in bars:
                bars[t] = Bar(open=1.0, close=999999.0 if k % 2 else 1.0)
        again = deal(dataclasses.replace(table, bars=bars), es)
        same = [x.card for x in again if x.card.moment == d.card.moment]
        assert same == [d.card]  # its own card: dealt again, and unchanged


def test_the_card_holds_the_window_before_the_moment_and_no_answer():
    table = walk()
    d = deal(table, entries(table))[0]
    assert len(d.card.shown) == B.WINDOW_MINUTES
    assert d.card.shown[-1] == table.bars[d.card.moment - timedelta(minutes=1)]
    assert not {"real", "trip_id", "points", "agreed"} & {f.name for f in dataclasses.fields(B.Card)}


def test_the_reveal_reads_from_the_last_close_shown_to_the_horizon():
    table = walk()
    d = deal(table, entries(table))[0]
    later = table.bars[d.card.moment + timedelta(minutes=B.HORIZON_MINUTES)]
    r = B.reveal(d, {"NIFTY": table})
    assert r.points == (later.close - d.card.shown[-1].close) * d.card.direction
    assert r.agreed == (r.points > 0) and r.real == d.real


def test_the_same_trader_gets_the_same_cards():
    table = walk()
    es = entries(table)
    assert deal(table, es) == deal(table, es)


def test_a_coin_flips_band_is_binomial():
    assert B.coin_band(10) == (2, 8)
    assert B.coin_band(0) == (0, 0)


def test_the_score_counts_calls_and_compares_them_with_a_coin():
    table = walk()
    dealt = deal(table, entries(table))
    series = {"NIFTY": table}
    calls = "".join("T" if B.reveal(d, series).agreed else "S" for d in dealt)
    s = B.score(dealt, calls, series)
    assert (s.calls, s.right) == (len(dealt), len(dealt))
    assert s.band == B.coin_band(len(dealt))
    assert s.took == calls.count("T") and s.took_points > 0


def _trip(lines):
    return mx.Trip(trip_id="x", symbol="NIFTY", trading_day="2025-03-03",
                   entry_ts=datetime(2025, 3, 3, 10, tzinfo=IST), exit_ts=datetime(2025, 3, 3, 11, tzinfo=IST),
                   holding_seconds=3600, net=Decimal(0), lots=1,
                   risk_unit_source=mx.s.RiskUnitSourceV1.PREMIUM_PAID, lines=tuple(lines))


def _line(side, segment="OPT", kind="CE"):
    return mx.TradeLine(symbol="NIFTY", segment=segment, side=side, quantity=1, entry_price=None,
                        exit_price=None, net=Decimal(0), option_type=kind if segment == "OPT" else None)


def test_direction_comes_from_the_shared_rule():
    assert B.direction_of(_trip([_line("Buy", kind="CE")])) == 1
    assert B.direction_of(_trip([_line("Buy", kind="PE")])) == -1
    assert B.direction_of(_trip([_line("Sell", kind="CE")])) == -1
    assert B.direction_of(_trip([_line("Sell", kind="PE")])) == 1
    assert B.direction_of(_trip([_line("Buy", segment="FUT")])) == 1
    assert B.direction_of(_trip([_line("Buy"), _line("Sell")])) is None
