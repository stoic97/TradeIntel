"""Read a Mirror page as words, with every figure taken out.

The handoff fixes the Mirror's wording word for word and lets only the figures vary.
So the comparison has to keep every word and ignore every number, however a number
happens to be formatted: today's templates print -12,345; the Scope prints −₹12,345
with a true minus and Indian digit grouping. Both read [N] here.

Pure functions over HTML text, standard library only, so they can be tested without
the app.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

PLACEHOLDER = "[N]"

# A figure: an optional sign (hyphen, true minus, plus), an optional rupee sign, then
# digits that may carry grouping commas, a decimal point or a clock colon, then an
# optional % or ×. It starts only where no letter or digit sits just before it, so the
# hyphens in 2026-03-04 are not minus signs (it reads [N]-[N]-[N] and is dropped with
# the other figure-only cells) and an identifier such as v1 is left as it is.
FIGURE = re.compile(r"(?<!\w)[-−+]?₹?\d(?:[\d,.:]*\d)?[%×]?")

# The elements a Mirror sentence, heading or table label lives in.
BLOCKS = {"p", "h1", "h2", "h3", "th", "td", "li"}

# Controls, not wording: the drawer buttons become the trade list on a fact page.
SKIPPED = {"button", "script", "style"}


def figures_out(text: str) -> str:
    """The text with each figure replaced by [N] and whitespace collapsed."""
    return " ".join(FIGURE.sub(PLACEHOLDER, text).split())


def is_figure_only(text: str) -> bool:
    """True when nothing but figures and punctuation is left: a data cell, not wording."""
    return not re.search(r"[A-Za-z]", text.replace(PLACEHOLDER, ""))


class _Sections(HTMLParser):
    """Collects the text of each block element, grouped by <section>."""

    def __init__(self) -> None:
        super().__init__()
        self.sections: list[list[str]] = []
        self._in_section = False
        self._block: list[str] | None = None
        self._block_depth = 0
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "section":
            self.sections.append([])
            self._in_section = True
        elif tag in SKIPPED:
            self._skip_depth += 1
        elif self._in_section and tag in BLOCKS:
            if self._block is None:
                self._block = []
            self._block_depth += 1

    def handle_endtag(self, tag):
        if tag == "section":
            self._in_section = False
        elif tag in SKIPPED:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif self._block is not None and tag in BLOCKS:
            self._block_depth -= 1
            if self._block_depth == 0:
                text = figures_out("".join(self._block))
                if text and not is_figure_only(text):
                    self.sections[-1].append(text)
                self._block = None

    def handle_data(self, data):
        if self._block is not None and not self._skip_depth:
            self._block.append(data)


def wording(html: str) -> list[dict]:
    """Each <section> with words in it, as its position and its blocks, in page order.

    Keyed by position because the Mirror's order is fixed (PRD section 6) and two of
    its sections have no heading. Where a section has one, it is the first block.
    """
    parser = _Sections()
    parser.feed(html)
    out = []
    for i, blocks in enumerate(parser.sections):
        if not blocks:
            continue
        out.append({"key": f"section-{i}", "blocks": blocks})
    return out
