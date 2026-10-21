"""The Journal screens (PRD 7.2, 7.4, 11).

Four rules these tests hold the routes to, each of which the PRD states and none of
which a journal library would give us for free:

**Five on the surface.** A backfill generates every Journal and shows the latest
five, with a catch-up list for the rest. "A developer who renders sixty entries has
built a defect" -- so the defect is a failing test here.

**Opened, not generated.** `opened_at` is set the first time he reads one and never
again. The willingness-to-pay trigger counts opens, so overwriting it would make a
backfill look like engagement.

**Append-only fields with a derived phase.** A second answer is a new row pointing at
the one it supersedes, and `capture_phase` comes from the clock, never from a form
field. In v1 every Journal field is `after_close` by construction, because the
Journal exists only after an upload; the test pins that rather than trusting it.

**The question waits.** Three opens is not enough on its own: a second upload must
have happened, or fourteen days passed. A trader who backfills a year in one sitting
is not asked what he would pay for it.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.production.journal import generate as gen
from services.production.journal import prose
from services.production.mirror import loader
from services.shared.schemas import scope_v1 as s

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
PASSWORD = "a-long-enough-password"


@pytest.fixture()
def engine():
    import os
    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


def _seed(sess, login_id: str) -> m.Trader:
    """The contract fixture as one trader's history, with his Journals generated."""
    from services.production.accounts import auth

    trader = m.Trader(display_name="Fixture", login_id=login_id,
                      password_hash=auth.hash_password(PASSWORD),
                      created_at=datetime.now(UTC), development_data=True)
    sess.add(trader)
    sess.flush()
    raw = m.RawFile(trader_id=trader.id, sha256="f" * 64, original_name="f.csv",
                    size=1, stored_path="/tmp/f", uploaded_at=datetime.now(UTC))
    sess.add(raw)
    sess.flush()
    imp = m.Import(trader_id=trader.id, raw_file_id=raw.id, source_account="A",
                   adapter_id="dhan_tradebook_v1", adapter_version="1",
                   filemap_version="1", code_version="fixturesha",
                   outcome=s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS,
                   rows_in=40, rows_parsed=40, rows_excluded=0,
                   fees_available=False, version_no=1, trips_reconstructed=40,
                   density_default_unit="day", created_at=datetime.now(UTC))
    sess.add(imp)
    sess.flush()
    for t in json.loads(Path("tests/fixtures/mirror_contract/main.json").read_text()):
        sess.add(m.Trip(
            import_id=imp.id, trip_id=t["trip_id"], trading_day=t["trading_day"],
            exchange=t["exchange"], symbol=t["symbol"], segment="OPT",
            direction="LONG",
            entry_ts=datetime.fromisoformat(t["entry_ts"]),
            exit_ts=datetime.fromisoformat(t["exit_ts"]),
            quantity=t["quantity"], entry_price=Decimal(100), exit_price=Decimal(100),
            gross=Decimal(t["gross"]), fees=Decimal(t["fees"]), net=Decimal(t["net"]),
            fees_available=False,
            risk_unit_source=s.RiskUnitSourceV1(t["risk_unit_source"])))
    sess.add(m.ConsentEvent(trader_id=trader.id, purpose=s.ConsentPurpose.DIAGNOSIS,
                            scope="v1", terms_version="0-draft", granted=True,
                            at=datetime.now(UTC), method="web", wording_shown="x" * 100))
    sess.commit()

    trips, current = loader.load_for(sess, trader)
    gen.generate(sess, trader=trader, imp=current, trips=trips)
    sess.commit()
    return trader


def _sign_in(login_id: str) -> TestClient:
    client = TestClient(create_app())
    csrf = CSRF.search(client.get("/login").text).group(1)
    client.post("/login", data={"login_id": login_id, "password": PASSWORD,
                                "csrf_token": csrf}, follow_redirects=False)
    return client


@pytest.fixture()
def client(engine):
    with make_session(engine) as sess:
        _seed(sess, "fx")
    return _sign_in("fx")


def _journals(engine) -> list[m.Journal]:
    with make_session(engine) as sess:
        return list(sess.scalars(
            select(m.Journal).order_by(m.Journal.period_start.desc())).all())


def test_the_fixture_generates_more_journals_than_fit_on_the_surface(engine, client):
    """Without this the surface rule below would pass on an empty catch-up list."""
    assert len(_journals(engine)) > 5, "the eight-day fixture should backfill"


def test_the_list_shows_five_and_counts_the_rest(engine, client):
    body = client.get("/journals").text
    shown = {int(x) for x in re.findall(r'/journals/(\d+)"', body)}
    assert len(shown) == 5, f"{len(shown)} journals on the surface, not five"
    newest = [j.id for j in _journals(engine)][:5]
    assert shown == set(newest), "the surface must be the latest five"
    assert "catch-up" in body.lower() or "earlier journal" in body.lower()


