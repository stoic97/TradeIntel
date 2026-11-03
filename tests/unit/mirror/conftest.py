"""Shared setup for the Mirror tests: a trader whose history is the contract fixture.

Moved here from test_page.py so the wording-reference test and, later, the Scope
page tests read the same 40-trip history through the same login, rather than each
keeping a copy that can drift. test_dwell.py keeps fixtures of its own, which take
precedence over these by pytest's rules.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.shared.schemas import scope_v1 as s_enums

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


@pytest.fixture()
def engine():
    import os
    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


@pytest.fixture()
def client(engine):
    """A trader with the contract fixture loaded as his history."""
    import json
    from datetime import UTC, datetime
    from pathlib import Path

    from services.production.accounts import auth

    with make_session(engine) as sess:
        trader = m.Trader(display_name="Fixture", login_id="fx",
                          password_hash=auth.hash_password("a-long-enough-password"),
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
                       outcome=s_enums.ImportOutcome.ACCEPTED_PARTIAL_FIELDS,
                       rows_in=40, rows_parsed=40,
                       rows_excluded=0, fees_available=False, version_no=1,
                       trips_reconstructed=40,
                       density_default_unit="day", created_at=datetime.now(UTC))
        sess.add(imp)
        sess.flush()
        trips = json.loads(Path("tests/fixtures/mirror_contract/main.json").read_text())
        for t in trips:
            sess.add(m.Trip(
                import_id=imp.id, trip_id=t["trip_id"], trading_day=t["trading_day"],
                exchange=t["exchange"], symbol=t["symbol"], segment="OPT",
                direction="LONG",
                entry_ts=datetime.fromisoformat(t["entry_ts"]),
                exit_ts=datetime.fromisoformat(t["exit_ts"]),
                quantity=t["quantity"],
                entry_price=Decimal(100), exit_price=Decimal(100),
                gross=Decimal(t["gross"]), fees=Decimal(t["fees"]),
                net=Decimal(t["net"]),
                fees_available=False, risk_unit_source=s_enums.RiskUnitSourceV1(t["risk_unit_source"])))
        sess.add(m.ConsentEvent(trader_id=trader.id,
                                purpose=s_enums.ConsentPurpose.DIAGNOSIS, scope="v1",
                                terms_version="0-draft", granted=True,
                                at=datetime.now(UTC), method="web", wording_shown="x" * 100))
        sess.commit()

    client = TestClient(create_app())
    csrf = CSRF.search(client.get("/login").text).group(1)
    client.post("/login", data={"login_id": "fx",
                                "password": "a-long-enough-password",
                                "csrf_token": csrf}, follow_redirects=False)
    return client
