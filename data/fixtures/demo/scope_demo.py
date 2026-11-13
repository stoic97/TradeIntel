"""Generate the Scope sample trader: a synthetic Dhan export (TICKET-842, TICKET-914).

Run: python data/fixtures/demo/scope_demo.py   (from the repository root)

/sample and "Try it with a demo file" both read this file through the ordinary upload
pipeline, so every figure a visitor sees is the pipeline's, read from these rows; nothing
on a sample page is typed by hand.

**An invented trader, with habits declared before a single row was drawn.** The first
version was built to touch every feature. This one is a person a retail trader would
recognise, and his habits are written down here, in ``HABITS``, as generic rules: none
is taken from any real trader's record (README rule 1). The seed was fixed with them and
the file is whatever they produce. It is **not tuned until a finding fires**: if a habit
doesn't show up in the report, that is the report's honest reading of this file, and the
seed and the numbers stay as they are. Changing either needs its own reason, written here.

*One correction, 13 Nov 2026, before anything was committed.* The first draw came out
+22,146 overall, NIFTY winning 56 of 118 against a declared 42 in 100. The habit as
declared, "slightly worse than even", had been written as an edge of about -1.5% of
premium a trade, which chance easily outweighs over a few hundred trades: the numbers
didn't say what the words said. A loser now gives up 15-45% of its premium rather than
10-35%, about -6% a trade. Same seed, nothing else changed, and the result was taken as
it came. No other change was made to reach any figure in the report.

**Reproducible.** The seed is committed and the generator uses only the standard
library, so the same seed writes the same bytes on any machine.
``tests/unit/demo/test_demo_tradebook.py`` fails if the committed file and this
script disagree.

**Still in it, from TICKET-842,** because the report talks about each: a spread (one
bought and one sold leg on the same expiry, entered seconds apart), a sold option, and a
position carried for days.

Dhan's shape: the header verbatim, newest first, INTRADAY for same-day trades, DELIVERY
for shares held, the trade value exact and the price its value per unit.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

SEED = 914  # fixed with HABITS, before the first row was drawn; never searched for
FIRST_DAY = date(2026, 6, 1)
LAST_DAY = date(2026, 8, 31)

HERE = Path(__file__).resolve().parent
OUT = HERE / "scope_demo_tradebook.csv"

HEADER = ("Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,"
          "Trade Price,Trade Value,Status")

CRUDE = "CRUDEOILM"  # the mini: a retail account's crude (profile MCX_CRUDEOILM)
CRUDE_LOT = 10       # barrels a lot (profile contract_multiplier)
NIFTY_LOT = 65       # NSE NIFTY: 65 units a lot from 29 Dec 2025 (profile lot_sizes)
ETF = "NIFTYBEES"    # an index ETF, held, not traded (profile NSE_EQUITY)


@dataclass(frozen=True)
class Habits:
    """Who this trader is, in rules. Generic: what many retail option buyers do."""

    lots: tuple[int, ...] = (1, 1, 1, 1, 1, 1, 1, 2, 2, 3)  # mostly one lot
    nifty_days: float = 0.7          # share of weekdays with a NIFTY morning
    crude_days: float = 0.8          # share of weekdays with a crude evening
    nifty_morning: tuple[time, time] = (time(9, 20), time(11, 30))
    crude_evening: tuple[time, time] = (time(18, 0), time(22, 45))
    trades_per_sitting: tuple[int, int] = (1, 5)
    win_chance: float = 0.42         # slightly worse than even, as option buyers often are
    win_move: tuple[float, float] = (0.10, 0.45)   # a winner's premium change
    loss_move: tuple[float, float] = (0.15, 0.45)  # a loser's: decay works against a buyer
    up_size_after: int = 2           # losses in a row in one sitting before size goes up
    max_lots: int = 4
    flip_after_loss: float = 0.5     # calls to puts, or back, after a loss
    winner_hold_min: tuple[int, int] = (12, 50)
    loser_hold_min: tuple[int, int] = (3, 14)    # losers cut faster than winners
    gap_after_loss_min: tuple[int, int] = (1, 4)  # quick to go again after a loss
    gap_after_win_min: tuple[int, int] = (15, 60)
    etf_units: int = 200             # one ETF position, bought early and held


HABITS = Habits()

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
    def __init__(self, seed: int = SEED, habits: Habits = HABITS) -> None:
        self.rng = random.Random(seed)
        self.habits = habits
        self.rows: list[Row] = []

    def _trip(self, *, entry: datetime, exit_: datetime, name: str, exchange: str,
              segment: str, quantity: int, open_price: Decimal, close_price: Decimal,
              sold: bool = False, product: str = "INTRADAY") -> None:
        first, second = ("SELL", "BUY") if sold else ("BUY", "SELL")
        self.rows.append(Row(entry, name, first, product, exchange, segment, quantity,
                             open_price))
        self.rows.append(Row(exit_, name, second, product, exchange, segment, quantity,
                             close_price))

    def _move(self, lose: bool | None = None) -> float:
        h = self.habits
        win = (self.rng.random() < h.win_chance) if lose is None else not lose
        return self.rng.uniform(*h.win_move) if win else -self.rng.uniform(*h.loss_move)

    def sitting(self, day: date, crude: bool) -> None:
        """One sitting, every habit applied the same way, whatever the day."""
        h, rng = self.habits, self.rng
        start, end = h.crude_evening if crude else h.nifty_morning
        clock = datetime.combine(day, start) + timedelta(minutes=rng.randint(0, 40))
        stop = datetime.combine(day, end)
        base = rng.choice(h.lots)
        kind = rng.choice(("CALL", "PUT"))
        losses = 0
        for _ in range(rng.randint(*h.trades_per_sitting)):
            if clock >= stop:
                break
            lots = min(h.max_lots, base + max(0, losses - h.up_size_after + 1))
            move = self._move()
            won = move > 0
            hold = timedelta(minutes=rng.randint(*(h.winner_hold_min if won else h.loser_hold_min)),
                             seconds=rng.randint(0, 59))
            if crude:
                premium = rng.uniform(80, 220)
                self._trip(entry=clock, exit_=clock + hold,
                           name=contract(CRUDE, crude_expiry(day), 50 * rng.randint(110, 130), kind),
                           exchange="MCX", segment="Commodity", quantity=lots * CRUDE_LOT,
                           open_price=crude_price(premium),
                           close_price=crude_price(premium * (1 + move)))
            else:
                premium = rng.uniform(60, 180)
                self._trip(entry=clock, exit_=clock + hold,
                           name=contract("NIFTY", nifty_expiry(day), 50 * rng.randint(480, 520), kind),
                           exchange="NSE", segment="Derivative", quantity=lots * NIFTY_LOT,
                           open_price=nifty_price(premium),
                           close_price=nifty_price(premium * (1 + move)))
            losses = 0 if won else losses + 1
            if not won and rng.random() < h.flip_after_loss:
                kind = "PUT" if kind == "CALL" else "CALL"
            gap = h.gap_after_win_min if won else h.gap_after_loss_min
            clock += hold + timedelta(minutes=rng.randint(*gap), seconds=rng.randint(0, 59))

    def etf(self, bought: date, sold: date) -> None:
        """One index ETF bought early and held to near the end (product DELIVERY)."""
        price = self.rng.uniform(260, 290)
        self._trip(entry=datetime.combine(bought, time(10, 12, self.rng.randint(0, 59))),
                   exit_=datetime.combine(sold, time(14, 41, self.rng.randint(0, 59))),
                   name=ETF, exchange="NSE", segment="Equity", quantity=self.habits.etf_units,
                   open_price=nifty_price(price),
                   close_price=nifty_price(price * (1 + self.rng.uniform(0.02, 0.12))),
                   product="DELIVERY")

    def crude_spread(self, day: date, at: time) -> None:
        """A bought call and a sold call one strike-step up: one position (Annex H)."""
        entry = datetime.combine(day, at)
        exit_ = entry + timedelta(minutes=self.rng.randint(25, 70))
        expiry, low = far_crude_expiry(day), 50 * self.rng.randint(115, 125)
        bought, sold = self.rng.uniform(120, 180), self.rng.uniform(60, 100)
        move = self._move(None)
        self._trip(entry=entry, exit_=exit_, name=contract(CRUDE, expiry, low, "CALL"),
                   exchange="MCX", segment="Commodity", quantity=CRUDE_LOT,
                   open_price=crude_price(bought), close_price=crude_price(bought * (1 + move)))
        self._trip(entry=entry + timedelta(seconds=self.rng.randint(5, 40)),
                   exit_=exit_ + timedelta(seconds=self.rng.randint(5, 40)),
                   name=contract(CRUDE, expiry, low + 100, "CALL"), exchange="MCX",
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
                   name=contract(CRUDE, expiry, 50 * self.rng.randint(118, 126), "CALL"),
                   exchange="MCX", segment="Commodity", quantity=CRUDE_LOT, product="MARGIN",
                   open_price=crude_price(premium),
                   close_price=crude_price(premium * (1 + self.rng.uniform(-0.3, 0.6))))


def build(seed: int = SEED) -> list[Row]:
    demo = Demo(seed)
    h, rng = demo.habits, demo.rng
    days = weekdays(FIRST_DAY, LAST_DAY)
    for day in days:
        if rng.random() < h.nifty_days:
            demo.sitting(day, crude=False)
        if rng.random() < h.crude_days:
            demo.sitting(day, crude=True)
    # Kept from TICKET-842, because the report talks about each; placed by the seed.
    demo.crude_spread(rng.choice(days[5:60]), time(13, 10))
    demo.sold_put(rng.choice(days[5:60]), time(13, 30))
    demo.held_call(rng.choice(days[10:55]), days_held=3)
    demo.etf(days[2], days[-3])
    return sorted(demo.rows, key=lambda r: (r.at, r.name, r.side), reverse=True)  # newest first


def render(seed: int = SEED) -> str:
    return "\n".join([HEADER, *(r.line() for r in build(seed))]) + "\n"


if __name__ == "__main__":
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT.name}: {len(build())} rows")
