"""TICKET-998: the day's Fyers token is handled like a key.

It can place orders, so it is stored encrypted with the file key, decrypted only for the sync,
and never written to a log, a page, an error or the admin trail. Every token here is made up.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select

from services.production.db import models as m
from services.production.db.session import make_session, run_migrations
from services.production.market import token as T

KEY = Fernet.generate_key().decode()
NOW = datetime(2026, 11, 20, 9, 30, tzinfo=UTC)  # 15:00 IST


def made_up_token(expires: datetime) -> str:
    def part(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{part({'alg': 'none'})}.{part({'exp': int(expires.timestamp()), 'sub': 'made-up'})}.not-a-signature"


def session():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    return make_session(engine)


TOMORROW_6 = datetime(2026, 11, 21, 0, 30, tzinfo=UTC)  # 06:00 IST on 21 Nov


def test_the_expiry_is_read_from_the_tokens_own_exp():
    assert T.jwt_expiry(made_up_token(TOMORROW_6)) == TOMORROW_6
    assert T.jwt_expiry("not a token") is None


def test_the_auth_code_is_read_from_the_whole_address_bar():
    pasted = "https://www.google.com/?s=ok&code=200&auth_code=eyJ.made.up&state=1234.abcd"
    assert T.auth_code_from(pasted) == ("eyJ.made.up", "1234.abcd")
    assert T.auth_code_from("  " + pasted + "\n") == ("eyJ.made.up", "1234.abcd")
    assert T.auth_code_from("https://www.google.com/?s=error&code=-413") == (None, None)
    assert T.auth_code_from("") == (None, None)


def test_the_token_is_stored_encrypted_in_one_row_and_read_back_only_with_the_key():
    tok = made_up_token(TOMORROW_6)
    with session() as sess:
        T.save(sess, KEY, tok, actor="trader:1", now=NOW)
        T.save(sess, KEY, tok, actor="trader:1", now=NOW)  # a second login replaces the first
        sess.commit()
        rows = sess.scalars(select(m.MarketToken)).all()
        assert len(rows) == 1
        assert tok not in rows[0].ciphertext and rows[0].ciphertext
        assert rows[0].expires_at == TOMORROW_6
        assert T.read(sess, KEY, now=NOW) == tok
        assert T.read(sess, Fernet.generate_key().decode(), now=NOW) is None


def test_an_expired_or_missing_token_reads_as_none():
    with session() as sess:
        assert T.read(sess, KEY, now=NOW) is None
        T.save(sess, KEY, made_up_token(NOW - timedelta(minutes=1)), actor="trader:1", now=NOW)
        assert T.read(sess, KEY, now=NOW) is None


def test_the_state_says_never_connected_until_or_expired():
    assert T.state_line(None, now=NOW) == "never connected"
    assert T.state_line(TOMORROW_6, now=NOW) == "connected until 06:00 tomorrow"
    assert T.state_line(datetime(2026, 11, 20, 12, 30, tzinfo=UTC), now=NOW) == "connected until 18:00 today"
    assert T.state_line(NOW - timedelta(hours=1), now=NOW) == "expired at 14:00 today; log in again"


def test_a_login_state_is_signed_for_one_admin_and_lasts_ten_minutes():
    state = T.sign_state("secret", "trader:1", NOW)
    assert T.state_ok("secret", "trader:1", state, NOW + timedelta(minutes=9))
    assert not T.state_ok("secret", "trader:1", state, NOW + timedelta(minutes=11))
    assert not T.state_ok("secret", "trader:2", state, NOW)
    assert not T.state_ok("other", "trader:1", state, NOW)
    assert not T.state_ok("secret", "trader:1", "made.up", NOW)
    assert not T.state_ok("secret", "trader:1", None, NOW)
