"""Passwords, sessions and CSRF.

Three decisions worth stating, because each is a place auth layers leak:

**argon2id, never the password.** The hash is the only form stored. A reset is a new
hash set by an admin command, not a recovered password, because no recoverable form
exists.

**Sessions are signed cookies, not rows.** A signed cookie needs no table and no
cleanup, and the signature makes forgery as hard as the secret key. The cost is that
a session cannot be revoked server-side for all devices; with a handful of invited
accounts and a password reset available that is an acceptable v1 trade, and it is
recorded here rather than discovered later.

**CSRF tokens are signed and bound to the session.** A token from one session cannot
be posted in another, so a form stolen from a page the attacker rendered is useless.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from itsdangerous import BadSignature, URLSafeSerializer

MIN_PASSWORD_LENGTH = 12
SESSION_COOKIE = "scope_session"
CSRF_SALT = "scope-csrf"
SESSION_SALT = "scope-session"

_hasher = PasswordHasher()


class PasswordTooShort(Exception):
    """Raised with the length in the message, so the page can say it plainly."""


@dataclass(frozen=True)
class Session:
    trader_id: int
    csrf_secret: str


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


def new_session(trader_id: int) -> Session:
    return Session(trader_id=trader_id, csrf_secret=secrets.token_urlsafe(16))


def seal_session(session: Session, secret_key: str) -> str:
    serializer = URLSafeSerializer(secret_key, salt=SESSION_SALT)
    return serializer.dumps({"t": session.trader_id, "c": session.csrf_secret})


def open_session(raw: str | None, secret_key: str) -> Session | None:
    if not raw:
        return None
    serializer = URLSafeSerializer(secret_key, salt=SESSION_SALT)
    try:
        data = serializer.loads(raw)
    except BadSignature:
        return None
    return Session(trader_id=int(data["t"]), csrf_secret=str(data["c"]))


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
