"""TICKET-1026, the ruling of 24 Nov 2026 on PR #208 (decided under the founder's delegation):
the Your numbers day tiles count same-day trades only (the 23 Nov "held" ruling), and each tile's
link opens the trades closed that day that also closed the same day they opened. So 1022's rule
still holds: the list a figure opens holds exactly the trades it counts.

Made-up record, worked by hand. By the day he closed:
    9 Mar  e +50                               same day
   10 Mar  a +500 (opened 9 Mar), b +100       a held past its day, b same day
   11 Mar  c -300 (opened 10 Mar), d -50       c held past its day, d same day
Same-day trades by the day he closed: 9 Mar +50 (e), 10 Mar +100 (b), 11 Mar -50 (d).
Best day 10 Mar +100 over 1 trade; worst day 11 Mar -50 over 1 trade.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from html import unescape
from zoneinfo import ZoneInfo

import pytest

from services.production.api import numbers as N
from services.production.api import scope_facts as SF
from services.production.api import trade_list as TL
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def trip(tid: str, opened: str, closed: str, net: str) -> mx.Trip:
    entry = datetime.fromisoformat(opened).replace(tzinfo=IST)
    leave = datetime.fromisoformat(closed).replace(tzinfo=IST)
    return mx.Trip(
        trip_id=tid, symbol="NIFTY", trading_day=entry.date().isoformat(), entry_ts=entry,
        exit_ts=leave, holding_seconds=int((leave - entry).total_seconds()), net=D(net), lots=1,
        risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True,
        lines=(mx.TradeLine("NIFTY", "OPT", "Buy", 1, None, None, D(net)),),
    )


RECORD = [
    trip("e", "2026-03-09T09:40", "2026-03-09T10:00", "50"),
    trip("a", "2026-03-09T14:00", "2026-03-10T10:00", "500"),
    trip("b", "2026-03-10T09:40", "2026-03-10T10:00", "100"),
    trip("c", "2026-03-10T14:00", "2026-03-11T10:00", "-300"),
    trip("d", "2026-03-11T11:00", "2026-03-11T11:20", "-50"),
]


def opened_by(href: str) -> list[mx.Trip]:
    """The trades the tile's own link opens, read through the trade list itself."""
    query = dict(part.split("=", 1) for part in unescape(href).split("?", 1)[1].split("&"))
    ctx = SF.record_context(RECORD)
    listing = TL.listing("risk", ctx, query, {})
    numbers = [row["number"] for g in listing["groups"] for row in g["trades"]]
    assert len(numbers) == listing["shown"]
    return [ctx["trips"][n - 1] for n in numbers]


@pytest.mark.parametrize("key, iso, ids, net", [
    ("best_day", "2026-03-10", ["b"], D(100)),
    ("worst_day", "2026-03-11", ["d"], D(-50)),
    ("per_day", "2026-03-09", ["e"], None),
])
def test_each_day_tile_counts_same_day_trades_and_its_link_opens_exactly_those(key, iso, ids, net):
    tile = N.build(RECORD, {}, gross=True)["tiles"][key]
    assert tile["day"] == iso
    assert "same_day=yes" in tile["href"] and f"closed_day={iso}" in tile["href"]
    shown = opened_by(tile["href"])
    assert sorted(t.trip_id for t in shown) == ids
    if net is not None:
        assert tile["value"] == net == sum(t.net for t in shown)
    else:
        assert tile["most"] == len(shown)


def test_the_same_day_filter_keeps_exactly_the_trades_that_closed_the_day_they_opened():
    f = next(f for f in TL.FILTERS if f.name == "same_day")
    assert f.quiet  # offered only when a link has chosen it, as closed_day is
    kept = [t.trip_id for t in RECORD if (c := f.read(t, {})) is not None and c[1] == "yes"]
    assert kept == ["e", "b", "d"]
