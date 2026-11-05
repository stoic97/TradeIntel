"""Generate the Scope demo tradebook: a synthetic Dhan export (TICKET-842).

Run: python data/fixtures/demo/scope_demo.py   (from the repository root)

A visitor without his broker export opens Scope on this file. It goes through the
ordinary upload pipeline, so every figure he sees is the pipeline's, read from this
file; nothing on a demo page is typed by hand.

**No one's trading.** Every row is drawn from ``random.Random(SEED)``: no real
trader's rows, no figure taken from any history (README rule 1). The instruments are
real contracts (MCX CRUDEOIL and NSE NIFTY options), because the adapter reads only
instruments it has a profile for. A contract name is a market fact, not a trader's.

**Reproducible.** The seed is committed and the generator uses only the standard
library, so the same seed writes the same bytes on any machine.
``tests/unit/demo/test_demo_tradebook.py`` fails if the committed file and this
script disagree.

**What it must contain** (the ticket's gate 2), each placed on purpose:

* enough history for the eligibility page: three months of weekdays, and several
  trades on most days, so trades after two earlier same-day trades are common;
* two books: crude options most days, NIFTY options on most days, at least thirty
  trades each (one book's rows need thirty to be shown);
* a long losing run, and a few heavy days that become the worst five;
* spreads: one bought and one sold leg on the same expiry, entered seconds apart
  (Annex H's link window is 180 s);
* sold options: a put sold and bought back the same day;
* held positions: a bought option carried for several days, product MARGIN.

Dhan's shape: the header verbatim, newest first, INTRADAY for same-day trades, the
trade value exact and the price its value per unit.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

SEED = 842  # the ticket's number: any fixed value would do; this one is findable
FIRST_DAY = date(2026, 6, 1)
LAST_DAY = date(2026, 8, 31)

HERE = Path(__file__).resolve().parent
OUT = HERE / "scope_demo_tradebook.csv"

HEADER = ("Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,"
          "Trade Price,Trade Value,Status")

CRUDE_LOT = 100   # MCX CRUDEOIL: 100 barrels a lot (profile contract_multiplier)
NIFTY_LOT = 65    # NSE NIFTY: 65 units a lot from 29 Dec 2025 (profile lot_sizes)

_MON = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


@dataclass(frozen=True)
class Row:
    at: datetime
    name: str
    side: str           # BUY | SELL
    product: str        # INTRADAY | MARGIN
    exchange: str       # MCX | NSE
    segment: str        # Commodity | Derivative
    quantity: int
    price: Decimal

    @property
    def value(self) -> Decimal:
        return self.price * self.quantity

    def line(self) -> str:
        return ",".join((
            self.at.strftime("%Y-%m-%d"), self.at.strftime("%H:%M:%S"), self.name,
            self.side, self.product, self.exchange, self.segment, str(self.quantity),
            f"{self.price:.2f}", f"{self.value:.2f}", "Traded",
        ))


def weekdays(first: date, last: date) -> list[date]:
    days, d = [], first
    while d <= last:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def crude_expiry(on: date) -> date:
    """The 16th of the month while it is at least three days away, else next month's."""
    candidate = date(on.year, on.month, 16)
    if (candidate - on).days < 3:
        month = on.month % 12 + 1
        candidate = date(on.year + (on.month == 12), month, 16)
    return candidate


def nifty_expiry(on: date) -> date:
    """The next Tuesday after the trade day (NIFTY's weekly expiry)."""
    ahead = (1 - on.weekday()) % 7 or 7
    return on + timedelta(days=ahead)


def far_crude_expiry(on: date) -> date:
    """The month after the ordinary one: planted positions sit on their own expiry, so an
    ordinary trade entered within the link window can never join them (Annex H links
    legs only on the same expiry)."""
    near = crude_expiry(on)
    return date(near.year + (near.month == 12), near.month % 12 + 1, 16)


def far_nifty_expiry(on: date) -> date:
    """A week after the ordinary weekly expiry, for the same reason."""
    return nifty_expiry(on) + timedelta(days=7)


def contract(symbol: str, expiry: date, strike: int, kind: str) -> str:
    return f"{symbol} {expiry.day:02d} {_MON[expiry.month - 1]} {strike} {kind}"


def crude_price(x: float) -> Decimal:
    return Decimal(max(1, round(x)))  # crude options tick in whole rupees


