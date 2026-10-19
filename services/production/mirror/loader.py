"""Load a trader's trips out of the database and into the metric functions' shape.

The metrics know nothing about SQLAlchemy and the database knows nothing about
Appendix A. This is the one place the two meet.

Trips come from the trader's **current** import versions only: a superseded import
is history, not his record, and showing both would double-count a re-upload.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.production.ctr.profiles import registry as profiles
from services.production.db import models as m
from services.production.mirror.metrics import Trip

PROFILE_DIR = Path(__file__).resolve().parents[1] / "ctr" / "profiles"


def current_import(sess: Session, trader: m.Trader) -> m.Import | None:
    """The most recent import that actually has trips.

    Asks for the trips rather than trusting the ``trips_reconstructed`` counter on
    the import row: the counter is a convenience for the review page, and a figure
    the trader reads should never depend on two things agreeing. A rejected import
    has no trips and is skipped by the same condition.
    """
    return sess.scalars(
        select(m.Import)
        .join(m.Trip, m.Trip.import_id == m.Import.id)
        .where(m.Import.trader_id == trader.id)
        .order_by(m.Import.id.desc())
        .limit(1)
    ).first()


def load_for(sess: Session, trader: m.Trader) -> tuple[list[Trip], m.Import | None]:
    """His trips and the import that produced them, for the lineage stamp."""
    imp = current_import(sess, trader)
    if imp is None:
        return [], None
    rows = sess.scalars(
        select(m.Trip).where(m.Trip.import_id == imp.id).order_by(m.Trip.entry_ts)
    ).all()

    # Timestamps are stored in UTC, which is right: a stored instant must be
    # unambiguous (ctr_v1 section 4.3). But every figure a trader reads is about HIS
    # day -- the hour he opened a trade, the day it belongs to -- so they are
    # converted here, once, as the trips enter the metric layer. Converting later,
    # in a template, would let the hour buckets and the displayed times disagree:
    # that is exactly how the clock section first reported hours 03 to 06 for a day
    # that ran 09 to 12 (TD-026).
    profile_map = profiles.load_all(PROFILE_DIR)

    def zone_for(row: m.Trip):
        """The instrument's own timezone. A missing profile is refused, not guessed.

        Falling back to UTC here would be the silent default PRD section 9 forbids,
        wearing different clothes: every time on the page would be wrong by the
        instrument's offset and nothing would say so. The import already records
        instruments without a profile; this makes the Mirror refuse to guess.
        """
        profile = profile_map.get((row.exchange, row.symbol))
        if profile is None:
            raise profiles.UnknownInstrument(
                f"no instrument profile for {row.exchange}:{row.symbol} -- the "
                "Mirror cannot show a time or a trading day without one"
            )
        return profile.timezone()

    trips = [
        Trip(
            trip_id=row.trip_id,
            trading_day=row.entry_ts.astimezone(zone_for(row)).date().isoformat(),
            entry_ts=row.entry_ts.astimezone(zone_for(row)),
            exit_ts=row.exit_ts.astimezone(zone_for(row)),
            holding_seconds=int((row.exit_ts - row.entry_ts).total_seconds()),
            net=row.net,
            lots=row.quantity or 1,
            risk_unit_source=row.risk_unit_source,
        )
        for row in rows
    ]
    return trips, imp
