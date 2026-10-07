"""Write corpus A out as an engine reads a trader: fills in the CTR shape, plus truth.

A synthetic history leaves the generator the way a real tradebook arrives - as
broker-style fills (``ctr_v1.Fill``) - so the engine meets it through the same
``reconstruct`` path as a design partner's export. Beside the fills sit the
answers the engine is never shown: per trip, the generator's own R, flags and
applied behaviours; per history, the planting and the twin's avoidable cost.

Conventions, each a choice the engine must not depend on:

* **Contract.** The series is a stitched continuous contract, so each trip is
  given the MCX CRUDEOIL future expiring on the 19th: of the entry month when
  entered on or before the 19th, otherwise of the next month
  (``corpus.contract_expiry``). A carried trip stays in its entry contract, which
  is why the generator never carries across an expiry (``corpus._carry_allowed``).
* **Market.** Each history's fills take their dates, times and prices from the
  market its trips index into: its own random walk for a clean null, the shared
  crude series for everything else.
* **Size.** One generator unit is ``LOTS_PER_UNIT`` lots; any size rounds to at
  least one lot. Rounding is why the truth table, not the fills, holds exact R.
* **Prices** are written to the paisa. **Times** are the bar's minute in IST:
  entries at :00, adds at :30, exits at :59, so fills on one bar keep their order.
* **No stop orders are exported** (CTR v1 has no field for them), so every
  futures trip reconstructs with ``risk_unit=None``. The truth table carries the
  generator's risk per trip until the inferred risk unit exists (Thesis
  glossary: size x volatility at entry, labelled inferred).

Output is gzip'd JSON Lines with sorted keys and a zero gzip timestamp, so the same
corpus is the same bytes on any machine. ``manifest.json`` records the sha256 of
each table's uncompressed content and two digests:

* ``corpus_sha256`` over all three tables, floats included. It is exact for one
  environment (the ``uv.lock`` pins); another numpy or CPU moves the last digits of
  R, risk and size and so moves this digest.
* ``decision_sha256`` over every fill (exact decimals) and every label - trip
  boundaries, direction, exit reason, flags, applied behaviours, carries, adds,
  cells, nominal sizes, reached marks - and no float. Research Spec §12.1 splits
  determinism this way: decisions must match on every platform, computed decimals
  only within one. This is the digest compared across machines.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Iterable, Iterator
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from services.production.ctr.reconstruct import reconstruct
from services.research.evaluation.synthetic.corpus import (
    GRID_VERSION,
    Market,
    SyntheticHistory,
    contract_expiry,
)
from services.research.evaluation.synthetic.trader import LONG, Trip
from services.shared.schemas.ctr_v1 import Fill, Segment, Side

IST = ZoneInfo("Asia/Kolkata")
LOTS_PER_UNIT = 4
SYMBOL, EXCHANGE, BROKER = "CRUDEOIL", "MCX", "SYNTHETIC"
_PAISA = Decimal("0.01")


def lots(units: float) -> int:
    return max(1, round(units * LOTS_PER_UNIT))


def history_id(h: SyntheticHistory) -> str:
    return f"{h.kind}-{h.seed}"


def _ts(market: Market, bar: int, second: int) -> datetime:
    bars = market.history.bars
    day = market.history.dates[int(bars.day[bar])]
    minute = int(bars.minute[bar])
    return datetime.combine(day, time(minute // 60, minute % 60, second), tzinfo=IST)


def _price(x: float) -> Decimal:
    return Decimal(repr(x)).quantize(_PAISA)


def market_of(h: SyntheticHistory, shared: Market) -> Market:
    return h.market if h.market is not None else shared


def _legs(t: Trip, market: Market) -> list[tuple[datetime, Side, int, Decimal]]:
    """(time, side, lots, price) per fill of one trip: entry, adds, exit."""
    opening = Side.BUY if t.direction == LONG else Side.SELL
    closing = Side.SELL if opening is Side.BUY else Side.BUY
    legs = [(t.entry_idx, 0, opening, lots(t.size), t.entry_price)]
    legs += [(bar, 30, opening, lots(units), price) for bar, price, units in t.adds]
    total = sum(q for _, _, _, q, _ in legs)
    legs.append((t.exit_idx, 59, closing, total, t.exit_price))
    return [(_ts(market, bar, sec), side, qty, _price(px)) for bar, sec, side, qty, px in legs]


def to_fills(h: SyntheticHistory, shared: Market) -> list[Fill]:
    market = market_of(h, shared)
    trader = history_id(h)
    raw = hashlib.sha256(f"{GRID_VERSION}|{trader}".encode()).hexdigest()
    fills: list[Fill] = []
    for t in h.trips:
        entry_day = market.history.dates[t.day]
        common: dict[str, Any] = {
            "trader_id": trader,
            "broker": BROKER,
            "exchange": EXCHANGE,
            "segment": Segment.FUT,
            "symbol": SYMBOL,
            "expiry": contract_expiry(entry_day),
            "raw_hash": raw,
        }
        for ts, side, qty, price in _legs(t, market):
            fills.append(
                Fill(**common, ts=ts, side=side, quantity=qty, price=price, trade_value=price * qty)
            )
    return fills


def fill_rows(h: SyntheticHistory, fills: list[Fill]) -> Iterator[dict[str, Any]]:
    for f in fills:
        yield {"history_id": history_id(h), **f.model_dump(mode="json")}


def truth_rows(h: SyntheticHistory) -> Iterator[dict[str, Any]]:
    for seq, t in enumerate(h.trips):
        yield {"history_id": history_id(h), "seq": seq, **_trip_truth(t)}


def _trip_truth(t: Trip) -> dict[str, Any]:
    return {
        "day": t.day,
        "entry_idx": t.entry_idx,
        "exit_idx": t.exit_idx,
        "direction": "LONG" if t.direction == LONG else "SHORT",
        "r_multiple": t.r_multiple,
        "risk_per_unit": t.risk_per_unit,
        "size": t.size,
        "exit_reason": t.exit_reason,
        "flags": list(t.flags),
        "applied": list(t.applied),
        "stop_moved": t.stop_moved,
        "n_adds": len(t.adds),
        "carried": t.carried,
    }


def history_row(h: SyntheticHistory) -> dict[str, Any]:
    row: dict[str, Any] = {
        "history_id": history_id(h),
        "kind": h.kind,
        "seed": h.seed,
        "n_trades": h.n_trades,
        "truth": dict(sorted(h.truth.items())),
    }
    if h.cell is not None and h.planting is not None:
        row["cell"] = {
            "index": h.cell.index,
            "test_id": h.cell.test_id,
            "multiple": h.cell.multiple,
        }
        row["planting"] = {
            "nominal": h.planting.nominal,
            "unit": h.planting.unit,
            "reached": h.planting.reached,
            "behaviours": [
                {
                    "test_id": b.test_id,
                    "mechanism": b.mechanism.value,
                    "strength": b.strength,
                    "prevalence": b.prevalence,
                }
                for b in h.planting.behaviours
            ],
        }
    return row


def verify_round_trip(h: SyntheticHistory, fills: list[Fill], shared: Market) -> None:
    """The fills must reconstruct into exactly the generator's trips, in order.

    Checked per trip: direction, quantity, entry and exit time, entry and exit
    price, and that the exit is not after the contract's expiry.
    """
    market = market_of(h, shared)
    recon = reconstruct(fills)
    trips = sorted(recon.round_trips, key=lambda r: r.entry_ts)
    if recon.open_positions or recon.skipped or len(trips) != len(h.trips):
        raise AssertionError(f"{history_id(h)}: fills do not reconstruct into its trips")
    for r, t in zip(trips, h.trips, strict=True):
        legs = _legs(t, market)
        want = (
            "LONG" if t.direction == LONG else "SHORT",
            sum(q for _, _, q, _ in legs[:-1]),
            legs[0][0],
            legs[-1][0],
            legs[-1][3],
        )
        got = (r.direction.value, r.quantity, r.entry_ts, r.exit_ts, r.exit_price)
        if got != want or (len(legs) == 2 and r.entry_price != legs[0][3]):
            raise AssertionError(f"{history_id(h)}: trip mismatch at entry {r.entry_ts}")
        if r.expiry is None or r.exit_ts.date() > r.expiry:
            raise AssertionError(f"{history_id(h)}: trip exits after its contract expired")


def _line(row: dict[str, Any]) -> bytes:
    return (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()


class _Table:
    """A gzip'd JSON Lines table whose content hash is taken over uncompressed bytes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.rows = 0
        self._sha = hashlib.sha256()
        self._raw = path.open("wb")
        self._gz = gzip.GzipFile(filename="", mode="wb", fileobj=self._raw, mtime=0)

    def write(self, rows: Iterable[dict[str, Any]]) -> None:
        for row in rows:
            line = _line(row)
            self._sha.update(line)
            self._gz.write(line)
            self.rows += 1

    def close(self) -> dict[str, Any]:
        self._gz.close()
        self._raw.close()
        return {"file": self.path.name, "rows": self.rows, "sha256": self._sha.hexdigest()}