def nifty_price(x: float) -> Decimal:
    return (Decimal(round(max(0.05, x) * 20)) / 20).quantize(Decimal("0.01"))  # 0.05 tick


class Demo:
    def __init__(self, seed: int = SEED) -> None:
        self.rng = random.Random(seed)
        self.rows: list[Row] = []

    def _trip(self, *, entry: datetime, exit_: datetime, name: str, exchange: str,
              segment: str, quantity: int, open_price: Decimal, close_price: Decimal,
              sold: bool = False, product: str = "INTRADAY") -> None:
        first, second = ("SELL", "BUY") if sold else ("BUY", "SELL")
        self.rows.append(Row(entry, name, first, product, exchange, segment, quantity,
                             open_price))
        self.rows.append(Row(exit_, name, second, product, exchange, segment, quantity,
                             close_price))

    def _move(self, lose: bool | None) -> float:
        # Slightly worse than even, as most retail option buyers' records are: the demo
        # should show the product's reveal, which needs a losing whole (handoff 7).
        win = (self.rng.random() < 0.42) if lose is None else not lose
        return self.rng.uniform(0.06, 0.32) if win else -self.rng.uniform(0.08, 0.40)

    def crude_day(self, day: date, count: int, forced_losses: int = 0,
                  heavy: bool = False) -> None:
        clock = datetime.combine(day, time(10, 0)) + timedelta(minutes=self.rng.randint(0, 40))
        expiry = crude_expiry(day)
        for i in range(count):
            hold = timedelta(minutes=self.rng.randint(6, 55), seconds=self.rng.randint(0, 59))
            premium = self.rng.uniform(80, 220)
            move = self._move(True if i < forced_losses else None)
            lots = self.rng.choice((3, 4)) if heavy else self.rng.choice((1, 1, 2, 2, 3))
            strike = 50 * self.rng.randint(110, 130)
            kind = self.rng.choice(("CALL", "PUT"))
            self._trip(entry=clock, exit_=clock + hold,
                       name=contract("CRUDEOIL", expiry, strike, kind), exchange="MCX",
                       segment="Commodity", quantity=lots * CRUDE_LOT,
                       open_price=crude_price(premium),
                       close_price=crude_price(premium * (1 + move)))
            clock += hold + timedelta(minutes=self.rng.randint(8, 70))
            if clock.time() > time(22, 30):
                break

    def nifty_day(self, day: date, count: int) -> None:
        clock = datetime.combine(day, time(9, 25)) + timedelta(minutes=self.rng.randint(0, 30))
        expiry = nifty_expiry(day)
        for _ in range(count):
            hold = timedelta(minutes=self.rng.randint(5, 45), seconds=self.rng.randint(0, 59))
            premium = self.rng.uniform(60, 180)
            move = self._move(None)
            strike = 50 * self.rng.randint(480, 520)
            self._trip(entry=clock, exit_=clock + hold,
                       name=contract("NIFTY", expiry, strike, self.rng.choice(("CALL", "PUT"))),
                       exchange="NSE", segment="Derivative",
                       quantity=self.rng.choice((1, 2, 2, 3)) * NIFTY_LOT,
                       open_price=nifty_price(premium),
                       close_price=nifty_price(premium * (1 + move)))
            clock += hold + timedelta(minutes=self.rng.randint(10, 60))
            if clock.time() > time(14, 50):
                break

    def crude_spread(self, day: date, at: time) -> None:
        """A bought call and a sold call one strike-step up: one position (Annex H)."""
        entry = datetime.combine(day, at)
        exit_ = entry + timedelta(minutes=self.rng.randint(25, 70))
        expiry, low = far_crude_expiry(day), 50 * self.rng.randint(115, 125)
        bought, sold = self.rng.uniform(120, 180), self.rng.uniform(60, 100)
        move = self._move(None)
        self._trip(entry=entry, exit_=exit_, name=contract("CRUDEOIL", expiry, low, "CALL"),
                   exchange="MCX", segment="Commodity", quantity=CRUDE_LOT,
                   open_price=crude_price(bought), close_price=crude_price(bought * (1 + move)))
        self._trip(entry=entry + timedelta(seconds=self.rng.randint(5, 40)),
                   exit_=exit_ + timedelta(seconds=self.rng.randint(5, 40)),
                   name=contract("CRUDEOIL", expiry, low + 100, "CALL"), exchange="MCX",
                   segment="Commodity", quantity=CRUDE_LOT, sold=True,
                   open_price=crude_price(sold), close_price=crude_price(sold * (1 + move)))

    def nifty_spread(self, day: date, at: time) -> None:
        """A bought put and a sold put one strike-step down."""
        entry = datetime.combine(day, at)
        exit_ = entry + timedelta(minutes=self.rng.randint(20, 60))
        expiry, high = far_nifty_expiry(day), 50 * self.rng.randint(490, 510)
        bought, sold = self.rng.uniform(90, 150), self.rng.uniform(40, 80)
        move = self._move(None)
        self._trip(entry=entry, exit_=exit_, name=contract("NIFTY", expiry, high, "PUT"),
                   exchange="NSE", segment="Derivative", quantity=NIFTY_LOT,
                   open_price=nifty_price(bought), close_price=nifty_price(bought * (1 + move)))
        self._trip(entry=entry + timedelta(seconds=self.rng.randint(5, 40)),
                   exit_=exit_ + timedelta(seconds=self.rng.randint(5, 40)),
                   name=contract("NIFTY", expiry, high - 100, "PUT"), exchange="NSE",
                   segment="Derivative", quantity=NIFTY_LOT, sold=True,
                   open_price=nifty_price(sold), close_price=nifty_price(sold * (1 + move)))

    def sold_put(self, day: date, at: time) -> None:
        """A NIFTY put sold on its own and bought back the same day."""
        entry = datetime.combine(day, at)
        premium = self.rng.uniform(70, 140)
        self._trip(entry=entry, exit_=entry + timedelta(minutes=self.rng.randint(30, 90)),
                   name=contract("NIFTY", far_nifty_expiry(day), 50 * self.rng.randint(470, 490),
                                 "PUT"),
                   exchange="NSE", segment="Derivative", quantity=NIFTY_LOT, sold=True,
                   open_price=nifty_price(premium),
                   close_price=nifty_price(premium * (1 - self._move(None))))

    def held_call(self, day: date, days_held: int) -> None:
        """A crude call bought and carried for several days (product MARGIN)."""
        entry = datetime.combine(day, time(11, 5, self.rng.randint(0, 59)))
        exit_ = datetime.combine(day + timedelta(days=days_held),
                                 time(15, 40, self.rng.randint(0, 59)))
        expiry = far_crude_expiry(day + timedelta(days=days_held))
        premium = self.rng.uniform(150, 250)
        self._trip(entry=entry, exit_=exit_,
                   name=contract("CRUDEOIL", expiry, 50 * self.rng.randint(118, 126), "CALL"),
                   exchange="MCX", segment="Commodity", quantity=CRUDE_LOT, product="MARGIN",
                   open_price=crude_price(premium),
                   close_price=crude_price(premium * (1 + self.rng.uniform(-0.3, 0.6))))


