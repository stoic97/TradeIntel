"""B7: the leaving card (handoff 5 and 9, screen 19).

At the top of Your Journals, once, after he has read his first Journal: one question
in his own words, or "Not now". Shown once, ever - the card he scrolls past is not
shown again (LeavingCardShown is the flag) - and answered once, never edited.

**Its words are the copy owner's to write (D9), and its link the founder's to choose
(D2).** Until both are signed, the heading, question and offer below are
placeholders, marked as such, LINK is None (so no link is drawn), and SIGNED is
False. A placeholder must never reach a trader, so in production the card is not
shown while SIGNED is False (ready()). Signing it is one change, here: the words, a
new COPY_VERSION, the link, SIGNED True - plus, for a WhatsApp link, its host named
in test_app_skeleton.py and a row in the data-flow map.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.production.db import models as m

SIGNED = False
COPY_VERSION = "placeholder"

HEADING = "[leaving card heading, D9]"
QUESTION = "[leaving card question, D9]"
OFFER = "[leaving card offer, D9]"
LINK: str | None = None  # D2: the founder's WhatsApp, or mailto

ANSWERED, DISMISSED = "answered", "dismissed"
LONGEST = 2000
"""Characters kept of an answer: a card, not a letter."""


def ready(production: bool) -> bool:
    """Whether the card may be shown: always in development, only once signed live."""
    return SIGNED or not production


def _first(sess: Session, model, trader: m.Trader):
    return sess.scalars(select(model).where(model.trader_id == trader.id)).first()


def due(sess: Session, trader: m.Trader, *, production: bool) -> bool:
    """Shown now: ready, never shown before, and he has read a Journal."""
    if not ready(production) or _first(sess, m.LeavingCardShown, trader) is not None:
        return False
    read = sess.scalars(
        select(m.Journal.id)
        .where(m.Journal.trader_id == trader.id, m.Journal.opened_at.is_not(None))
    ).first()
    return read is not None


def mark_shown(sess: Session, trader: m.Trader) -> None:
    sess.add(m.LeavingCardShown(trader_id=trader.id, copy_version=COPY_VERSION,
                                shown_at=datetime.now(UTC)))
    try:
        sess.flush()
    except IntegrityError:  # two tabs raced: it was shown once either way
        sess.rollback()


def record(sess: Session, *, trader: m.Trader, answer: str | None) -> m.LeavingCardAnswer | None:
    """His answer, or "Not now" when answer is None or blank.

    Kept only for a card he was shown, and only the first time: None otherwise.
    """
    if _first(sess, m.LeavingCardShown, trader) is None:
        return None
    first = _first(sess, m.LeavingCardAnswer, trader)
    if first is not None:
        return first
    words = (answer or "").strip()[:LONGEST]
    sess.add(m.LeavingCardAnswer(
        trader_id=trader.id,
        outcome=ANSWERED if words else DISMISSED,
        answer=words or None,
        copy_version=COPY_VERSION,
        answered_at=datetime.now(UTC),
    ))
    try:
        sess.flush()
    except IntegrityError:
        sess.rollback()
    return _first(sess, m.LeavingCardAnswer, trader)
