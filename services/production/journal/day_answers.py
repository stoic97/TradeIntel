"""TICKET-915: his answers to the day's questions, kept with the words he saw.

A fixed set of answers, Yes, No or This looks wrong, never a typed word, so consent v1 is
untouched (the TICKET-906 precedent). Each answer is a new row carrying the question as it
was written, the day it is about and when he said it: a changed answer is a second row, not
an edit, and the list of them is his history to read back.

Ask, never score (founder, 12 Nov 2026; Pawan, 17 Nov). Nothing here reads what the day
came to, and nothing anywhere counts or splits these answers by result. A guard test fails
if any other module touches this table.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.production.db import models as m
from services.production.journal import day_questions as dq

YES, NO, WRONG = "yes", "no", "wrong"
ANSWERS = (YES, NO, WRONG)
LABELS = {YES: "Yes", NO: "No", WRONG: "This looks wrong"}


class NotAnAnswer(Exception):
    """Yes, No or This looks wrong, nothing else."""


class NotAQuestion(Exception):
    """The day did not ask that question."""


class NotADay(Exception):
    """A Journal covering more than a day asks no day questions."""


def _rows(sess: Session, trader: m.Trader, day: str) -> list[m.JournalDayAnswer]:
    return list(sess.scalars(
        select(m.JournalDayAnswer)
        .where(m.JournalDayAnswer.trader_id == trader.id,
               m.JournalDayAnswer.trading_day == day)
        .order_by(m.JournalDayAnswer.id)))


def record(sess: Session, *, trader: m.Trader, journal: m.Journal, key: str, answer: str,
           questions: list[dq.DayQuestion]) -> m.JournalDayAnswer:
    """Keep one answer. The same answer said again writes nothing; a different one is a new row."""
    if answer not in ANSWERS:
        raise NotAnAnswer(answer)
    if journal.period_start != journal.period_end:
        raise NotADay(journal.id)
    asked = {q.key: q.text for q in questions}
    if key not in asked:
        raise NotAQuestion(key)
    said = [r for r in _rows(sess, trader, journal.period_start) if r.question_key == key]
    if said and said[-1].answer == answer:
        return said[-1]
    row = m.JournalDayAnswer(
        trader_id=trader.id, journal_id=journal.id, trading_day=journal.period_start,
        question_key=key, question_text=asked[key], answer=answer,
        answered_at=datetime.now(UTC))
    sess.add(row)
    sess.flush()
    return row


def latest_by_key(sess: Session, trader: m.Trader, day: str) -> dict[str, str]:
    """What he last said to each of the day's questions, as the words on the buttons."""
    return {r.question_key: LABELS[r.answer] for r in _rows(sess, trader, day)}


def answered_days(sess: Session, trader: m.Trader) -> set[str]:
    """The days he has answered at least one question of."""
    return set(sess.scalars(
        select(m.JournalDayAnswer.trading_day)
        .where(m.JournalDayAnswer.trader_id == trader.id)))


def history(sess: Session, trader: m.Trader) -> list[m.JournalDayAnswer]:
    """Everything he has said, newest first."""
    return list(sess.scalars(
        select(m.JournalDayAnswer)
        .where(m.JournalDayAnswer.trader_id == trader.id)
        .order_by(m.JournalDayAnswer.id.desc())))