"""The bar figures Your process reads, as stored off the web app.

The bar-figures worker writes one ``bar_trade_figure`` row per trade of an import: how far its
underlying went his way while he held, what he took, in points, or the reason it has none. A page
reads those rows and never bars. Until the worker's table exists in this database, or before it has
worked an import out, there is nothing to read, and the Execution row says so rather than failing.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from services.production.api.process import Bars
from services.production.db import models as m


def _point(text: str | None) -> Decimal | None:
    return None if text is None else Decimal(text)


def ranges(sess: Session, import_id: int) -> dict[tuple[str, str], Decimal] | None:
    """Each (underlying, day) he traded and how far the market moved that day, in points, or None
    when none are stored for this import."""
    model = getattr(m, "BarDayRange", None)
    if model is None:
        return None
    try:
        rows = sess.scalars(select(model).where(model.import_id == import_id)).all()
    except (OperationalError, ProgrammingError):
        return None
    return {(r.underlying, r.day): Decimal(r.range_points) for r in rows} or None


def stored(sess: Session, import_id: int) -> dict[str, Bars] | None:
    """Each trade's stored figures by trip id, or None when none are stored for this import."""
    model = getattr(m, "BarTradeFigure", None)
    if model is None:
        return None
    try:
        rows = sess.scalars(select(model).where(model.import_id == import_id)).all()
    except (OperationalError, ProgrammingError):
        return None
    if not rows:
        return None
    return {r.trip_id: Bars(underlying=r.underlying, way=_point(r.way), took=_point(r.took), reason=r.reason)
            for r in rows}
