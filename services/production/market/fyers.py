"""The server's connection to Fyers, for market data only (TICKET-998, ADR 008).

**The app's keys** come from ``/etc/scope/scope.env``: ``FYERS_APP_ID``, ``FYERS_SECRET_KEY`` and
``FYERS_REDIRECT_URI``, the address the app is registered with in the Fyers dashboard. None of them
is in the repository. Without all three, ``from_env`` is None: the admin card says Fyers isn't set
up here, and the sync does nothing. Staging gets no keys.

**Logging in** is the broker's own page. When the registered address is the server's
``/admin/fyers/callback``, the broker comes straight back with the day's code (one click). When it
is anything else (the existing app's lands on google.com), the admin pastes the address bar into
the card. Either way ``exchange`` turns the code into the day's token, which goes straight to
``token.save`` and nowhere else.

**Pacing.** ``Paced`` wraps the history client: at most one request a second, and a busy answer
(429) is waited out, 2 s then 4, 8 and 16, before it is handed back for the next run. The clock and
the sleep are passed in, so tests never wait.
"""

from __future__ import annotations

import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass

CALLBACK = "/admin/fyers/callback"
BUSY = 429
BACKOFF = (2, 4, 8, 16)


class ExchangeFailed(Exception):
    """The broker wouldn't turn the code into a token. The message never holds the code."""


@dataclass(frozen=True)
class FyersApp:
    app_id: str
    secret: str
    redirect_uri: str

    @property
    def comes_back_here(self) -> bool:
        """Whether the broker's login returns to the server, so one click is enough."""
        return self.redirect_uri.rstrip("/").endswith(CALLBACK)


def from_env() -> FyersApp | None:
    keys = [os.environ.get(k, "").strip() for k in ("FYERS_APP_ID", "FYERS_SECRET_KEY", "FYERS_REDIRECT_URI")]
    return FyersApp(*keys) if all(keys) else None


def _session(app: FyersApp, state: str | None = None):
    from fyers_apiv3 import fyersModel

    return fyersModel.SessionModel(client_id=app.app_id, secret_key=app.secret, redirect_uri=app.redirect_uri,
                                   response_type="code", grant_type="authorization_code", state=state)


def login_url(app: FyersApp, state: str) -> str:
    """The broker's login page for this app. It carries no secret."""
    return _session(app, state).generate_authcode()


def exchange(app: FyersApp, code: str) -> str:
    """The day's token for this code, or ExchangeFailed. Codes last minutes and work once."""
    session = _session(app)
    session.set_token(code)
    try:
        answer = session.generate_token()
    except Exception as exc:  # noqa: BLE001 - a network failure is a refusal here, not a crash
        raise ExchangeFailed(f"the broker couldn't be reached ({exc.__class__.__name__})") from None
    if isinstance(answer, dict) and answer.get("s") == "ok" and answer.get("access_token"):
        return answer["access_token"]
    raise ExchangeFailed("the code has expired or was used already")


def history_client(app: FyersApp, access_token: str):
    from fyers_apiv3 import fyersModel

    logs = tempfile.mkdtemp(prefix="fyers-")  # the library writes request logs; keep them out of the app
    return fyersModel.FyersModel(client_id=app.app_id, token=access_token, is_async=False, log_path=logs + "/")


class Paced:
    """A history client asked at most once a second, waiting out a busy broker."""

    def __init__(self, client, *, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep, gap: float = 1.0) -> None:
        self.client, self.clock, self.sleep, self.gap = client, clock, sleep, gap
        self._last: float | None = None

    def _wait(self) -> None:
        if self._last is not None:
            left = self.gap - (self.clock() - self._last)
            if left > 0:
                self.sleep(left)
        self._last = self.clock()

    def history(self, data: dict) -> dict:
        self._wait()
        answer = self.client.history(data)
        for pause in BACKOFF:
            if not (isinstance(answer, dict) and answer.get("code") == BUSY):
                break
            self.sleep(pause)
            self._last = self.clock()
            answer = self.client.history(data)
        return answer
