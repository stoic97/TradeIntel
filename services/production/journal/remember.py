"""TICKET-906: "Do you remember this day?" and what he answered.

A day that is neither worth a look nor new asks this before its questions
(days_worth_a_look.offer). Yes and No are both kept, with the day's age, because together
they say whether seven days (constants.NEW_DAY_WITHIN_DAYS) is the right window - the
founder's ruling, 13 Nov 2026. Kept once per trading day, never edited: a day he answered
stops asking, and stays on the calendar and writable. A week or ten-trade Journal is not
a day and is never asked.

The same pattern as the guess (mirror/guess.py): a closed set of answers, the first
stands, two tabs racing leave one row.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.production.db import models as m
from services.production.journal import recency

YES, NO = "yes", "no"


class NotAnAnswer(Exception):
    """Yes or no, nothing else."""


class NotADay(Exception):
    """A Journal covering more than a day is not asked whether he remembers the day."""


def answer_of(sess: Session, trader: m.Trader, day: str) -> m.JournalRememberAnswer | None:
    return sess.scalars(
        select(m.JournalRememberAnswer).where(m.JournalRememberAnswer.trader_id == trader.id,
                                              m.JournalRememberAnswer.trading_day == day)
    ).first()


def record(sess: Session, *, trader: m.Trader, journal: m.Journal, answer: str,
           on: date) -> m.JournalRememberAnswer:
    """Keep his first answer for the day; a second is ignored and the first returned."""
    if answer not in (YES, NO):
        raise NotAnAnswer(answer)
    if journal.period_start != journal.period_end:
        raise NotADay(journal.id)
    first = answer_of(sess, trader, journal.period_start)
    if first is not None:
        return first
    sess.add(m.JournalRememberAnswer(
        trader_id=trader.id, journal_id=journal.id, trading_day=journal.period_start,
        answer=answer, day_age_days=recency.day_age(journal.period_start, on),
        answered_at=datetime.now(UTC),
    ))
    try:
        sess.flush()
    except IntegrityError:  # two tabs raced: the first stands
        sess.rollback()
    return answer_of(sess, trader, journal.period_start)


def remembered_days(sess: Session, trader: m.Trader) -> set[str]:
    """The trading days he has answered Yes or No for."""
    return set(sess.scalars(
        select(m.JournalRememberAnswer.trading_day)
        .where(m.JournalRememberAnswer.trader_id == trader.id)
    ))


def written_days(sess: Session, trader: m.Trader) -> set[str]:
    """The day Journals he has written something on, in any version of the day."""
    return set(sess.scalars(
        select(m.Journal.period_start)
        .join(m.JournalFieldEntry, m.JournalFieldEntry.journal_id == m.Journal.id)
        .where(m.Journal.trader_id == trader.id, m.Journal.period_start == m.Journal.period_end,
               m.JournalFieldEntry.value.is_not(None), m.JournalFieldEntry.value != "")
    ))


def answered_days(sess: Session, trader: m.Trader) -> set[str]:
    """What the calendar marks answered (gate 4): a Yes, a No, or anything he wrote."""
    return remembered_days(sess, trader) | written_days(sess, trader)
