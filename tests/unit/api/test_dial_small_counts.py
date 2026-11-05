"""A single-digit count on a chapter dial stays with its unit [TICKET-853].

A slice breaks a figure that won't fit on one line, so "3 trades" could draw a lone 3 over
"trades", which reads as a serial. Trades here are synthetic, with counts small on purpose.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal
from html import unescape

import pytest

from services.production.api import dial as D
from services.production.api import scope_facts as SF
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_scope_chapters import IMP, TRIPS, chapter_page, readable


def trip(i: int, day: str, net: int, minute: int) -> mx.Trip:
    entry = datetime.fromisoformat(f"2026-{day}T09:15:00+05:30") + timedelta(minutes=minute)
    leave = entry + timedelta(minutes=5)
    return mx.Trip(f"T{i}", "WIDGET", entry.date().isoformat(), entry, leave, 300, Decimal(net), 1,
                   s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True)


def small_file() -> list[mx.Trip]:
    """Ten days. The first runs three losers then a winner, so the run is 3 and two trades
    follow two straight losses. The rest are one winner and one loser."""
    trips, n = [], 0
    for d in range(1, 11):
        for k, net in enumerate([-100, -100, -100, 50] if d == 1 else [50, -20]):
            trips.append(trip(n, f"01-{d:02d}", net, k * 10))
            n += 1
    return trips


def slices(view: dict) -> dict[str, list[str]]:
    out = {}
    for block in re.findall(r'<a class="scope__slice.*?</a>', str(D.scope_dial(view)), flags=re.DOTALL):
        name = unescape(re.search(r'aria-label="([^"]*?)\.?"', block).group(1))
        texts = re.findall(r'<text class="scope__[a-z-]+[^"]*"[^>]*>(.*?)</text>', block, flags=re.DOTALL)
        out[name] = [unescape(re.sub(r"<[^>]+>", " ", t)).replace(chr(0xA0), " ").strip() for t in texts]
    return out


FIGS = SF.facts(SF.record_context(small_file()), IMP)


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_no_slice_draws_a_lone_digit(n):
    for name, texts in slices(SF.chapter_view(n, FIGS)).items():
        assert not [w for w in texts if re.fullmatch(r"\d", w)], (name, texts)


def test_the_run_keeps_its_digit_with_its_unit():
    assert "3 trades" in slices(SF.chapter_view(2, FIGS))["Longest losing run"]


def test_the_trades_after_two_losses_keep_theirs():
    assert "2 trades" in slices(SF.chapter_view(3, FIGS))["After two straight losses"]


def test_a_two_digit_count_can_still_stack():
    """Only a lone digit is held together: a wider figure still breaks to fit its slice."""
    figs = SF.facts(SF.record_context(TRIPS), IMP)
    assert slices(SF.chapter_view(2, figs))["Longest losing run"] == ["10", "trades"]


@pytest.mark.parametrize(("figure", "held"), [
    ("3 trades", True), ("8 of 80 rows read", True), ("10 trades", False), ("Best trade +₹20", False),
    ("5 days: −₹130", True), ("15.8%", False), ("", False),
])
def test_the_rule_holds_only_a_leading_single_digit(figure, held):
    got = SF.keep_digit_with_its_unit(figure)
    assert (chr(0xA0) in got) is held
    assert got.replace(chr(0xA0), " ") == figure


def test_the_figure_itself_doesnt_change():
    """The cards read the fact's own figure, so only the dial's copy is joined."""
    assert FIGS["run"]["figure"] == "3 trades"
    assert chr(0xA0) not in readable(chapter_page(2, small_file())).split("Longest losing run")[1][:40]