_TRIP_DECISION_KEYS = (
    *("history_id", "seq", "day", "entry_idx", "exit_idx", "direction"),
    *("exit_reason", "flags", "applied", "stop_moved", "n_adds", "carried"),
)


def _decision_rows(h: SyntheticHistory, fills: list[Fill]) -> Iterator[dict[str, Any]]:
    """Everything that must be identical on every platform: no float in it."""
    for row in fill_rows(h, fills):
        yield {"table": "fills", **row}
    for row in truth_rows(h):
        yield {"table": "trips", **{k: row[k] for k in _TRIP_DECISION_KEYS}}
    hist = history_row(h)
    labels: dict[str, Any] = {
        "table": "histories",
        "history_id": hist["history_id"],
        "kind": hist["kind"],
        "seed": hist["seed"],
        "n_trades": hist["n_trades"],
        "n_flagged": h.truth.get("n_flagged"),
        "n_applied": h.truth.get("n_applied"),
        "start_day": h.truth.get("start_day"),
    }
    if "cell" in hist:
        labels["cell"] = hist["cell"]
        labels["planted"] = {
            "unit": hist["planting"]["unit"],
            "reached": hist["planting"]["reached"],
            "behaviours": [
                {"test_id": b["test_id"], "mechanism": b["mechanism"]}
                for b in hist["planting"]["behaviours"]
            ],
        }
    yield labels


