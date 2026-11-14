"""The broker connection's two actions: agree to it, and stop it (TICKET-896).

Both write the ledger the way every consent does: a new ``broker_pull`` row, never an
edit. Disconnecting is one call: the stored key goes and nothing more is fetched, and
every import, journal and report he already has stays, because they are ordinary records.
The fetching itself is the connector's ticket and is not here.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from services.production.accounts import consent as cs
from services.production.db import models as m
from services.shared.schemas import scope_v1 as s


def grant(sess: Session, trader: m.Trader) -> m.ConsentEvent:
    """Record that he agreed to the recurring pull, with the words he was shown.

    A real account is refused while the text is an unreviewed draft: the wording is a
    promise, and nobody has yet checked we can keep it.
    """
    text = cs.require_reviewed(cs.BROKER_PULL, development_data=trader.development_data)
    event = m.ConsentEvent(
        trader_id=trader.id, purpose=s.ConsentPurpose.BROKER_PULL, scope="v1",
        terms_version=text.version, granted=True, at=datetime.now(UTC), method="web",
        wording_shown=cs.broker_pull_wording(text),
    )
    sess.add(event)
    sess.flush()
    return event


def is_connected(sess: Session, trader: m.Trader) -> bool:
    return sess.scalars(select(m.BrokerConnection.id)
                        .where(m.BrokerConnection.trader_id == trader.id).limit(1)).first() is not None


def disconnect(sess: Session, trader: m.Trader) -> m.ConsentEvent:
    """One action: delete the stored key, then write the withdrawal. Caller commits."""
    sess.execute(delete(m.BrokerConnection).where(m.BrokerConnection.trader_id == trader.id))
    event = m.ConsentEvent(
        trader_id=trader.id, purpose=s.ConsentPurpose.BROKER_PULL, scope="v1",
        terms_version=cs.BROKER_PULL.version, granted=False, at=datetime.now(UTC),
        method="web", wording_shown=f"[withdrawn] {cs.BROKER_PULL.purpose.title}",
    )
    sess.add(event)
    sess.flush()
    return event