"""Moved out of tests/unit/api/test_rate_limits.py by TICKET-945, so that no test file imports another."""

from __future__ import annotations

import re

from sqlalchemy import select

from services.production.db import models as m
from services.production.db.session import make_session

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


PASSWORD = "a-long-enough-password"


def sign_up(client, login_id, password=PASSWORD):
    client.cookies.clear()
    csrf = CSRF.search(client.get("/signup").text).group(1)
    return client.post(
        "/signup",
        data={
            "login_id": login_id,
            "display_name": login_id,
            "password": password,
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )


def trader_id(engine, login_id) -> int:
    with make_session(engine) as sess:
        return sess.scalars(select(m.Trader.id).where(m.Trader.login_id == login_id)).one()


def stored_files(engine, login_id, count, at) -> None:
    """Files this account already sent, without paying to read each one."""
    owner = trader_id(engine, login_id)
    with make_session(engine) as sess:
        for n in range(count):
            sess.add(
                m.RawFile(
                    trader_id=owner,
                    sha256=f"{login_id}{at.isoformat()}{n}",
                    original_name="old.csv",
                    size=1,
                    stored_path="old",
                    uploaded_at=at,
                )
            )
        sess.commit()
