"""The day's Fyers token, handled like a key (TICKET-998).

The token can place orders on the account it belongs to. So:

* it is stored only as Fernet ciphertext under the file key (``SCOPE_FILE_KEY``, as the file
  store encrypts tradebooks), in one row that a new login replaces;
* ``read`` is the one place it is decrypted, and only the sync calls it;
* it never goes into a log, a page, an error message or the admin trail. Nothing here logs.

Its expiry is read from the token's own JWT ``exp`` (Fyers' day tokens end at 06:00 IST the next
morning), so the admin card can say how long it lasts without decrypting it.

A login started from the card carries a ``state``: the admin's actor and the time, signed with the
app's secret key. The broker's redirect back is a GET that can't carry the page's CSRF token, so
the signed state is what ties it to the admin who asked, for ten minutes.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.production.db import models as m

ZONE = ZoneInfo("Asia/Kolkata")
STATE_LASTS = timedelta(minutes=10)


def jwt_expiry(token: str) -> datetime | None:
    """The token's ``exp``, or None when it isn't a JWT carrying one."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return datetime.fromtimestamp(int(claims["exp"]), UTC)
    except (IndexError, ValueError, KeyError, TypeError, binascii.Error, json.JSONDecodeError):
        return None


def auth_code_from(address: str) -> tuple[str | None, str | None]:
    """The ``auth_code`` and ``state`` in the address the broker's login ended on."""
    query = parse_qs(urlparse((address or "").strip()).query)
    code = (query.get("auth_code") or [None])[0]
    state = (query.get("state") or [None])[0]
    return (code, state) if code else (None, None)


def save(sess: Session, file_key: str, token: str, *, actor: str, now: datetime) -> datetime:
    """Encrypt and keep the token in the one row; returns when it expires."""
    expires = jwt_expiry(token)
    if expires is None:
        raise ValueError("the broker's answer is not a token with an expiry")
    ciphertext = Fernet(file_key.encode()).encrypt(token.encode()).decode()
    row = sess.scalars(select(m.MarketToken)).first()
    if row is None:
        sess.add(m.MarketToken(ciphertext=ciphertext, expires_at=expires, connected_at=now, connected_by=actor))
    else:
        row.ciphertext, row.expires_at, row.connected_at, row.connected_by = ciphertext, expires, now, actor
    sess.flush()
    return expires


def read(sess: Session, file_key: str, *, now: datetime) -> str | None:
    """The token, for the sync only: None when there is none, it has expired, or the key can't open it."""
    row = sess.scalars(select(m.MarketToken)).first()
    if row is None or row.expires_at <= now:
        return None
    try:
        return Fernet(file_key.encode()).decrypt(row.ciphertext.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def _clock(at: datetime, now: datetime) -> str:
    here, today = at.astimezone(ZONE), now.astimezone(ZONE).date()
    if here.date() == today:
        return f"{here:%H:%M} today"
    if here.date() == today + timedelta(days=1):
        return f"{here:%H:%M} tomorrow"
    return f"{here:%H:%M} on {here:%d %b %Y}"


def state_line(expires: datetime | None, *, now: datetime) -> str:
    """What the card says about the token, from its expiry alone."""
    if expires is None:
        return "never connected"
    if expires <= now:
        return f"expired at {_clock(expires, now)}; log in again"
    return f"connected until {_clock(expires, now)}"


def _sign(secret: str, actor: str, stamp: str) -> str:
    return hmac.new(secret.encode(), f"fyers-login|{actor}|{stamp}".encode(), hashlib.sha256).hexdigest()[:32]


def sign_state(secret: str, actor: str, now: datetime) -> str:
    stamp = str(int(now.timestamp()))
    return f"{stamp}.{_sign(secret, actor, stamp)}"


def state_ok(secret: str, actor: str, state: str | None, now: datetime) -> bool:
    """Whether this state was signed for this admin in the last ten minutes."""
    stamp, _, mac = (state or "").partition(".")
    if not stamp.isdigit() or not hmac.compare_digest(mac, _sign(secret, actor, stamp)):
        return False
    return timedelta(0) <= now - datetime.fromtimestamp(int(stamp), UTC) <= STATE_LASTS
