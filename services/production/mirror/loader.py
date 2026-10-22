"""Load a trader's trips out of the database and into the metric functions' shape.

The metrics know nothing about SQLAlchemy and the database knows nothing about
Appendix A. This is the one place the two meet.

Trips come from the trader's **current** import versions only: a superseded import
is history, not his record, and showing both would double-count a re-upload.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.production.accounts import risk_budget as rb
from services.production.ctr.intake import outcomes as oc
from services.production.ctr.profiles import registry as profiles
from services.production.db import models as m
from services.production.mirror.metrics import Trip
from services.shared.schemas import scope_v1 as s

PROFILE_DIR = Path(__file__).resolve().parents[1] / "ctr" / "profiles"


class UnknownAdapter(Exception):
    """An import read by an adapter this code no longer carries."""


class MisdeclaredQuantityUnit(Exception):
    """A quantity that cannot be whole lots under the declared unit."""


def _measured_against(
    row: m.Trip, trading_day: str, declarations: list[m.RiskBudgetDeclaration]
) -> s.RiskUnitSourceV1:
    """Which denominator this trip is counted under, decided as it is read.

    The row carries what was knowable when the file was imported. The declared
    budget usually is not: PRD section 4 asks for it after the import, and trips
    are insert-only, so a trip written before the question was answered would
    report `premium_paid` forever. The first walkthrough showed exactly that --
    forty trades against premium paid, none against the budget, with a declaration
    covering every one of them.

    PRD 5.5 puts the declared budget first in the hierarchy, so it wins here too,
    over a stop and over the premium.
    """
    if rb.rupees(rb.in_force(declarations, trading_day)) is not None:
        return s.RiskUnitSourceV1.DECLARED_BUDGET
    return row.risk_unit_source


def lots_for(
    quantity: int,
    profile: profiles.InstrumentProfile,
    quantity_unit: str,
    on: date | None = None,
) -> int:
    """The trader's size in lots, from the count his broker exported.

    Appendix A defines lots as "quantity in the instrument profile's lot unit", and
    the export's column is named "Quantity/Lot" -- which of the two it holds is not
    among the facts verified against real rows, so it is declared in the file map
    (TD-029) rather than assumed here.

    A count that is not a whole number of lots is refused. It means the declared
    unit is wrong, and the alternative is printing a trader a fractional lot he
    cannot have held.

    Lot sizes change, and at a changeover two are live at once for different
    expiries, so the profile may carry dated sizes and ``on`` picks the ones in
    force that day. The largest one that divides the quantity wins; with no date,
    or no history, the current size is the only candidate.
    """
    if quantity_unit == "lots":
        return quantity
    candidates = profile.lot_sizes_on(on)
    if not candidates:
        raise MisdeclaredQuantityUnit(
            f"{profile.exchange}:{profile.symbol} has no lot size in force on {on}"
        )
    for lot_size in candidates:
        if lot_size <= 0:
            raise MisdeclaredQuantityUnit(
                f"{profile.exchange}:{profile.symbol} has a lot size of {lot_size}"
            )
        lots, remainder = divmod(Decimal(quantity), lot_size)
        if remainder == 0:
            return int(lots)
    sizes = ", ".join(str(c) for c in candidates)
    raise MisdeclaredQuantityUnit(
        f"{quantity} units of {profile.exchange}:{profile.symbol} is not a whole "
        f"number of lots at any lot size in force"
        f"{f' on {on}' if on else ''} ({sizes}) -- not a position anyone can "
        "hold, so either the declared quantity unit or the profile's lot history is wrong"
    )


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
        return profile_for(row).timezone()

    def profile_for(row: m.Trip) -> profiles.InstrumentProfile:
        profile = profiles.lookup(profile_map, row.exchange, row.symbol, row.segment)
        if profile is None:
            raise profiles.UnknownInstrument(
                f"no instrument profile for {row.exchange}:{row.symbol} -- the "
                "Mirror cannot show a time or a trading day without one"
            )
        return profile

    quantity_unit = "lots"
    if imp is not None:
        adapter = oc.adapter_for(imp.adapter_id)
        if adapter is None:
            raise UnknownAdapter(
                f"import {imp.id} was read with {imp.adapter_id!r}, which this "
                "code no longer has a file map for, so the size figures cannot "
                "be read in a known unit (TD-027)"
            )
        quantity_unit = adapter.file_map().quantity_unit

    declarations = rb.for_trader(sess, trader)

    trips = []
    for row in rows:
        zone = zone_for(row)
        trading_day = row.entry_ts.astimezone(zone).date().isoformat()
        trips.append(Trip(
            trip_id=row.trip_id,
            trading_day=trading_day,
            entry_ts=row.entry_ts.astimezone(zone),
            exit_ts=row.exit_ts.astimezone(zone),
            holding_seconds=int((row.exit_ts - row.entry_ts).total_seconds()),
            net=row.net,
            lots=lots_for(row.quantity or 1, profile_for(row), quantity_unit,
                          on=date.fromisoformat(trading_day)),
            risk_unit_source=_measured_against(row, trading_day, declarations),
        ))
    return trips, imp
