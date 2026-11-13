"""The published factor map (TICKET-921): what Scope looks at, and how far each has got.

It answers a mentor's first question, "what factors do you look at?", in one list:
**Family · Factor · When it's known · Status**, and for a signed-in trader with a record,
**In your file?**

**Derived from the code and the spec, not typed beside them.** Each factor names where
it lives: a check in the pre-registered framework's library (``framework_v1.yaml``), a
filter on the trade lists (``trade_list.FILTERS``), or a fact the report shows
(``scope_map.FACTS``). ``tests/unit/api/test_factor_map.py`` fails when any of those
gains an entry the map doesn't carry, and when the map names one that no longer exists,
so the map can't drift from what is really looked at.

**The status is the product's state, never a trader's result.** README rule 1: one
trader's results don't go on a published page. A status says whether Scope works the
factor out today, whether a tradebook carries it, whether it needs market bars, whether
only the trader can give it, or whether it is held by a ruling. No figure from anyone's
file is in this module or on the page, and the spec's own confidence tiers are never
printed.

**When it's known** uses the three labels every finding carries (the vocabulary the
``Finding`` type will hold): before the session, at the click, or only afterwards. A
factor known only afterwards describes; it can't become a rule.

Words here are new copy and wait for D9.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Known(str, Enum):
    """When the trader could have known it."""

    BEFORE = "Before the session"
    AT_CLICK = "At the click"
    ONLY_AFTER = "Only afterwards"


class Status(str, Enum):
    """Where the product stands on this factor. Never a trader's result."""

    WORKED_OUT = "Worked out"
    IN_YOUR_FILE = "In your file"          # a tradebook carries it; not worked out yet
    NEEDS_BARS = "Needs bars"              # needs the market's own prices
    NOT_IN_ANY_FILE = "Not in any file"    # the plan: only the trader can give it
    HELD = "Held"                          # paused by a ruling


STATUS_MEANS: dict[Status, str] = {
    Status.WORKED_OUT: "Scope works this out from your file today.",
    Status.IN_YOUR_FILE: "Your tradebook carries it. Scope doesn't work it out yet.",
    Status.NEEDS_BARS: "It needs the market's own prices, which a tradebook doesn't hold.",
    Status.NOT_IN_ANY_FILE: "Only you can give it, and only before the trade counts.",
    Status.HELD: "Paused by a decision, until there is reason to restart it.",
}


@dataclass(frozen=True)
class Factor:
    family: str
    name: str                 # in the trader's words, not the engine's key
    known: Known
    status: Status
    checks: tuple[str, ...] = ()    # framework library ids (the spec)
    filters: tuple[str, ...] = ()   # trade_list.FILTERS keys (the code)
    facts: tuple[str, ...] = ()     # scope_map.FACTS keys (the code)
    sources: tuple[str, ...] = field(default=())  # other code it reads, by dotted name
    needs_charges: bool = False     # in his file only when the file, or a statement, has them


F, K, S = Factor, Known, Status

