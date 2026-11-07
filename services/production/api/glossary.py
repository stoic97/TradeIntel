"""The words a trader reads, in one place a test can hold them to.

Each entry is a word, whether it is in use or retired, and the word that replaced it. A word
is retired by the page that stopped using it, so the list starts with the dial and only ever
grows, and a retired word can't come back on a page that has given it up. `where` says which
pages have, because a word can be gone from the dial and still live copy elsewhere; with no
`where`, it is gone from every page. test_retired_words holds rendered pages to this list.

Adding a word is one line, in the commit that rewords its pages.
"""

from __future__ import annotations

from dataclasses import dataclass

IN_USE, RETIRED = "in use", "retired"
DIAL = "dial"
MONEY_PAGES = "the money pages"


@dataclass(frozen=True)
class Entry:
    word: str
    status: str
    replaced_by: str | None = None
    where: str | None = None


GLOSSARY: tuple[Entry, ...] = (
    Entry("trade", IN_USE),
    Entry("trades", IN_USE),
    Entry("day", IN_USE),
    Entry("days", IN_USE),
    Entry("loss", IN_USE),
    Entry("losses", IN_USE),
    Entry("rows", IN_USE),
    Entry("hour", IN_USE),
    Entry("number", IN_USE),
    Entry("money", IN_USE),
    Entry("things", IN_USE),
    Entry("items", IN_USE),
    Entry("row", IN_USE),
    Entry("strike", RETIRED, "N of 100 trades made money", DIAL),
    Entry("uncapped", RETIRED, "trades we could not size", DIAL),
    Entry("of losses", RETIRED, "lost N% of all you lost", DIAL),
    Entry("past it", RETIRED, "past your number", DIAL),
    Entry("Net (gross)", RETIRED, "Result"),
    Entry("strike rate", RETIRED, "N of 100 trades made money, or win rate"),
    Entry("qualified", RETIRED, "after two had closed"),
    Entry("qualifying", RETIRED, "after two had closed"),
    Entry("the math", RETIRED, "Your wins and losses"),
)


def nouns() -> frozenset[str]:
    return frozenset(e.word for e in GLOSSARY if e.status == IN_USE)


def retired(where: str) -> tuple[Entry, ...]:
    return tuple(e for e in GLOSSARY if e.status == RETIRED and e.where == where)
