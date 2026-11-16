"""Moved out of tests/unit/api/test_deletion_page.py by TICKET-945, so that no test file imports another.

Fixtures are not kept here: each fixture that lived in that file is a plain function
below, and the fixture of the same name calls it.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from services.production.accounts.consent import CURRENT as CONSENT_TEXT
from services.production.accounts.file_store import FileStore
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.shared.schemas import scope_v1 as s

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


PASSWORD = "a-long-enough-password"


def deletion_page_engine():
    import os
    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


def deletion_page_store():
    import os
    from pathlib import Path
    return FileStore(Path(os.environ["SCOPE_FILES"]), os.environ["SCOPE_FILE_KEY"])


def deletion_page_client(engine, store):
    from services.production.accounts import auth
    with make_session(engine) as sess:
        trader = m.Trader(display_name="R", login_id="rikk",
                          password_hash=auth.hash_password(PASSWORD),
                          created_at=datetime.now(UTC), development_data=True)
        sess.add(trader)
        sess.flush()
        stored = store.put(b"his export\n")
        sess.add(m.RawFile(trader_id=trader.id, sha256=stored.sha256,
                           original_name="t.csv", size=stored.size,
                           stored_path=str(stored.path),
                           uploaded_at=datetime.now(UTC)))
        sess.add(m.ConsentEvent(trader_id=trader.id,
                                purpose=s.ConsentPurpose.DIAGNOSIS, scope="v1",
                                terms_version=CONSENT_TEXT.version, granted=True,
                                at=datetime.now(UTC), method="web",
                                wording_shown="x" * 100))
        sess.commit()
    c = TestClient(create_app())
    csrf = CSRF.search(c.get("/login").text).group(1)
    c.post("/login", data={"login_id": "rikk", "password": PASSWORD,
                           "csrf_token": csrf}, follow_redirects=False)
    return c