FACTORS: tuple[Factor, ...] = (
    # Cost
    F("Cost", "Charges per round trip", K.BEFORE, S.WORKED_OUT,
      sources=("services.production.charges.record",), needs_charges=True),
    # Instrument
    F("Instrument", "Book", K.AT_CLICK, S.WORKED_OUT, filters=("book",)),
    F("Instrument", "Premium paid", K.AT_CLICK, S.WORKED_OUT, filters=("price",)),
    F("Instrument", "Days to expiry", K.AT_CLICK, S.WORKED_OUT, filters=("dte",)),
    F("Instrument", "Strike's distance from the market", K.AT_CLICK, S.NEEDS_BARS),
    # Clock
    F("Clock", "Hour you opened", K.AT_CLICK, S.WORKED_OUT, checks=("S1",),
      filters=("hour",), facts=("clock",)),
    F("Clock", "Weekday", K.AT_CLICK, S.IN_YOUR_FILE),
    F("Clock", "Month and year", K.ONLY_AFTER, S.WORKED_OUT, filters=("year",)),
    F("Clock", "Around a scheduled release", K.BEFORE, S.HELD, checks=("S10",)),
    # Sequence
    F("Sequence", "Trade number in the day", K.AT_CLICK, S.IN_YOUR_FILE, checks=("B5",)),
    F("Sequence", "Last trade's result", K.AT_CLICK, S.WORKED_OUT, checks=("B2",),
      facts=("down",)),
    F("Sequence", "Time since the last close", K.AT_CLICK, S.IN_YOUR_FILE, checks=("B1",)),
    F("Sequence", "The day so far", K.AT_CLICK, S.IN_YOUR_FILE, checks=("B12",)),
    F("Sequence", "Same strike again", K.AT_CLICK, S.IN_YOUR_FILE),
    F("Sequence", "Losing runs", K.ONLY_AFTER, S.WORKED_OUT, facts=("run",)),
    F("Sequence", "Busiest day", K.ONLY_AFTER, S.WORKED_OUT, facts=("busiest",)),
    # Size
    F("Size", "Lots", K.AT_CLICK, S.WORKED_OUT, checks=("R1",)),
    F("Size", "Change from the last trade", K.AT_CLICK, S.IN_YOUR_FILE, checks=("R2",)),
    F("Size", "Adding to a losing position", K.AT_CLICK, S.IN_YOUR_FILE, checks=("R11",)),
    F("Size", "Risk against your number", K.BEFORE, S.WORKED_OUT, facts=("risk",)),
    F("Size", "Size when the market is moving", K.AT_CLICK, S.NEEDS_BARS, checks=("R8",)),
    # Holding and exits
    F("Holding and exits", "How long you hold", K.ONLY_AFTER, S.WORKED_OUT, checks=("E5",)),
    F("Holding and exits", "Held past the day", K.AT_CLICK, S.WORKED_OUT, checks=("S6",)),
    F("Holding and exits", "How much of a move you kept", K.ONLY_AFTER, S.NEEDS_BARS,
      checks=("E2",)),
    F("Holding and exits", "Losses that grew late", K.ONLY_AFTER, S.NEEDS_BARS,
      checks=("E4p",)),
    # Results
    F("Results", "Worst days", K.ONLY_AFTER, S.WORKED_OUT, facts=("worst-days",)),
    F("Results", "Best and worst trades", K.ONLY_AFTER, S.WORKED_OUT, facts=("money",)),
    F("Results", "Wins, losses and break-even", K.ONLY_AFTER, S.WORKED_OUT, filters=("result",),
      facts=("math",)),
    F("Results", "Your result over time", K.ONLY_AFTER, S.IN_YOUR_FILE,
      checks=("S11", "S12")),
    F("Results", "Where your results come from, cell by cell", K.ONLY_AFTER,
      S.IN_YOUR_FILE, checks=("C1",)),
    # Market before entry
    F("Market before entry", "The minute before you bought", K.AT_CLICK, S.NEEDS_BARS,
      sources=("services.production.mirror.prior_minute",)),
    F("Market before entry", "The last 15 minutes", K.AT_CLICK, S.NEEDS_BARS),
    F("Market before entry", "The market's regime", K.AT_CLICK, S.NEEDS_BARS,
      checks=("S5",)),
    # Plan
    F("Plan", "Your stop", K.BEFORE, S.NOT_IN_ANY_FILE, checks=("R7",)),
    F("Plan", "Your target", K.BEFORE, S.NOT_IN_ANY_FILE),
    F("Plan", "Your reason for the trade", K.BEFORE, S.NOT_IN_ANY_FILE),
    F("Plan", "Your limit for the day", K.BEFORE, S.NOT_IN_ANY_FILE),
    # Market state
    F("Market state", "The engine's read of the market", K.AT_CLICK, S.HELD),
)

NOT_FACTORS: dict[str, str] = {
    "unread": "what Scope could and couldn't read from the file, not a factor",
    "not-told": "the report's limits, not a factor",
}
"""Report facts that aren't factors, each with why. A new fact must be one or the other."""

FAMILIES: tuple[str, ...] = tuple(dict.fromkeys(f.family for f in FACTORS))


class InFile(str, Enum):
    """Whether this trader's own tradebook let Scope look at the factor."""

    YES = "Yes"
    NOT_ENOUGH = "Not enough yet"
    NO = "Not in your file"
    NEEDS_BARS = "Needs bars"
    ONLY_YOU = "Only you can give it"
    HELD = "Held"


def in_file(factor: Factor, *, enough: frozenset[str], short: frozenset[str],
            fact_states: dict[str, str | None], filters_seen: frozenset[str],
            has_charges: bool) -> InFile:
    """For one trader: could Scope look at this factor in his file?

    A factor Scope looks at but couldn't for him stays on the list and says why. Read from
    what the report already decided: the eligibility checks (``enough``, ``short``), each
    fact's state (None when it is shown), and which trade-list filters his trades fill.
    """
    if factor.status is Status.NOT_IN_ANY_FILE:
        return InFile.ONLY_YOU
    if factor.status is Status.NEEDS_BARS:
        return InFile.NEEDS_BARS
    if factor.status is Status.HELD:
        return InFile.HELD
    if factor.needs_charges:
        return InFile.YES if has_charges else InFile.NO
    if (any(k in fact_states and not fact_states[k] for k in factor.facts)
            or any(k in filters_seen for k in factor.filters)
            or any(c in enough for c in factor.checks)):
        return InFile.YES
    if any(c in short for c in factor.checks) or any(
            fact_states.get(k) == "not-enough" for k in factor.facts):
        return InFile.NOT_ENOUGH
    if factor.checks or factor.facts or factor.filters:
        return InFile.NO
    return InFile.YES  # read from every trade's own time and contract
