"""The admin command line.

Only the invite command is covered here. The import path is exercised through the
upload route, and the two commands that touch a password deliberately cannot produce
a trader who signs in -- a trader sets his own password through his invite.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import select

from services.production.api import cli
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations


def test_invite_mints_a_code_and_prints_where_it_opens(capsys):
    cli.main(["--db", os.environ["SCOPE_DB"], "invite", "--code", "DEV-9"])
    assert "/invite/DEV-9" in capsys.readouterr().out

    engine = make_engine(os.environ["SCOPE_DB"])
    run_migrations(engine)
    with make_session(engine) as sess:
        stored = sess.scalars(
            select(m.InviteCode).where(m.InviteCode.code == "DEV-9")).one()
    assert stored.code == "DEV-9"


def test_a_code_that_already_exists_is_refused(capsys):
    """Silently reusing a code would hand two traders the same door."""
    args = ["--db", os.environ["SCOPE_DB"], "invite", "--code", "DEV-9"]
    cli.main(args)
    with pytest.raises(SystemExit):
        cli.main(args)


def _trader(engine, login_id: str) -> m.Trader:
    with make_session(engine) as sess:
        return sess.scalars(
            select(m.Trader).where(m.Trader.login_id == login_id)).one()


def test_classify_marks_an_existing_account_as_development_data(capsys):
    """An account is created through an invite, where nobody is asked this.

    Before this command the flag could only be set at creation, so the one account
    that needs it -- a partner whose history is development data -- could not get
    it without hand-written SQL.
    """
    db = os.environ["SCOPE_DB"]
    engine = make_engine(db)
    run_migrations(engine)
    from datetime import UTC, datetime
    with make_session(engine) as sess:
        sess.add(m.Trader(display_name="R", login_id="rikk",
                          password_hash="x", created_at=datetime.now(UTC),
                          development_data=False))
        sess.commit()

    cli.main(["--db", db, "classify", "--login-id", "rikk", "--development-data"])
    out = capsys.readouterr().out
    assert _trader(engine, "rikk").development_data is True
    assert "addendum" in out, "decision 21: that partner is owed one"

    cli.main(["--db", db, "classify", "--login-id", "rikk", "--real"])
    assert _trader(engine, "rikk").development_data is False


def test_classify_records_who_changed_it(capsys):
    db = os.environ["SCOPE_DB"]
    engine = make_engine(db)
    run_migrations(engine)
    from datetime import UTC, datetime
    with make_session(engine) as sess:
        sess.add(m.Trader(display_name="R", login_id="rikk",
                          password_hash="x", created_at=datetime.now(UTC),
                          development_data=False))
        sess.commit()
    cli.main(["--db", db, "classify", "--login-id", "rikk", "--development-data"])
    with make_session(engine) as sess:
        actions = [a.action for a in sess.scalars(select(m.AdminAction)).all()]
    assert "classify_development_data" in actions


def test_classify_refuses_an_account_that_does_not_exist():
    with pytest.raises(SystemExit):
        cli.main(["--db", os.environ["SCOPE_DB"], "classify",
                  "--login-id", "nobody", "--development-data"])
