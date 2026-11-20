"""Moved out of tests/unit/api/test_journals.py by TICKET-945, so that no test file imports another.

Fixtures are not kept here: each fixture that lived in that file is a plain function
below, and the fixture of the same name calls it.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.accounts.consent import CURRENT as CONSENT_TEXT
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.production.journal import generate as gen
from services.production.mirror import loader
from services.shared.schemas import scope_v1 as s

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


PASSWORD = "a-long-enough-password"


def journals_engine():
    import os

    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


def _seed(sess, login_id: str) -> m.Trader:
    """The contract fixture as one trader's history, with his Journals generated."""
    from services.production.accounts import auth

    trader = m.Trader(
        display_name="Fixture",
        login_id=login_id,
        password_hash=auth.hash_password(PASSWORD),
        created_at=datetime.now(UTC),
        development_data=True,
    )
    sess.add(trader)
    sess.flush()
    raw = m.RawFile(
        trader_id=trader.id,
        sha256="f" * 64,
        original_name="f.csv",
        size=1,
        stored_path="/tmp/f",
        uploaded_at=datetime.now(UTC),
    )
    sess.add(raw)
    sess.flush()
    imp = m.Import(
        trader_id=trader.id,
        raw_file_id=raw.id,
        source_account="A",
        adapter_id="dhan_tradebook_v1",
        adapter_version="1",
        filemap_version="1",
        code_version="fixturesha",
        outcome=s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS,
        rows_in=40,
        rows_parsed=40,
        rows_excluded=0,
        fees_available=False,
        version_no=1,
        trips_reconstructed=40,
        density_default_unit="day",
        created_at=datetime.now(UTC),
    )
    sess.add(imp)
    sess.flush()
    for t in json.loads(Path("tests/fixtures/mirror_contract/main.json").read_text()):
        sess.add(
            m.Trip(
                import_id=imp.id,
                trip_id=t["trip_id"],
                trading_day=t["trading_day"],
                exchange=t["exchange"],
                symbol=t["symbol"],
                segment="OPT",
                direction="LONG",
                entry_ts=datetime.fromisoformat(t["entry_ts"]),
                exit_ts=datetime.fromisoformat(t["exit_ts"]),
                quantity=t["quantity"],
                entry_price=Decimal(100),
                exit_price=Decimal(100),
                gross=Decimal(t["gross"]),
                fees=Decimal(t["fees"]),
                net=Decimal(t["net"]),
                fees_available=False,
                risk_unit_source=s.RiskUnitSourceV1(t["risk_unit_source"]),
            )
        )
    sess.add(
        m.ConsentEvent(
            trader_id=trader.id,
            purpose=s.ConsentPurpose.DIAGNOSIS,
            scope="v1",
            terms_version=CONSENT_TEXT.version,
            granted=True,
            at=datetime.now(UTC),
            method="web",
            wording_shown="x" * 100,
        )
    )
    sess.commit()

    trips, current = loader.load_for(sess, trader)
    gen.generate(sess, trader=trader, imp=current, trips=trips)
    sess.commit()
    return trader


def _sign_in(login_id: str) -> TestClient:
    client = TestClient(create_app())
    csrf = CSRF.search(client.get("/login").text).group(1)
    client.post(
        "/login",
        data={"login_id": login_id, "password": PASSWORD, "csrf_token": csrf},
        follow_redirects=False,
    )
    return client


def journals_client(engine):
    with make_session(engine) as sess:
        _seed(sess, "fx")
    return _sign_in("fx")


def _journals(engine) -> list[m.Journal]:
    with make_session(engine) as sess:
        return list(sess.scalars(select(m.Journal).order_by(m.Journal.period_start.desc())).all())