def write_corpus(
    histories: Iterable[SyntheticHistory],
    market: Market,
    out: Path,
    source: dict[str, Any],
) -> dict[str, Any]:
    """Write fills, truth and histories to ``out``; return (and write) the manifest."""
    out.mkdir(parents=True, exist_ok=True)
    tables = {name: _Table(out / f"{name}.jsonl.gz") for name in ("fills", "trips", "histories")}
    kinds: dict[str, int] = {}
    decision = hashlib.sha256()
    for h in histories:
        fills = to_fills(h, market)
        verify_round_trip(h, fills, market)
        for row in _decision_rows(h, fills):
            decision.update(_line(row))
        tables["fills"].write(fill_rows(h, fills))
        tables["trips"].write(truth_rows(h))
        tables["histories"].write([history_row(h)])
        kinds[h.kind] = kinds.get(h.kind, 0) + 1
    files = {name: table.close() for name, table in tables.items()}
    corpus = hashlib.sha256(
        "".join(f"{n}:{files[n]['sha256']}\n" for n in sorted(files)).encode()
    ).hexdigest()
    manifest = {
        "grid_version": GRID_VERSION,
        "source": dict(sorted(source.items())),
        "histories": dict(sorted(kinds.items())),
        "tables": files,
        "corpus_sha256": corpus,
        "decision_sha256": decision.hexdigest(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return manifest
