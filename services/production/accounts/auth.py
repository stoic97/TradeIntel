"""Passwords, sessions and CSRF.

Three decisions worth stating, because each is a place auth layers leak:

**argon2id, never the password.** The hash is the only form stored. A reset is a new
hash set by an admin command, not a recovered password, because no recoverable form
exists.

**Sessions are signed cookies, not rows.** A signed cookie needs no table and no
cleanup, and the signature makes forgery as hard as the secret key. The cost is that
a session cannot be revoked server-side for all devices; with few
accounts and a password reset available that is an acceptable v1 trade, and it is
recorded here rather than discovered later.

**CSRF tokens are signed and bound to the session.** A token from one session cannot
be posted in another, so a form stolen from a page the attacker rendered is useless.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from itsdangerous import BadSignature, URLSafeSerializer

MIN_PASSWORD_LENGTH = 12
SESSION_COOKIE = "scope_session"
CSRF_SALT = "scope-csrf"
SESSION_SALT = "scope-session"
ADMIN_SESSION_HOURS = 8  # an admin signed in longer ago than this signs in again (TICKET-1108)

_hasher = PasswordHasher()


class PasswordTooShort(Exception):
    """Raised with the length in the message, so the page can say it plainly."""


@dataclass(frozen=True)
class Session:
    trader_id: int
    csrf_secret: str
    account: str = ""  # account_mark of the account it was issued for
    signed_in_at: int | None = None  # UTC epoch seconds of the sign-in; None on an old cookie


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordTooShort(
            f"A password needs at least {MIN_PASSWORD_LENGTH} characters."
        )
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def account_mark(password_hash: str, secret_key: str) -> str:
    """What ties a session to one account rather than to its number.

    A trader id can be used again once its account has gone. The salted hash is unique to
    the account and changes with its password, so a reset ends older sessions too. A signed
    cookie can be read by whoever holds it, so it carries this, never the hash.
    """
    return hmac.new(secret_key.encode(), password_hash.encode(), hashlib.sha256).hexdigest()


def clock() -> int:
    """Now, in UTC epoch seconds. The one clock sessions are stamped and judged by."""
    return int(time.time())


def new_session(trader_id: int, password_hash: str, secret_key: str) -> Session:
    """Only a sign-in or a sign-up makes one, so ``signed_in_at`` is the moment of that."""
    return Session(trader_id=trader_id, csrf_secret=secrets.token_urlsafe(16),
                   account=account_mark(password_hash, secret_key), signed_in_at=clock())


def admin_signin_fresh(session: Session, now: int) -> bool:
    """Whether this sign-in is recent enough to open /admin. No sign-in time is not fresh."""
    if session.signed_in_at is None:
        return False
    return now - session.signed_in_at < ADMIN_SESSION_HOURS * 60 * 60


def session_is_for(session: Session, password_hash: str, secret_key: str) -> bool:
    return secrets.compare_digest(session.account, account_mark(password_hash, secret_key))


def seal_session(session: Session, secret_key: str) -> str:
    serializer = URLSafeSerializer(secret_key, salt=SESSION_SALT)
    payload = {"t": session.trader_id, "c": session.csrf_secret, "a": session.account}
    if session.signed_in_at is not None:
        payload["i"] = session.signed_in_at
    return serializer.dumps(payload)


def open_session(raw: str | None, secret_key: str) -> Session | None:
    if not raw:
        return None
    serializer = URLSafeSerializer(secret_key, salt=SESSION_SALT)
    try:
        data = serializer.loads(raw)
    except BadSignature:
        return None
    # A cookie from before the mark has none, matches no account, and signs in again.
    signed_in_at = data.get("i")
    if not isinstance(signed_in_at, int) or isinstance(signed_in_at, bool):
        signed_in_at = None  # an old cookie: a trader reads on, an admin signs in again
    return Session(trader_id=int(data["t"]), csrf_secret=str(data["c"]),
                   account=str(data.get("a", "")), signed_in_at=signed_in_at)


def csrf_token(session: Session | None, secret_key: str) -> str:
    """A token bound to this session, or to the anonymous one before login."""
    serializer = URLSafeSerializer(secret_key, salt=CSRF_SALT)
    return serializer.dumps(session.csrf_secret if session else "anonymous")


def csrf_ok(token: str | None, session: Session | None, secret_key: str) -> bool:
    if not token:
        return False
    serializer = URLSafeSerializer(secret_key, salt=CSRF_SALT)
    try:
        bound_to = serializer.loads(token)
    except BadSignature:
        return False
    expected = session.csrf_secret if session else "anonymous"
    return secrets.compare_digest(str(bound_to), expected)
