"""Read a Mirror page as words, with every figure taken out.

The handoff fixes the Mirror's wording word for word and lets only the figures vary.
So the comparison has to keep every word and ignore every number, however a number
happens to be formatted: today's templates print -12,345; the Scope prints −₹12,345
with a true minus and Indian digit grouping. Both read [N] here.

Pure functions over HTML text, standard library only, so they can be tested without
the app. The long page is gone now; the frozen reference it left, with the drawer
captions and the one sentence the fixture never reaches, is the Mirror's wording, and
every Scope page is read against it.
"""

from __future__ import annotations

import json
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

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


# ---------- The Mirror's words, after its page has gone ----------

REFERENCE = Path("tests/fixtures/mirror_wording/mirror_v1.json")

DRAWER_CAPTIONS = (
    "The five days, and every trade on them.",
    "Your best five and worst five, by result.",
    "Every trade opened after two that had already closed at a loss.",
    "How long each trade was open, by how it ended.",
    "Every trade, by the hour you opened it.",
)
"""The long page's drawer captions (routes_mirror.DRAWERS), taken word for word when
the drawers became fact pages. Wording too (handoff 6), so kept here with the rest."""

SHARE_NOT_A_PERCENTAGE = (
    "Those five days came to [N]. Your result for the whole period was [N]. "
    "The other [N] days were net [N]."
)
"""The sentence the Mirror printed when the share is not a percentage (Appendix A: a
positive total, or worst days larger than the whole). The 40-trip fixture never
reaches it, so it is not in the frozen reference; it was written from the template,
figures out, and test_wording_reference.py held the template to it while it lived."""


def sentences(text: str) -> list[str]:
    """A block of wording split into its sentences; a label is one sentence."""
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def mirror_sentences() -> list[str]:
    """Every sentence, heading and label the Mirror said, figures out, in page order."""
    frozen = json.loads(REFERENCE.read_text())["sections"]
    out = [s for section in frozen for block in section["blocks"] for s in sentences(block)]
    out += [s for caption in DRAWER_CAPTIONS for s in sentences(caption)]
    out += sentences(SHARE_NOT_A_PERCENTAGE)
    return list(dict.fromkeys(out))


INLINE = r"span|strong|em|a|b|i|br|sup|sub"
DATE = re.compile(r"\[N\]-\[N\]-\[N\]|\[N\] (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b")


def page_text(html: str) -> str:
    """Everything a reader sees on a page, figures out, as one line of words.

    Inline tags join their text to the words around them; every other tag is a
    break. A date reads [DATE] whichever way it is written - the long page printed
    2026-09-07, the Scope prints 07 Sep as the kit does - so a sentence is not a
    different sentence because a date's writing changed.
    """
    html = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.DOTALL)
    html = re.sub(rf"</?(?:{INLINE})\b[^>]*>", "", html)
    html = re.sub(r"<[^>]+>", " ", html)
    return DATE.sub("[DATE]", figures_out(unescape(html)))


def said_as_written(sentence: str) -> str:
    """A Mirror sentence ready to look for in page_text."""
    return DATE.sub("[DATE]", sentence)
