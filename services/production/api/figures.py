"""A figure is a value and the noun it belongs to. One type, for every page a trader reads.

"Three uncapped" passed a test that every figure has a label next to it, because "uncapped"
is a label. A structural test can catch a thing that is missing and never a thing that means
nothing, so the rule is in the type: a figure cannot be made without a noun.

Today the noun is declared where the figure is written, and the words around it on the page
are still the page's own, so a figure writes exactly what it wrote before: its value through
the same filter. That is what lets every page move to it at once with nothing on screen
changing. A page that says the noun takes it from here, and when a figure's wording has one
place to change, there is one place to change it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class NoNoun(ValueError):
    """A figure with nothing for its value to belong to."""


class Written(str):
    """A figure's value as a filter wrote it: how a page's text is told from a bare number."""


@dataclass(frozen=True)
class Figure:
    value: Any
    noun: str
    of: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.noun, str) or not self.noun.strip():
            raise NoNoun(f"a figure needs a noun: {self.value!r} has {self.noun!r}")

    def __str__(self) -> str:
        return str(self.value)

    @property
    def with_noun(self) -> str:
        """As a sentence says it: "8 trades"."""
        return f"{self.value} {self.noun}"


def through_figure(write):
    """A filter that takes a Figure, and writes its value as the filter always wrote it."""

    def written(value, *args, **kwargs):
        if isinstance(value, Figure):
            return Written(write(value.value, *args, **kwargs))
        return write(value, *args, **kwargs)

    written.__name__ = write.__name__
    written.__doc__ = write.__doc__
    return written
