"""TICKET-896: consent for a recurring, read-only broker pull.

A trader who uploads a file agrees to one diagnosis of that file. A broker connection
is a standing permission to fetch his trades, so it is its own consent: its own words,
its own ledger kind (``broker_pull``), its own version, and never an amendment to the
diagnosis consent. Disconnecting is one action: the stored key is deleted and nothing
more is fetched, and every report he already has stays. Deleting his account removes
the key with everything else.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from services.production.accounts import broker_connection as bc
from services.production.accounts import consent as cs
from services.production.accounts import deletion
from services.production.api.routes_consent import _grants_on_an_older_text, consent_state
from services.production.db import models as m
from services.production.db.session import make_session
from services.shared.schemas import scope_v1 as s
from tests.unit.accounts.test_deletion import a_trader, engine, store  # noqa: F401

KEY = "ciphertext-of-his-broker-key"


def connected(sess, store, login_id: str = "connected") -> m.Trader:
    """A development account with a current diagnosis grant, a broker grant and a key."""
    trader = a_trader(sess, login_id, store, b"his own file\n")
    trader.development_data = True
    sess.add(m.ConsentEvent(trader_id=trader.id, purpose=s.ConsentPurpose.DIAGNOSIS,
                            scope="v1", terms_version=cs.CURRENT.version, granted=True,
                            at=datetime.now(UTC), method="web", wording_shown="x" * 100))
    sess.flush()
    bc.grant(sess, trader)
    sess.add(m.BrokerConnection(trader_id=trader.id, broker="dhan",
                                token_ciphertext=KEY, connected_at=datetime.now(UTC)))
    sess.flush()
    return trader


def broker_rows(sess, trader_id: int) -> list[m.ConsentEvent]:
    return list(sess.scalars(
        select(m.ConsentEvent)
        .where(m.ConsentEvent.trader_id == trader_id,
               m.ConsentEvent.purpose == s.ConsentPurpose.BROKER_PULL)
        .order_by(m.ConsentEvent.id)).all())


def test_broker_pull_is_its_own_kind_and_not_in_the_diagnosis_text():
    assert s.ConsentPurpose.BROKER_PULL.value == "broker_pull"
    assert cs.BROKER_PULL.purpose.enum is s.ConsentPurpose.BROKER_PULL
    assert "broker_pull" not in {p.key for p in cs.CURRENT.purposes}
    assert cs.CURRENT.version == "1"
    assert cs.BROKER_PULL.version != cs.CURRENT.version


def test_the_words_say_what_how_often_read_only_how_long_and_how_to_stop():
    words = cs.broker_pull_wording()
    text = cs.BROKER_PULL
    assert cs.READ_ONLY_PROMISE == (
        "read-only: we can fetch your trades, we can never place, change or cancel an order."
    )
    assert cs.READ_ONLY_PROMISE in words
    for part in (text.what_we_fetch, text.how_often, text.how_to_stop,
                 text.what_stopping_keeps):
        assert part and part in words
    assert words.startswith(f"[{text.version}]")


def test_retention_is_the_existing_wording_not_a_new_period():
    assert cs.BROKER_PULL.how_long == cs.CURRENT.how_long
    words = cs.broker_pull_wording()
    assert cs.CURRENT.how_long in words
    assert cs.CURRENT.what_deletion_covers in words


def test_the_words_are_a_draft_until_someone_reviews_them():
    assert cs.BROKER_PULL.reviewed is False
    with pytest.raises(cs.UnreviewedConsentText):
        cs.require_reviewed(cs.BROKER_PULL, development_data=False)
    cs.require_reviewed(cs.BROKER_PULL, development_data=True)


@pytest.mark.parametrize("never", ["guaranteed", "platform", "signal", "you should",
                                   "we recommend", "profitable"])
def test_the_words_make_no_claim(never):
    assert never not in cs.broker_pull_wording().lower()


def test_a_real_account_cannot_grant_on_the_draft(engine, store):  # noqa: F811
    with make_session(engine) as sess:
        trader = a_trader(sess, "real", store, b"his own file\n")
        with pytest.raises(cs.UnreviewedConsentText):
            bc.grant(sess, trader)


def test_a_grant_is_a_new_row_and_the_diagnosis_consent_is_untouched(engine, store):  # noqa: F811
    with make_session(engine) as sess:
        trader = connected(sess, store)
        sess.commit()
        rows = broker_rows(sess, trader.id)
        assert [(r.granted, r.terms_version) for r in rows] == [(True, cs.BROKER_PULL.version)]
        assert rows[0].wording_shown == cs.broker_pull_wording()
        state = consent_state(sess, trader)
        assert state[s.ConsentPurpose.DIAGNOSIS] is True
        assert state[s.ConsentPurpose.BROKER_PULL] is True
        assert _grants_on_an_older_text(sess, trader) == set()


def test_disconnect_is_one_action_and_his_reports_stay(engine, store):  # noqa: F811
    with make_session(engine) as sess:
        trader = connected(sess, store)
        sess.commit()
        imports = sess.scalar(select(func.count()).select_from(m.Import))
        journals = sess.scalar(select(func.count()).select_from(m.Journal))

        bc.disconnect(sess, trader)
        sess.commit()

        assert not bc.is_connected(sess, trader)
        assert sess.scalars(select(m.BrokerConnection)).all() == []
        assert [r.granted for r in broker_rows(sess, trader.id)] == [True, False]
        assert consent_state(sess, trader)[s.ConsentPurpose.DIAGNOSIS] is True
        assert sess.scalar(select(func.count()).select_from(m.Import)) == imports
        assert sess.scalar(select(func.count()).select_from(m.Journal)) == journals


def test_deleting_a_connected_trader_leaves_no_key_behind(engine, store):  # noqa: F811
    with make_session(engine) as sess:
        trader = connected(sess, store)
        trader_id = trader.id
        sess.commit()
        assert "broker_connection" in deletion.nothing_remains(sess, store, trader_id)

        record = deletion.delete_trader(sess, store, trader=trader)
        sess.commit()

        assert sess.scalars(select(m.BrokerConnection)).all() == []
        assert deletion.nothing_remains(sess, store, trader_id) == []
        assert json.loads(record.what_removed)["rows"]["broker_connection"] == 1
        assert sess.scalars(select(m.DeletionRecord)).one().id == record.id
        kept = f"{record.what_removed} {record.what_retained} {record.locations_checked}"
    assert KEY not in kept