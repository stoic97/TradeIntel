"""Every finding carries two labels, and the rule is in the type (TICKET-917).

A mentor's challenge to the trader: in hindsight everything looks good or bad; real time is
the problem. So a finding says when the trader could have known it, and how far it has got,
and the rule goes where ``Figure`` put its own: a finding cannot be made without both
labels, the way a figure cannot be made without a noun (``figures.py``).

* ``known``: ``BEFORE`` the session, ``AT_CLICK``, or ``ONLY_AFTER``.
* ``rung``: ``SEEN`` in the file, ``WOULD_YOU_HAVE_KNOWN`` (it still holds when picked using
  only earlier trades), or ``RUN_FORWARD`` (kept or broken, trade by trade).

**Where the labels are set.** One table here, ``LABELS``, one row per fact the report
decides (``scope_map.FIGURES``), read once where the facts are decided
(``scope_facts.facts``). A fact with no row stops there, with ``Unlabelled``, before any
page draws it. The pages format and compute nothing, so no label logic is in a route or a
template; a template reads a label only through the ``known`` and ``rung`` filters, which
refuse anything that is not a ``Finding``.

**Every rung is ``SEEN`` today.** Nothing the report shows has been picked using only
earlier trades, or run forward, so nothing is labelled higher than it has reached.

The research spec's own tiers (``Established``, ``Likely``, ``Exploratory``) are internal
language and are not these labels; nothing here maps one onto the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Unlabelled(ValueError):
    """A finding missing a label, or carrying something that isn't one."""


class Known(str, Enum):
    """When the trader could have known it."""

    BEFORE = "BEFORE"
    AT_CLICK = "AT_CLICK"
    ONLY_AFTER = "ONLY_AFTER"


class Rung(str, Enum):
    """How far it has got."""

    SEEN = "SEEN"
    WOULD_YOU_HAVE_KNOWN = "WOULD_YOU_HAVE_KNOWN"
    RUN_FORWARD = "RUN_FORWARD"


@dataclass(frozen=True)
class Finding:
    key: str
    known: Known
    rung: Rung

    def __post_init__(self) -> None:
        if not isinstance(self.known, Known) or not isinstance(self.rung, Rung):
            raise Unlabelled(
                f"a finding needs both labels: {self.key!r} has known={self.known!r}, "
                f"rung={self.rung!r}")


K, R = Known, Rung

LABELS: dict[str, Finding] = {f.key: f for f in (
    Finding("hidden", K.ONLY_AFTER, R.SEEN),       # plain counts over the record
    Finding("worst-days", K.ONLY_AFTER, R.SEEN),   # which days were worst: known after them
    Finding("share", K.ONLY_AFTER, R.SEEN),
    Finding("money", K.ONLY_AFTER, R.SEEN),        # best and worst trades, by result
    Finding("math", K.ONLY_AFTER, R.SEEN),         # win rate and break-even over the record
    Finding("run", K.ONLY_AFTER, R.SEEN),          # a losing run, known once it has run
    Finding("clock", K.AT_CLICK, R.SEEN),          # the hour he opens in
    Finding("down", K.AT_CLICK, R.SEEN),           # the last two trades' results
    Finding("back-in", K.AT_CLICK, R.SEEN),        # the last trade's result, and the minutes since
    Finding("same-way", K.AT_CLICK, R.SEEN),       # the last trade's result, and its direction
    Finding("next-day", K.BEFORE, R.SEEN),         # yesterday's result, known before the session
    Finding("busiest", K.ONLY_AFTER, R.SEEN),      # the busiest day, known once it is over
    Finding("unread", K.ONLY_AFTER, R.SEEN),       # what the file held, known on reading it
    Finding("risk", K.AT_CLICK, R.SEEN),           # a trade's size against his number
    Finding("not-told", K.ONLY_AFTER, R.SEEN),
)}
"""One row per fact the report decides. A new fact without a row stops in scope_facts."""


FIGURE_LABELS: dict[str, Finding] = {f.key: f for f in (
    Finding("hidden.record", K.ONLY_AFTER, R.SEEN),  # a state's trades over the whole record
    Finding("hidden.then", K.AT_CLICK, R.SEEN),      # chosen at the click from earlier trades
)}
"""A fact's own figures, where its page shows more than one (TICKET-919). Rung SEEN until
TICKET-909's bar: a figure chosen from earlier trades is not yet a finding that held."""


def of_figure(key: str) -> Finding:
    """The labelled finding for one of a fact's figures, or ``Unlabelled`` if it has none."""
    finding = FIGURE_LABELS.get(key)
    if not isinstance(finding, Finding):
        raise Unlabelled(f"the figure {key!r} has no labels: add it to findings.FIGURE_LABELS")
    return finding


def of(key: str) -> Finding:
    """The labelled finding for a fact, or ``Unlabelled`` if it has none."""
    finding = LABELS.get(key)
    if not isinstance(finding, Finding):
        raise Unlabelled(f"the fact {key!r} has no labels: add it to findings.LABELS")
    return finding


def _labelled(value) -> Finding:
    if not isinstance(value, Finding):
        raise Unlabelled(f"a template asked for a label of {value!r}, which is not a Finding")
    return value


def known(value) -> str:
    return _labelled(value).known.value


def rung(value) -> str:
    return _labelled(value).rung.value


@dataclass(frozen=True)
class Step:
    """One rung of the ladder as a page draws it: its words, and whether it is reached."""

    key: str
    name: str
    says: str
    reached: bool
    state: str


NOT_YET_REACHED = "Not reached"

LADDER: tuple[tuple[str, Rung | None, str, str], ...] = (
    ("SEEN", Rung.SEEN, "Seen", "it appears in your file."),
    ("WOULD_YOU_HAVE_KNOWN", Rung.WOULD_YOU_HAVE_KNOWN, "Would you have known?",
     "it still holds when picked using only earlier trades."),
    ("SET_AS_YOUR_RULE", None, "Set as a rule",
     "you set it as a rule, by tapping, dated, before it was tested on anything new."),
    ("RUN_FORWARD", Rung.RUN_FORWARD, "Run forward",
     "followed or broken, trade by trade. Charges and trade count first."),
    ("VERDICT", None, "Verdict",
     ('only at a sample size stated at the start, and "not enough trades" is a proper '
      "answer.")),
)
"""The ladder from a finding to a rule, in the trader's words (TICKET-925, ruled 13 Nov).

Five rungs in order. ``Rung`` labels three of them (TICKET-917); no label reaches the other
two yet, so every page draws them as not yet reached. The words are here and nowhere else:
a template reads them through the ``ladder`` filter and writes none of its own."""


def ladder(value) -> tuple[Step, ...]:
    """All five rungs for a finding: those up to its label reached, the rest not yet."""
    finding = _labelled(value)
    top = next(i for i, row in enumerate(LADDER) if row[1] is finding.rung)
    return tuple(
        Step(key, name, says, i <= top, "" if i <= top else NOT_YET_REACHED)
        for i, (key, _label, name, says) in enumerate(LADDER))


def register(env) -> None:
    """The filters a template reads the labels and the ladder through."""
    env.filters.update(known=known, rung=rung, ladder=ladder)
    env.globals["ladder_words"] = tuple((name, says) for _key, _label, name, says in LADDER)
