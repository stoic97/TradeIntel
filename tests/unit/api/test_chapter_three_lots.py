"""Chapter 3 compares size in lots: options only, to one decimal [TICKET-798].

One day, worked by hand. Two losses at 1 and 2 lots, then an option at 3 lots: that one
is after two straight losses. Later that day, an option at 2 lots with a win just before
it, and 100 shares. After two losses: 3.0. Every other option: (1 + 2 + 2) / 3 = 1.667,
or 35.333 if the shares were counted.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from services.production.api import scope_facts as SF
from services.production.mirror import metrics as mx
from tests.unit.api.test_scope_chapters import chapter_page, trips_from


def one_day() -> list[mx.Trip]:
    start = datetime.fromisoformat("2026-09-01T09:15:00+05:30")
    rows = [(-100, 1, True), (-100, 2, True), (500, 3, True), (100, 2, True), (0, 100, False)]
    out = []
    for i, (t, (net, lots, option)) in enumerate(zip(trips_from([1] * 5), rows, strict=True)):
        entry = start + timedelta(minutes=20 * i)
        out.append(replace(t, trading_day="2026-09-01", entry_ts=entry,
                           exit_ts=entry + timedelta(minutes=10), net=mx.Decimal(net),
                           lots=lots, is_option=option))
    return out


def test_the_comparison_reads_options_only():
    ctx = SF.record_context(one_day())
    assert (str(ctx["after_lots"].mean), str(ctx["rest_lots"].mean)) == ("3", "1.667")


def test_average_lots_is_shown_to_one_decimal():
    html = chapter_page(3, one_day())
    assert '<td class="table__num">3.0</td></tr>' in html
    assert '<td class="table__num">1.7</td></tr>' in html
    assert "1.667" not in html


def test_a_side_with_no_option_trade_shows_a_dash():
    """No trade came after two straight losses here."""
    html = chapter_page(3, trips_from([100, 200, 300, 50]))
    assert '<td class="table__num">—</td></tr>' in html
    assert "None" not in html
