"""B4: "Does this match your trading?" under each chapter's story cards (handoff 9).

Chapters 1 to 3 ask it; chapter 4 is the honest close and asks nothing. One answer
per chapter per trader, and it is never changed: a second tap after the first is
not a second opinion, it is a slip, and an answer that can be taken back is one
nobody can read. After "Wrong" the trader may say which of three it was, once, or
say nothing; a reason is never asked for after "Accurate" or "Not sure".

The answers are what the kit's screen 17 shows, in its own words.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.production.db import models as m

CHAPTERS = frozenset({1, 2, 3})

ANSWERS = {"accurate": "Accurate", "not_sure": "Not sure", "wrong": "Wrong"}

REASONS = {
    "wrong_facts": "Wrong facts",
    "wrong_reading": "Right facts, wrong reading",
    "already_changed": "I've already changed this",
}


class NotAsked(Exception):
    """A chapter that does not ask, or a value that is not one of the choices."""


@dataclass(frozen=True)
class State:
    """Where the question stands for one trader and one chapter."""

    answer: str | None
    reason: str | None

    @property
    def stage(self) -> str:
        """asked, why (after Wrong, no reason yet) or recorded."""
        if self.answer is None:
            return "asked"
        if self.answer == "wrong" and self.reason is None:
            return "why"
        return "recorded"


NOTE_LIMIT = 2000
WHOLE_REPORT = ""


def report_answer(sess: Session, trader: m.Trader, import_id: int) -> str | None:
    """The answer given about this report, if one was."""
    return sess.scalars(
        select(m.ReportFeedback.answer).where(
            m.ReportFeedback.trader_id == trader.id,
            m.ReportFeedback.import_id == import_id,
            m.ReportFeedback.trading_day == WHOLE_REPORT,
        )
    ).first()


def record_report_answer(
    sess: Session, *, trader: m.Trader, import_id: int, answer: str, note: str | None
) -> None:
    """Keep the first answer about a report and its note; a later one changes nothing."""
    if answer not in ANSWERS:
        raise NotAsked(f"answer {answer!r}")
    if report_answer(sess, trader, import_id) is not None:
        return
    sess.add(
        m.ReportFeedback(
            trader_id=trader.id, import_id=import_id, trading_day=WHOLE_REPORT, answer=answer,
            note=(note or "").strip()[:NOTE_LIMIT] or None, answered_at=datetime.now(UTC),
        )
    )
    try:
        sess.flush()
    except IntegrityError:  # a second tap raced the first: the first stands
        sess.rollback()


def _row(sess: Session, trader: m.Trader, chapter: int) -> m.ChapterFeedback | None:
    return sess.scalars(
        select(m.ChapterFeedback).where(
            m.ChapterFeedback.trader_id == trader.id, m.ChapterFeedback.chapter == chapter
        )
    ).first()


def state(sess: Session, trader: m.Trader, chapter: int) -> State:
    row = _row(sess, trader, chapter)
    if row is None:
        return State(None, None)
    reason = sess.scalars(
        select(m.ChapterFeedbackReason.reason).where(m.ChapterFeedbackReason.feedback_id == row.id)
    ).first()
    return State(row.answer, reason)


def record_answer(
    sess: Session, *, trader: m.Trader, chapter: int, answer: str, import_id: int
) -> State:
    """Keep the first answer; a later one is ignored and the state returned as it is."""
    if chapter not in CHAPTERS or answer not in ANSWERS:
        raise NotAsked(f"chapter {chapter}, answer {answer!r}")
    if _row(sess, trader, chapter) is None:
        sess.add(
            m.ChapterFeedback(
                trader_id=trader.id,
                chapter=chapter,
                answer=answer,
                import_id=import_id,
                answered_at=datetime.now(UTC),
            )
        )
        try:
            sess.flush()
        except IntegrityError:  # a second tap raced the first: the first stands
            sess.rollback()
    return state(sess, trader, chapter)


def record_reason(sess: Session, *, trader: m.Trader, chapter: int, reason: str) -> State:
    """Keep the reason for a Wrong that has none yet; anything else changes nothing."""
    if chapter not in CHAPTERS or reason not in REASONS:
        raise NotAsked(f"chapter {chapter}, reason {reason!r}")
    row = _row(sess, trader, chapter)
    if row is not None and state(sess, trader, chapter).stage == "why":
        sess.add(
            m.ChapterFeedbackReason(feedback_id=row.id, reason=reason, given_at=datetime.now(UTC))
        )
        try:
            sess.flush()
        except IntegrityError:
            sess.rollback()
    return state(sess, trader, chapter)