def test_the_catch_up_list_holds_everything_behind_the_surface(engine, client):
    body = client.get("/journals/catch-up").text
    listed = {int(x) for x in re.findall(r'/journals/(\d+)"', body)}
    behind = {j.id for j in _journals(engine)[5:]}
    assert listed == behind


def test_a_journal_renders_the_prose_the_generator_wrote(engine, client):
    journal = _journals(engine)[0]
    with make_session(engine) as sess:
        stored = sess.get(m.Journal, journal.id)
        expected = prose.render(json.loads(stored.sections))
    body = client.get(f"/journals/{journal.id}").text
    opening = expected.split(".")[0]
    assert opening in body, f"expected the generated prose, starting {opening!r}"


def test_opening_a_journal_is_recorded_once(engine, client):
    journal_id = _journals(engine)[0].id
    client.get(f"/journals/{journal_id}")
    with make_session(engine) as sess:
        first = sess.get(m.Journal, journal_id).opened_at
    assert first is not None, "opened_at drives the willingness-to-pay trigger"
    client.get(f"/journals/{journal_id}")
    with make_session(engine) as sess:
        assert sess.get(m.Journal, journal_id).opened_at == first


def test_a_field_answer_is_stored_with_a_derived_phase(engine, client):
    journal = _journals(engine)[0]
    with make_session(engine) as sess:
        trip_id = json.loads(sess.get(m.Journal, journal.id).trip_ids)[0]
    page = client.get(f"/journals/{journal.id}").text
    client.post(f"/journals/{journal.id}/field",
                data={"field": "planned_sl", "trip_id": trip_id, "value": "250",
                      "csrf_token": CSRF.search(page).group(1)})
    with make_session(engine) as sess:
        entry = sess.scalars(select(m.JournalFieldEntry)).one()
    assert entry.value == "250"
    assert entry.capture_phase is s.CapturePhase.AFTER_CLOSE, (
        "a stop entered after the close is not a pre-trade commitment"
    )


def test_a_second_answer_is_a_version_not_an_edit(engine, client):
    journal = _journals(engine)[0]
    with make_session(engine) as sess:
        trip_id = json.loads(sess.get(m.Journal, journal.id).trip_ids)[0]
    for value in ("250", "300"):
        page = client.get(f"/journals/{journal.id}").text
        client.post(f"/journals/{journal.id}/field",
                    data={"field": "planned_sl", "trip_id": trip_id, "value": value,
                          "csrf_token": CSRF.search(page).group(1)})
    with make_session(engine) as sess:
        rows = list(sess.scalars(
            select(m.JournalFieldEntry).order_by(m.JournalFieldEntry.id)).all())
    assert [r.value for r in rows] == ["250", "300"]
    assert rows[1].previous_entry_id == rows[0].id, "the earlier answer is still there"


def test_a_field_answer_needs_its_csrf_token(engine, client):
    journal = _journals(engine)[0]
    response = client.post(f"/journals/{journal.id}/field",
                           data={"field": "planned_sl", "trip_id": "t01",
                                 "value": "250", "csrf_token": "forged"})
    assert response.status_code == 403
    with make_session(engine) as sess:
        assert sess.scalars(select(m.JournalFieldEntry)).all() == []


def test_the_question_does_not_arrive_on_a_single_backfill(engine, client):
    """Three opens, one upload, nothing aged: the trigger must not fire."""
    for journal in _journals(engine)[:3]:
        client.get(f"/journals/{journal.id}")
    body = client.get(f"/journals/{_journals(engine)[0].id}").text
    assert "500" not in body or "month" not in body.lower(), (
        "the willingness-to-pay question fired before a second upload or 14 days"
    )


def test_the_question_arrives_after_a_second_upload(engine, client):
    for journal in _journals(engine)[:3]:
        client.get(f"/journals/{journal.id}")
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "fx")).one()
        raw = m.RawFile(trader_id=trader.id, sha256="e" * 64, original_name="g.csv",
                        size=1, stored_path="/tmp/g", uploaded_at=datetime.now(UTC))
        sess.add(raw)
        sess.flush()
        sess.add(m.Import(trader_id=trader.id, raw_file_id=raw.id, source_account="A",
                          adapter_id="dhan_tradebook_v1", adapter_version="1",
                          filemap_version="1", code_version="fixturesha",
                          outcome=s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS,
                          rows_in=0, rows_parsed=0, rows_excluded=0,
                          fees_available=False, version_no=2, trips_reconstructed=0,
                          density_default_unit="day", created_at=datetime.now(UTC)))
        sess.commit()
    body = client.get(f"/journals/{_journals(engine)[0].id}").text
    assert "month" in body.lower() and "500" in body, "the question should be asked"


