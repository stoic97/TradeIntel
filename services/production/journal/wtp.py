"""The willingness-to-pay question (PRD 7.2, 11).

Asked once, in the third Journal he OPENS -- not the third generated -- and not
before either a second upload or 14 days since his first, whichever comes first.

Each condition blocks a different way of getting a worthless answer. Opens rather
than generations, because a backfill makes sixty Journals in a second and he has
read none of them. A second upload or a fortnight, because asking a man who has had
the product for four minutes what he would pay produces a number about his
politeness. And once, because a question asked twice is a request: ``ask_here`` holds it
to the first Journal it may be asked on, and ``wtp_asked`` remembers which that was.

The answer is stored with uploads-so-far and days-since-first-upload. Ten answers
give the first price range at zero cost; ten answers nobody can interpret give
nothing, and the difference is whether the context was recorded at the time.

The price is a placeholder the team sets before the first partner reaches the
trigger (PRD 11). It lives in constants.py with its argument.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.production.db import models as m
from services.production.journal import constants as k

ANSWERS = frozenset({"yes", "no", "maybe"})
JOURNALS_BEFORE_ASKING = 3

QUESTION = (
    f"We are deciding what to charge. Would you pay ₹{k.WTP_PRICE_INR} a month for "
    "this Journal and a monthly record of how you traded? Yes, no, or maybe — and "
    "if not, what would change it?"
)


class NotAnAnswer(Exception):
    """Yes, no or maybe. A free-text answer goes in the free-text field."""


def _journals_opened(sess: Session, trader: m.Trader) -> int:
    return int(sess.scalar(
        select(func.count())
        .select_from(m.Journal)
        .where(m.Journal.trader_id == trader.id,
               m.Journal.opened_at.is_not(None))
    ) or 0)


def _upload_count(sess: Session, trader: m.Trader) -> int:
    return int(sess.scalar(
        select(func.count())
        .select_from(m.Import)
        .where(m.Import.trader_id == trader.id)
    ) or 0)


def _days_since_first_upload(sess: Session, trader: m.Trader) -> int:
    first = sess.scalars(
        select(m.Import)
        .where(m.Import.trader_id == trader.id)
        .order_by(m.Import.created_at)
    ).first()
    if first is None:
        return 0
    return (datetime.now(UTC) - first.created_at).days


def _already_answered(sess: Session, trader: m.Trader) -> bool:
    return sess.scalars(
        select(m.WtpAnswer).where(m.WtpAnswer.trader_id == trader.id)
    ).first() is not None


def should_ask(sess: Session, *, trader: m.Trader) -> bool:
    """Whether this trader may be asked, right now."""
    if _already_answered(sess, trader):
        return False
    if _journals_opened(sess, trader) < JOURNALS_BEFORE_ASKING:
        return False
    settled_in = (
        _upload_count(sess, trader) >= 2
        or _days_since_first_upload(sess, trader) >= k.WTP_DAYS_SINCE_FIRST_UPLOAD
    )
    return settled_in


def _asked_on(sess: Session, trader: m.Trader) -> m.WtpAsked | None:
    return sess.scalars(select(m.WtpAsked).where(m.WtpAsked.trader_id == trader.id)).first()


def ask_here(sess: Session, *, trader: m.Trader, journal: m.Journal) -> bool:
    """Whether this Journal is the one that asks. The caller commits.

    The first Journal drawn once he may be asked becomes the one, and only that one asks. It
    stays there until answered, so saving a note on that page doesn't take the question away.
    """
    if not should_ask(sess, trader=trader):
        return False
    asked = _asked_on(sess, trader)
    if asked is None:
        sess.add(m.WtpAsked(trader_id=trader.id, journal_id=journal.id,
                            asked_at=datetime.now(UTC)))
        try:
            sess.flush()
        except IntegrityError:  # two tabs raced: the other one asked
            sess.rollback()
        asked = _asked_on(sess, trader)
    return asked is not None and asked.journal_id == journal.id


def record(
    sess: Session,
    *,
    trader: m.Trader,
    journal: m.Journal,
    answer: str,
    free_text: str,
) -> m.WtpAnswer:
    """Store the answer with the context that makes it interpretable."""
    if answer not in ANSWERS:
        raise NotAnAnswer(f"{answer!r} is not one of {sorted(ANSWERS)}")

    stored = m.WtpAnswer(
        trader_id=trader.id,
        journal_id=journal.id,
        answer=answer,
        free_text=free_text or None,
        uploads_so_far=_upload_count(sess, trader),
        days_since_first_upload=_days_since_first_upload(sess, trader),
        asked_at=datetime.now(UTC),
    )
    sess.add(stored)
    sess.flush()
    return stored