def build(seed: int = SEED) -> list[Row]:
    demo = Demo(seed)
    days = weekdays(FIRST_DAY, LAST_DAY)
    losing_run_days = set(days[20:23])          # seven straight losers across three days
    heavy_days = {days[9], days[31], days[52]}  # bigger size: the worst five pick from these
    for i, day in enumerate(days):
        if day in losing_run_days:
            demo.crude_day(day, count=3, forced_losses=3 if day != days[22] else 1)
        else:
            demo.crude_day(day, count=demo.rng.randint(3, 6), heavy=day in heavy_days)
        if i % 5 != 4:                          # NIFTY on four days in five
            demo.nifty_day(day, count=demo.rng.randint(1, 2))
    for day in (days[5], days[27], days[44], days[60]):
        demo.crude_spread(day, time(13, 10))
    demo.nifty_spread(days[38], time(12, 5))
    for day in (days[12], days[35], days[57]):
        demo.sold_put(day, time(13, 30))
    demo.held_call(days[15], days_held=3)       # carried over a weekend's worth of days
    demo.held_call(days[47], days_held=2)
    return sorted(demo.rows, key=lambda r: (r.at, r.name, r.side), reverse=True)  # newest first


def render(seed: int = SEED) -> str:
    return "\n".join([HEADER, *(r.line() for r in build(seed))]) + "\n"


if __name__ == "__main__":
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT.name}: {len(build())} rows")