def test_a_journal_belongs_to_its_owner_only(engine, client):
    with make_session(engine) as sess:
        _seed(sess, "other")
        mine = sess.scalars(
            select(m.Journal).join(m.Trader, m.Journal.trader_id == m.Trader.id)
            .where(m.Trader.login_id == "fx")).first()
        theirs = sess.scalars(
            select(m.Journal).join(m.Trader, m.Journal.trader_id == m.Trader.id)
            .where(m.Trader.login_id == "other")).first()
        mine_id, theirs_id = mine.id, theirs.id
    assert client.get(f"/journals/{mine_id}").status_code == 200
    assert client.get(f"/journals/{theirs_id}").status_code == 404


def test_the_journals_need_signing_in(engine):
    with make_session(engine) as sess:
        _seed(sess, "fx")
    anonymous = TestClient(create_app())
    assert anonymous.get("/journals", follow_redirects=False).status_code in (302, 303)


def test_one_save_records_every_answer_for_that_trade(engine, client):
    """Three questions, one form, one button.

    The first version of this page gave each question its own form: three buttons
    a trade, twenty-four on a day with eight trades. That is data entry, not a
    journal, and it was only visible by looking at the page.
    """
    journal = _journals(engine)[0]
    with make_session(engine) as sess:
        trip_id = json.loads(sess.get(m.Journal, journal.id).trip_ids)[0]
    page = client.get(f"/journals/{journal.id}").text
    client.post(f"/journals/{journal.id}/field",
                data={"trip_id": trip_id, "planned_sl": "250",
                      "rationale": "range break", "stop_existed_at_entry": "yes",
                      "csrf_token": CSRF.search(page).group(1)})
    with make_session(engine) as sess:
        stored = {e.field: e.value for e in sess.scalars(
            select(m.JournalFieldEntry)).all()}
    assert stored == {"planned_sl": "250", "rationale": "range break",
                      "stop_existed_at_entry": "yes"}


def test_resaving_the_same_answers_adds_no_versions(engine, client):
    """Edits are append-only, so an unchanged field must not be written.

    One Save posts all three questions whether or not he touched them. Recording
    those would fill his own history with rows saying he did not change his mind,
    and the history is the thing PRD 7.4 exists to keep readable.
    """
    journal = _journals(engine)[0]
    with make_session(engine) as sess:
        trip_id = json.loads(sess.get(m.Journal, journal.id).trip_ids)[0]
    answers = {"trip_id": trip_id, "planned_sl": "250", "rationale": "range break",
               "stop_existed_at_entry": "yes"}
    for _ in range(3):
        page = client.get(f"/journals/{journal.id}").text
        client.post(f"/journals/{journal.id}/field",
                    data={**answers, "csrf_token": CSRF.search(page).group(1)})
    with make_session(engine) as sess:
        rows = list(sess.scalars(select(m.JournalFieldEntry)).all())
    assert len(rows) == 3, [(r.field, r.value) for r in rows]

    # Changing one of them is still a version, and only that one.
    page = client.get(f"/journals/{journal.id}").text
    client.post(f"/journals/{journal.id}/field",
                data={**answers, "planned_sl": "300",
                      "csrf_token": CSRF.search(page).group(1)})
    with make_session(engine) as sess:
        rows = list(sess.scalars(
            select(m.JournalFieldEntry).order_by(m.JournalFieldEntry.id)).all())
    assert len(rows) == 4
    assert rows[-1].field == "planned_sl" and rows[-1].value == "300"


def test_an_empty_answer_left_alone_is_not_recorded(engine, client):
    """Opening a Journal and saving without typing anything records nothing."""
    journal = _journals(engine)[0]
    with make_session(engine) as sess:
        trip_id = json.loads(sess.get(m.Journal, journal.id).trip_ids)[0]
    page = client.get(f"/journals/{journal.id}").text
    client.post(f"/journals/{journal.id}/field",
                data={"trip_id": trip_id, "planned_sl": "", "rationale": "",
                      "stop_existed_at_entry": "",
                      "csrf_token": CSRF.search(page).group(1)})
    with make_session(engine) as sess:
        assert sess.scalars(select(m.JournalFieldEntry)).all() == []


def test_the_page_has_one_form_for_each_trade(engine, client):
    journal = _journals(engine)[0]
    with make_session(engine) as sess:
        trades = len(json.loads(sess.get(m.Journal, journal.id).trip_ids))
    body = client.get(f"/journals/{journal.id}").text
    assert body.count('class="trade-form"') == trades

    # One a trade, plus one for the note, whose trip_id is empty because a note is
    # about the period and not about any single trade. Before this change there
    # were three forms a trade.
    assert body.count('name="trip_id"') == trades + 1
    assert body.count(">Save</button>") == trades + 1
