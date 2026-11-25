"""TICKET-1032 review (24 Nov): a thin year between two counted years breaks the lines instead of
being bridged; the first and last year labels stay inside the drawing; the chart names its two
lines in the ruled words, "you win" and "break even at".

Made-up trades, worked by hand:
  NIFTY 2024  16 wins of +300, 24 losses of -150: win 40, break-even 33  (counted)
  NIFTY 2025  5 wins of +100, 5 losses of -100: 10 trades, too few
  NIFTY 2026  12 wins of +200, 28 losses of -200: win 30, break-even 50  (counted)
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from services.production.api import wins_gap
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s

IST = ZoneInfo("Asia/Kolkata")


def trades(symbol: str, year: int, wins: int, win_net: int, losses: int, loss_net: int) -> list:
    """wins at +win_net and losses at -loss_net, each opened and closed the same day."""
    out = []
    for i, net in enumerate([win_net] * wins + [-loss_net] * losses):
        entry = datetime(year, 3, 2, 10, 0, tzinfo=IST) + timedelta(days=i)
        out.append(mx.Trip(trip_id=f"r{symbol}{year}{i}", symbol=symbol, trading_day=entry.date().isoformat(),
                           entry_ts=entry, exit_ts=entry + timedelta(minutes=10), holding_seconds=600,
                           net=Decimal(net), lots=1, risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID,
                           is_option=True))
    return out


RECORD = (trades("NIFTY", 2024, 16, 300, 24, 150) + trades("NIFTY", 2025, 5, 100, 5, 100)
          + trades("NIFTY", 2026, 12, 200, 28, 200))


def svg() -> str:
    return str(wins_gap.view(mx.math_by_book(RECORD))["years"][0]["svg"])


def test_a_thin_year_between_two_counted_years_is_not_bridged_by_a_line():
    s = svg()
    # two counted years either side of a thin one: no line joins them, only their dots
    assert 'class="wg-you"' not in s and 'class="wg-even"' not in s and 'class="wg-band"' not in s
    assert s.count('class="wg-you-dot"') == 2


def test_the_first_and_last_year_labels_stay_inside_the_drawing():
    labels = re.findall(r'<text[^>]*class="ch-axis ch-axis--x"[^>]*>', svg())
    assert 'text-anchor="start"' in labels[0] and 'text-anchor="end"' in labels[-1]


def test_the_chart_names_its_lines_in_the_ruled_words():
    page = Path("services/production/api/templates/scope/_wins_gap.html").read_text(encoding="utf-8")
    year_caption = page.split("wg-years__title", 1)[1]
    assert "you win" in year_caption and "break even at" in year_caption
