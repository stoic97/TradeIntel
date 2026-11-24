"""Where the money went: from what his trades made, through each charge, to what he kept (TICKET-995).

Read back from what the import stored (``trip_charge``), never worked out again here. Which
step a trade's charges sit in depends on where they came from:

* **calculated** (912's rate table): each component its own step, named as a contract note
  writes it.
* **tradebook** (his file carried them): one step, "Charges in your tradebook".
* **his charges file**: one step, "Charges from your charges file". Where his own file covers
  a day (828, read on the page), its day total outranks anything else for that day and is
  shared across the day's trades with ``compute.share_day``, so a day sums to his figure.
  A trade the import shared his total onto (``statement``) is in the same step.
* **not_priced** (before the rate table starts) and **none**: left out, counted, and never
  mixed into an after-charges total (ruled 14 Nov 2026; ``compute.py``).

An import stored before this ticket has no ``trip_charge`` rows: it reads as tradebook where
the file carried charges, otherwise as none, and the charges file then applies to the days it
covers. Reading the file again stores the rows.

Everything is Decimal. Before charges less the steps is after charges, exactly; rounding is for
display only.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.production.charges import compute
from services.production.charges import record as statement_record
from services.production.db import models as m
from services.production.mirror import metrics as mx

ZERO = Decimal(0)

NAMES = {
    "BROKERAGE": "Brokerage",
    "STT": "STT",
    "CTT": "CTT",
    "EXCHANGE": "Exchange transaction charges",
    "SEBI": "SEBI fee",
    "STAMP": "Stamp duty",
    "GST": "GST",
    "IPFT": "IPFT (investor protection fund charge)",
    "tradebook": "Charges in your tradebook",
    "file": "Charges from your charges file",
}
"""Each step's name, as a contract note writes it."""

LEFT_OUT = frozenset({"not_priced", "none"})


@dataclass(frozen=True)
class TripCharge:
    """One trade's charges as stored: by position, the way the report reads a trade."""

    trip_id: str  # as the report's Trip names it (a position's id, or the leg's)
    trading_day: str
    gross: Decimal
    source: str  # calculated, tradebook, file, or a left-out source
    components: dict[str, Decimal] = field(default_factory=dict)

    @property
    def total(self) -> Decimal:
        return sum(self.components.values(), ZERO)


@dataclass(frozen=True)
class Step:
    key: str
    name: str
    amount: Decimal
    trip_ids: frozenset[str]


@dataclass(frozen=True)
class Waterfall:
    before: Decimal
    steps: tuple[Step, ...]
    after: Decimal
    included: tuple[str, ...]  # one id per included trade, a repeated identical trade twice
    left_out: int

    @property
    def charges(self) -> Decimal:
        return sum((s.amount for s in self.steps), ZERO)

    @property
    def per_trade(self) -> Decimal | None:
        return self.charges / len(self.included) if self.included else None


EMPTY = Waterfall(ZERO, (), ZERO, (), 0)


def _legs(sess: Session, imp: m.Import) -> dict[object, list[m.Trip]]:
    """The import's trips grouped as the loader groups them: a position's legs are one trade."""
    rows = sess.scalars(select(m.Trip).where(m.Trip.import_id == imp.id).order_by(m.Trip.entry_ts))
    out: dict[object, list[m.Trip]] = {}
    for row in rows:
        out.setdefault(row.position_id or row.id, []).append(row)
    return out


def load(sess: Session, trader: m.Trader, imp: m.Import | None) -> list[TripCharge]:
    """Every trade's charges for this import, by source, read from what was stored."""
    if imp is None:
        return []
    stored: dict[int, list[m.TripCharge]] = {}
    for c in sess.scalars(select(m.TripCharge).where(m.TripCharge.import_id == imp.id)):
        stored.setdefault(c.trip_row_id, []).append(c)
    old = not stored
    out: list[TripCharge] = []
    for legs in _legs(sess, imp).values():
        first = legs[0]
        sources, parts = set(), {}
        for leg in legs:
            rows = stored.get(leg.id, [])
            source = (("tradebook" if imp.fees_available else "none") if old or not rows
                      else rows[0].source)
            sources.add(source)
            if source == "calculated":
                for r in rows:
                    parts[r.component] = parts.get(r.component, ZERO) + r.amount
            elif source in ("tradebook", "statement"):
                key = "tradebook" if source == "tradebook" else "file"
                parts[key] = parts.get(key, ZERO) + leg.fees
        if sources & LEFT_OUT:
            source, parts = "none", {}
        elif sources == {"calculated"}:
            source = "calculated"
        elif "tradebook" in sources:
            source = "tradebook"
        else:
            source = "file"
        out.append(TripCharge(
            trip_id=first.position_id or first.trip_id, trading_day=first.trading_day,
            gross=sum((leg.gross for leg in legs), ZERO), source=source, components=parts))
    return _his_file(sess, trader, imp, out)


def _his_file(sess: Session, trader: m.Trader, imp: m.Import,
              trips: list[TripCharge]) -> list[TripCharge]:
    """His own charges file outranks the rest on every day it covers (828)."""
    if imp.fees_available:
        return trips
    stated = statement_record.statement_days(sess, trader)
    if not stated:
        return trips
    out = list(trips)
    days: dict[str, list[int]] = {}
    for i, t in enumerate(trips):
        if t.trading_day in stated:
            days.setdefault(t.trading_day, []).append(i)
    for day, at in days.items():
        ours = [trips[i].total if trips[i].source == "calculated" else None for i in at]
        for i, share in zip(at, compute.share_day(stated[day], ours), strict=True):
            t = trips[i]
            out[i] = TripCharge(t.trip_id, t.trading_day, t.gross, "file", {"file": share})
    return out


def build(entries: Iterable[TripCharge], trips: list[mx.Trip]) -> Waterfall:
    """The waterfall over the trades shown (the report filter's), largest step first."""
    shown = {t.trip_id for t in trips}
    mine = [e for e in entries if e.trip_id in shown]
    kept = [e for e in mine if e.source not in LEFT_OUT]
    if not kept:
        return Waterfall(ZERO, (), ZERO, (), len(mine))
    totals: dict[str, Decimal] = {}
    charged: dict[str, set[str]] = {}
    for e in kept:
        for key, amount in e.components.items():
            totals[key] = totals.get(key, ZERO) + amount
            if amount:
                charged.setdefault(key, set()).add(e.trip_id)
    steps = tuple(sorted(
        (Step(k, NAMES.get(k, k), a, frozenset(charged.get(k, ()))) for k, a in totals.items()),
        key=lambda s: (-s.amount, s.name)))
    before = sum((e.gross for e in kept), ZERO)
    return Waterfall(before=before, steps=steps,
                     after=before - sum((s.amount for s in steps), ZERO),
                     included=tuple(e.trip_id for e in kept), left_out=len(mine) - len(kept))
