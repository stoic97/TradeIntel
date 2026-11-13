"""The weekdays an exchange was shut, read from its own daily bars (TICKET-895).

``exchange_closures.yaml`` is written by ``scripts/build_exchange_closures.py`` through the
Fyers connection. Dates only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from functools import cache
from pathlib import Path

import yaml

CLOSURES = Path(__file__).with_name("exchange_closures.yaml")


@dataclass(frozen=True)
class Closures:
    closed: frozenset[date]
    through: date

    def trading_day_on_or_before(self, day: date) -> date:
        """``day`` if the exchange traded then, else the trading day before it.

        A day after ``through`` is not known here and comes back unmoved.
        """
        if day > self.through:
            return day
        while day.weekday() >= 5 or day in self.closed:
            day -= timedelta(days=1)
        return day


@cache
def load(path: Path = CLOSURES) -> dict[str, Closures]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    through = raw["through"] if isinstance(raw["through"], date) else date.fromisoformat(raw["through"])
    return {exchange: Closures(frozenset(entry["closed"]), through)
            for exchange, entry in raw["exchanges"].items()}
