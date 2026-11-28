"""The report pages a trader has opened, per upload: what the dial's reading ring shows.

Recorded on the server when a fact page is served, so "read" never depends on a script. Keyed to
the upload he is reading, so a new upload starts unread; the year and book filter he read it
through are kept beside each row, and any of them counts the page as opened.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from services.production.db import models as m

BOOK_LENGTH = 64


def record(sess, trader, imp, key: str, period: str, book: str | None) -> None:
    """Note that he opened `key` in this upload, once per period and book."""
    book = (book or "")[:BOOK_LENGTH]
    seen = sess.scalar(select(m.FactRead.id).where(
        m.FactRead.trader_id == trader.id, m.FactRead.import_id == imp.id,
        m.FactRead.fact_key == key, m.FactRead.period == period,
        m.FactRead.book == book).limit(1))
    if seen is None:
        sess.add(m.FactRead(trader_id=trader.id, import_id=imp.id, fact_key=key, period=period,
                            book=book, opened_at=datetime.now(UTC)))
        sess.commit()


def opened(sess, trader, imp) -> frozenset[str]:
    """Every page he has opened in this upload, whatever filter he read it through."""
    if trader is None or imp is None:
        return frozenset()
    return frozenset(sess.scalars(select(m.FactRead.fact_key).where(
        m.FactRead.trader_id == trader.id, m.FactRead.import_id == imp.id)))
