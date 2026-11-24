"""The chance line's one way onto a page (TICKET-919, gate 2).

"Can't be told apart from chance." is a verdict, so it is written only where a comparison was
run. A template reads it through the ``inside`` filter, which takes a ``ChanceBand`` from
services/shared/conditions/leave_out.py and nothing else: no band, no line; anything that is
not a band stops the page, the way findings refuses an unlabelled finding.
"""

from __future__ import annotations

from services.shared.conditions.leave_out import ChanceBand


class NoComparison(ValueError):
    """Something other than a band was asked whether a figure sits inside it."""


def inside(value) -> bool:
    """Whether the chance line may be written: only a band can say so."""
    if value is None:
        return False
    if not isinstance(value, ChanceBand):
        raise NoComparison(f"the chance line needs the band it rests on, not {value!r}")
    if (value.size == 0 or value.size >= value.pool_size
            or value.band[0] == value.band[1]):
        # The only set of its size was compared with nothing (review, 18 and 24 Nov); so
        # was a figure whose band is one value (founder, 24 Nov, 919 Q1: b).
        return False
    return value.inside


def register(env) -> None:
    """The one filter a template reads the chance line through."""
    env.filters.update(inside=inside)
