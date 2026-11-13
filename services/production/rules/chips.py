"""The chips a rule is built from (TICKET-922). Every input is a tap; there is no text box.

**These lists wait for the founder and D9.** The ticket sets them there, not in a
template, so they live here, in one place, and every screen and test reads them. Where
the pre-registered framework already names a rule (``framework_v1.yaml`` ``moves``: two
losses then done for the day, a cap on size), the chips include its values; nothing is
ranked, marked as better, or chosen in advance. A screen shows them in this order, all
alike.

Rupee limits are written in thousands so no large figure sits in code.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleFactor:
    key: str
    label: str           # what the chip row is called
    phrase: str          # the rule in words; {v} is the chip's value as shown
    values: tuple[int, ...]
    unit: str = ""

    noun: str = ""       # what a chip's number counts, said on the chip
    one: str = ""        # the noun for 1

    def shown(self, value: int) -> str:
        if self.key == "day_down":
            return f"₹{value},000"
        if self.key == "last_hour":
            return f"{value:02d}:00"
        return str(value)

    def chip(self, value: int) -> str:
        """What the button says: the value with what it counts, never a bare number."""
        if not self.noun:
            return self.shown(value)
        return f"{value} {self.one if value == 1 else self.noun}"

    def words(self, value: int) -> str:
        return self.phrase.format(v=self.shown(value))


FACTORS: dict[str, RuleFactor] = {f.key: f for f in (
    RuleFactor("day_down", "Today's limit", "Stop for the day once it is down {v}",
               (1, 2, 3, 5, 10, 20)),
    RuleFactor("most_trades", "Most trades", "At most {v} trades in a day",
               (1, 2, 3, 4, 5, 6, 8, 10), noun="trades", one="trade"),
    RuleFactor("losses_in_a_row", "What would make me stop",
               "Stop for the day after {v} losses in a row", (1, 2, 3), noun="losses in a row",
               one="loss"),
    RuleFactor("last_hour", "Hour", "No new trade from {v}", tuple(range(10, 24))),
    RuleFactor("most_lots", "Size", "At most {v} lots a trade", (1, 2, 3, 4, 5), noun="lots",
               one="lot"),
)}

BEFORE_SESSION: tuple[str, ...] = ("day_down", "most_trades", "losses_in_a_row")
"""Screen A, in this order: today's limit, most trades, what would make me stop."""

REASONS: tuple[str, ...] = ("My setup", "Following a move", "Against a move", "News", "Other")
"""Screen B's reasons, as chips. Neutral words: none is a better reason than another."""

OTHER_BOOK = "Other"

SCREENS = ("before_session", "standing")
