"""Where blind replay's bars come from (TICKET-924).

ADR 008 serves every family from the existing Fyers connection, and the shared series
layer records each series' manifest. Production has no loader of bars into memory yet,
so this returns nothing, and the page says the bars aren't here rather than inventing
any. When the loader lands, it plugs in here and nothing else changes.
"""

from __future__ import annotations

from datetime import datetime

from services.production.mirror.prior_minute import MinuteBars


def series_for(underlyings: set[str]) -> dict[str, MinuteBars]:
    """One series per underlying the trader traded, for the ones we hold."""
    return {}


def candidates_for(series: dict[str, MinuteBars]) -> dict[str, list[datetime]]:
    """Every minute each series has a bar for, to draw random moments from."""
    return {u: sorted(getattr(s, "bars", {})) for u, s in series.items()}
