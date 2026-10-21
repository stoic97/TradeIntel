"""Deletion that executes, and a way to prove it did (PRD 3, PRD 10).

The consent screen makes a promise in specific words: the file, every artefact
derived from it, every Journal, and backups within 30 days. These tests are what
make that sentence something other than an intention.

The release gate (PRD 10, step 3) requires the runbook run end to end on a fixture
account with every location in the data-flow map checked afterwards. The last test
here is that drill, run on every commit rather than once before launch.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from services.production.accounts import deletion
from services.production.accounts.file_store import FileStore
from services.production.db import models as m
from services.production.db.models import InsertOnlyViolation
from services.production.db.session import make_engine, make_session, run_migrations
from services.shared.schemas import scope_v1 as s


@pytest.fixture()
def engine():
    import os
    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


@pytest.fixture()
def store(tmp_path):
    from services.production.accounts.file_store import generate_key
    return FileStore(tmp_path / "files", generate_key())


def a_trader(sess, login_id: str, store: FileStore, content: bytes) -> m.Trader:
    """A trader with one of everything his deletion has to reach."""
    trader = m.Trader(display_name=login_id, login_id=login_id,
                      password_hash="x", created_at=datetime.now(UTC))
    sess.add(trader)
    sess.flush()
    sess.add(m.InviteCode(code=f"I-{login_id}", created_at=datetime.now(UTC),
                          redeemed_by=trader.id))
    sess.add(m.ConsentEvent(trader_id=trader.id, purpose=s.ConsentPurpose.DIAGNOSIS,
                            scope="v1", terms_version="0-draft", granted=True,
                            at=datetime.now(UTC), method="web",
                            wording_shown="x" * 100))
    sess.add(m.RiskBudgetDeclaration(
        trader_id=trader.id, value=Decimal(3000), unit="INR",
        effective_from="2026-09-01", declared_at=datetime.now(UTC),
        retrospective=True))

    stored = store.put(content)
    raw = m.RawFile(trader_id=trader.id, sha256=stored.sha256,
                    original_name="t.csv", size=stored.size,
                    stored_path=str(stored.path), uploaded_at=datetime.now(UTC))
    sess.add(raw)
    sess.flush()
    imp = m.Import(trader_id=trader.id, raw_file_id=raw.id, source_account="A",
                   adapter_id="dhan_tradebook_v1", adapter_version="1",
                   filemap_version="1", code_version="t",
                   outcome=s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS,
                   rows_in=1, rows_parsed=1, rows_excluded=0, fees_available=False,
                   version_no=1, trips_reconstructed=1, density_default_unit="day",
                   created_at=datetime.now(UTC))
    sess.add(imp)
    sess.flush()
    sess.add(m.Trip(
        import_id=imp.id, trip_id=f"{login_id}-trip", trading_day="2026-09-01",
        exchange="MCX", symbol="WIDGETOIL", segment="OPT", direction="LONG",
        entry_ts=datetime(2026, 9, 1, 9, 30, tzinfo=UTC),
        exit_ts=datetime(2026, 9, 1, 10, 0, tzinfo=UTC), quantity=1,
        entry_price=Decimal(100), exit_price=Decimal(105), gross=Decimal(5),
        fees=Decimal(0), net=Decimal(5), fees_available=False,
        risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID))
    journal = m.Journal(trader_id=trader.id, import_id=imp.id,
                        unit=s.JournalUnit.DAY, period_start="2026-09-01",
                        period_end="2026-09-01", version_no=1,
                        generated_at=datetime.now(UTC), opened_at=None,
                        trip_ids=json.dumps([f"{login_id}-trip"]), sections="{}")
    sess.add(journal)
    sess.flush()
    sess.add(m.JournalFieldEntry(
        journal_id=journal.id, trip_id=f"{login_id}-trip", field="planned_sl",
        value="250", entered_at=datetime.now(UTC),
        capture_phase=s.CapturePhase.AFTER_CLOSE))
    sess.add(m.DwellEvent(trader_id=trader.id, surface="mirror", key="worst-days",
                          event="drawer_opened", at=datetime.now(UTC),
                          duration_ms=1200))
    sess.commit()
    return trader


def test_everything_derived_from_him_goes(engine, store):
    with make_session(engine) as sess:
        trader = a_trader(sess, "rikk", store, b"his own file\n")
        trader_id = trader.id
        assert deletion.nothing_remains(sess, store, trader_id) != []

        deletion.delete_trader(sess, store, trader=trader)
        sess.commit()

        assert deletion.nothing_remains(sess, store, trader_id) == []


def test_the_file_itself_is_gone_from_disk(engine, store):
    content = b"his own file\n"
    with make_session(engine) as sess:
        trader = a_trader(sess, "rikk", store, content)
        digest = sess.scalars(select(m.RawFile.sha256)).one()
        assert store.exists(digest)

        deletion.delete_trader(sess, store, trader=trader)
        sess.commit()
    assert not store.exists(digest), "the encrypted file is still on the disk"


def test_a_file_two_traders_share_is_not_taken_from_the_other(engine, store):
    """The store is keyed by the hash of the plaintext.

    Two traders who upload byte-identical exports have one blob between them.
    Deleting it for one would take the other's file with it, and nothing would
    say so until he next opened his record.
    """
    same = b"identical export\n"
    with make_session(engine) as sess:
        first = a_trader(sess, "one", store, same)
        a_trader(sess, "two", store, same)
        digest = sess.scalars(select(m.RawFile.sha256).limit(1)).first()

        record = deletion.delete_trader(sess, store, trader=first)
        sess.commit()
        removed = json.loads(record.what_removed)

    assert store.exists(digest), "the other trader's file went with it"
    assert removed["files_deleted"] == 0
    assert removed["files_kept_because_another_account_has_the_same_bytes"] == 1


def test_the_other_trader_is_untouched(engine, store):
    with make_session(engine) as sess:
        first = a_trader(sess, "one", store, b"one file\n")
        second = a_trader(sess, "two", store, b"two file\n")
        second_id = second.id

        deletion.delete_trader(sess, store, trader=first)
        sess.commit()

        assert deletion.nothing_remains(sess, store, second_id) != []
        assert sess.get(m.Trader, second_id) is not None


def test_the_record_of_the_deletion_survives_it(engine, store):
    """Thesis 19.4, and the consent text: the proof that both things happened."""
    with make_session(engine) as sess:
        trader = a_trader(sess, "rikk", store, b"his own file\n")
        trader_id = trader.id
        record = deletion.delete_trader(sess, store, trader=trader)
        sess.commit()

        kept = sess.scalars(select(m.DeletionRecord)).one()

    assert kept.trader_id == trader_id
    assert kept.completed_at is not None
    assert "No name, no trades" in kept.what_retained
    assert json.loads(kept.locations_checked) == list(deletion.LOCATIONS)
    rows = json.loads(record.what_removed)["rows"]
    assert rows["journal"] == 1 and rows["trip"] == 1 and rows["trader"] == 1


def test_the_record_carries_no_trade_of_his(engine, store):
    """What survives must not be his data wearing a different hat."""
    with make_session(engine) as sess:
        trader = a_trader(sess, "rikk", store, b"his own file\n")
        record = deletion.delete_trader(sess, store, trader=trader)
        sess.commit()
    text = f"{record.what_removed} {record.what_retained} {record.locations_checked}"
    for leak in ("rikk", "WIDGETOIL", "2026-09-01", "3000", "250"):
        assert leak not in text, leak


def test_insert_only_refuses_edits_but_permits_deletion(engine, store):
    """The guard this depends on, pinned.

    Insert-only means a correction is a new row. It does not mean a trader cannot
    leave. If the guard is ever widened to DELETE, deletion stops working, and it
    would stop quietly -- so this test fails first.
    """
    with make_session(engine) as sess:
        trader = a_trader(sess, "rikk", store, b"his own file\n")
        with pytest.raises(InsertOnlyViolation):
            sess.execute(update(m.ConsentEvent)
                         .where(m.ConsentEvent.trader_id == trader.id)
                         .values(granted=False))
        sess.rollback()

    with make_session(engine) as sess:
        trader = sess.scalars(
            select(m.Trader).where(m.Trader.login_id == "rikk")).one()
        deletion.delete_trader(sess, store, trader=trader)
        sess.commit()


def test_the_deletion_drill_the_release_gate_asks_for(engine, store):
    """PRD 10 step 3, run on every commit instead of once before launch.

    A fixture account with data in every location on the map, deleted, and every
    location checked afterwards -- including the encrypted file on disk, which is
    the one a database-only check would miss.
    """
    content = b"the fixture account's export\n"
    with make_session(engine) as sess:
        trader = a_trader(sess, "fixture", store, content)
        trader_id = trader.id
        digest = sess.scalars(select(m.RawFile.sha256)).one()

        before = deletion.nothing_remains(sess, store, trader_id)
        assert "trader" in before and "journal" in before and "trip" in before

        record = deletion.delete_trader(sess, store, trader=trader)
        sess.commit()

        assert deletion.nothing_remains(sess, store, trader_id) == []
        assert not store.exists(digest)
        assert sess.scalars(select(m.DeletionRecord)).one().id == record.id


def test_an_admin_import_puts_the_file_where_deletion_can_reach_it(engine, store,
                                                                   tmp_path):
    """The CLI wrote the raw file in plaintext, outside the encrypted store.

    Found by the deletion drill on the dev box: the record said
    "files_deleted: 0" after deleting an account whose tradebook had been
    imported by the admin command. The file was there, as `<digest>.csv`, in
    plaintext -- so it was neither encrypted at rest (ADR-007) nor reachable by
    the trader's own deletion, while the data-flow map said it was both.
    """
    import os

    from services.production.api import cli

    csv = tmp_path / "book.csv"
    csv.write_text(
        "Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,"
        "Trade Price,Trade Value,Status\n"
        "2026-10-14,09:20:01,WIDGETOIL 19 NOV 5000 CALL,BUY,INTRADAY,MCX,"
        "Commodity,100,52.00,5200.00,Traded\n"
        "2026-10-14,10:11:30,WIDGETOIL 19 NOV 5000 CALL,SELL,INTRADAY,MCX,"
        "Commodity,100,52.15,5215.00,Traded\n"
    )
    db = os.environ["SCOPE_DB"]
    cli.main(["--db", db, "create-trader", "--login-id", "cli", "--name", "C"])
    cli.main(["--db", db, "import", "--login-id", "cli", "--file", str(csv)])

    live = cli.file_store()
    with make_session(engine) as sess:
        digest = sess.scalars(select(m.RawFile.sha256)).one()
    assert live.exists(digest), "the file is not in the encrypted store"
    assert not list(cli.store_root().glob("*.csv")), "plaintext left behind"

    with make_session(engine) as sess:
        trader = sess.scalars(
            select(m.Trader).where(m.Trader.login_id == "cli")).one()
        record = deletion.delete_trader(sess, live, trader=trader)
        sess.commit()
    assert json.loads(record.what_removed)["files_deleted"] == 1
    assert not live.exists(digest)
