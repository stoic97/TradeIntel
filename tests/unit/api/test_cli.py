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
