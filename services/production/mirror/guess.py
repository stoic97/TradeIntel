"""B6: the guess, before the reveal (handoff 5 and 9, screen 10; TR-009).

Right after his import is checked, before anything is shown, the trader is asked
what he thinks his tradebook will say. Then the reveal shows him his five worst
days. The method rule behind it (brand C03): never build on self-report alone - the
gap between the guess and the count is the product's first proof.

**The question and the ten labels are the research seat's to write and freeze**
(TR-009, D3). Until they are, the set below is a placeholder, marked as one, and
FROZEN is False. A placeholder must never reach a trader, so in production the guess
is skipped while FROZEN is False (ready()): the reveal shows, without a guess.
Freezing the set is one change, here: the labels, a new LABELS_VERSION, FROZEN True.

One guess per trader, ever, and never changed: a guess made after the answer is not
a guess. "I don't know" is its own answer.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.production.db import models as m

FROZEN = False
LABELS_VERSION = "placeholder"

QUESTION = "[guess question, TR-009]"
LABELS = {f"option-{n}": f"[guess option {n}, TR-009]" for n in range(1, 11)}

UNKNOWN = "unknown"
UNKNOWN_LABEL = "I don't know"


class NotAGuess(Exception):
    """One of the labels, or "unknown"."""


def ready(production: bool) -> bool:
    """Whether the guess may be asked: always in development, only once frozen live."""
    return FROZEN or not production


def label_of(answer: str) -> str:
    return UNKNOWN_LABEL if answer == UNKNOWN else LABELS[answer]


def answer_of(sess: Session, trader: m.Trader) -> m.GuessAnswer | None:
    return sess.scalars(select(m.GuessAnswer).where(m.GuessAnswer.trader_id == trader.id)).first()


def record(sess: Session, *, trader: m.Trader, answer: str, import_id: int) -> m.GuessAnswer:
    """Keep his first guess; a second is ignored and the first returned."""
    if answer != UNKNOWN and answer not in LABELS:
        raise NotAGuess(answer)
    first = answer_of(sess, trader)
    if first is not None:
        return first
    sess.add(
        m.GuessAnswer(
            trader_id=trader.id,
            answer=answer,
            labels_version=LABELS_VERSION,
            import_id=import_id,
            answered_at=datetime.now(UTC),
        )
    )
    try:
        sess.flush()
    except IntegrityError:  # two tabs raced: the first stands
        sess.rollback()
    return answer_of(sess, trader)
