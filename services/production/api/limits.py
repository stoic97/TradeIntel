"""The caps between an open sign-up and a small box.

Anyone with the address can make an account and send a file, on one process with one
CPU. Four things stop that being a way to take the app down, each refusing in a sentence
that says what happened and when to try again:

**Sign-ups per connection per hour.** Counted here, in memory, and nowhere else. A
visitor's address is never written down: not in the database, not in a file. A restart
forgets every count, which costs a stranger's next hour and costs a trader nothing.

**Uploads per account per day.** Counted from ``RawFile``, so a restart forgets nothing,
and a file that added nothing (the same bytes again) uses nothing up. Everything that
stores a file writes that row, the charges step included.

**A body too big to read.** The form parser writes a whole upload to temporary files
before any route runs, so a route's own byte check can't protect the disk. ``BodyCap``
reads the stated length first and refuses before a byte of the body is read. It answers
everyone, signed in or not, which is the point: a stranger doesn't need an account to send
a body.

**The disk.** Past a set share, no new files. Nobody else is told, so it also goes in the
log.

**Failed sign-ins per login id and per connection per hour.** In memory too, so nothing
is written down, and only a failure counts.

The numbers are in ``journal/constants.py`` with their arguments.
"""

from __future__ import annotations

import ipaddress
import logging
import math
import shutil
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from services.production.db import models as m
from services.production.journal import constants as k

logger = logging.getLogger(__name__)

HOUR_SECONDS = 60 * 60
DAY_SECONDS = 24 * HOUR_SECONDS
IPV6_CUSTOMER_PREFIX = 64  # one IPv6 customer is handed a whole /64
INDIA = ZoneInfo("Asia/Kolkata")

TOO_LARGE = (
    f"That file is larger than {k.MAX_UPLOAD_BYTES // (1024 * 1024)} MB. Every tradebook we "
    "have seen is far smaller — if yours is genuinely this big, tell us and we will raise it."
)
DISK_NEARLY_FULL = (
    "Our storage is nearly full, so we cannot take new files right now. "
    "Nothing was added. Try again tomorrow."
)


def signups_refused(wait_seconds: int) -> str:
    minutes = math.ceil(wait_seconds / 60)
    unit = "minute" if minutes == 1 else "minutes"
    return ("Too many accounts have been made from this connection in the last hour. "
            f"Try again in {minutes} {unit}.")


def logins_refused(wait_seconds: int) -> str:
    """The same words whether or not the login id exists."""
    minutes = math.ceil(wait_seconds / 60)
    unit = "minute" if minutes == 1 else "minutes"
    return f"Too many failed sign-ins. Try again in {minutes} {unit}."


def uploads_refused() -> str:
    return (f"You have sent {k.UPLOADS_PER_ACCOUNT_PER_DAY} files today, the most one account "
            "can send in a day. Nothing was added. Try again tomorrow.")


class HourlyCount:
    """How many times each key did something in the last hour. In memory, on purpose.

    One process (ADR-007), so one count. Sync routes run on a thread pool, hence the lock.
    Checking and adding are separate because only a sign-up that made an account counts,
    so two sign-ups at the same moment can pass the cap by one, which is harmless.
    """

    def __init__(self, cap: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._cap = cap
        self._clock = clock
        self._seen: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _forget_old(self, now: float) -> None:
        for key in list(self._seen):
            times = self._seen[key]
            while times and now - times[0] >= HOUR_SECONDS:
                times.popleft()
            if not times:
                del self._seen[key]

    def wait_seconds(self, key: str) -> int:
        """Seconds until this key may go again; 0 if it may go now."""
        with self._lock:
            now = self._clock()
            self._forget_old(now)
            times = self._seen.get(key)
            if times is None or len(times) < self._cap:
                return 0
            return math.ceil(times[0] + HOUR_SECONDS - now)

    def add(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            self._forget_old(now)
            self._seen.setdefault(key, deque()).append(now)

    def held(self) -> set[str]:
        with self._lock:
            return set(self._seen)


def network(host: str | None) -> str:
    """The key a connection is counted under: its address, or its /64 on IPv6."""
    if not host:
        return "unknown"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if address.version == 6:
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f"{address}/{IPV6_CUSTOMER_PREFIX}", strict=False))
    return str(address)


def connection(request: Request) -> str:
    """Who is asking. Behind Caddy, uvicorn has already put the visitor's address here."""
    return network(request.client.host if request.client else None)


def disk_used_percent(path: Path) -> float:
    """How full the disk under ``path`` is, the way ``df`` counts it, free meaning usable."""
    folder = Path(path)
    while not folder.exists() and folder != folder.parent:
        folder = folder.parent
    usage = shutil.disk_usage(folder)
    return usage.used * 100 / (usage.used + usage.free)


def _disk_nearly_full(path: Path) -> bool:
    try:
        used = disk_used_percent(path)
    except OSError:
        # A check that can't read the disk says nothing about it, and shutting uploads for
        # that would be the check taking the app down.
        logger.warning("could not read the disk under %s; uploads stay open", path)
        return False
    if used >= k.UPLOADS_REFUSED_AT_DISK_PERCENT:
        logger.warning("uploads refused: disk is %.1f%% full (line is %d%%)",
                       used, k.UPLOADS_REFUSED_AT_DISK_PERCENT)
        return True
    return False


def _start_of_today() -> datetime:
    return datetime.now(INDIA).replace(hour=0, minute=0, second=0, microsecond=0)


def _files_today(sess, trader: m.Trader) -> int:
    since = _start_of_today().astimezone(UTC)
    return sess.scalar(
        select(func.count()).select_from(m.RawFile)
        .where(m.RawFile.trader_id == trader.id, m.RawFile.uploaded_at >= since)
    )


@dataclass(frozen=True)
class Refusal:
    status_code: int
    sentence: str
    retry_after: int


def upload_refusal(request: Request, sess, trader: m.Trader) -> Refusal | None:
    """Why this file can't be taken before it is read, or None if it can."""
    if _disk_nearly_full(request.app.state.settings.file_store):
        return Refusal(503, DISK_NEARLY_FULL, DAY_SECONDS)
    if _files_today(sess, trader) >= k.UPLOADS_PER_ACCOUNT_PER_DAY:
        tomorrow = _start_of_today() + timedelta(days=1)
        wait = math.ceil((tomorrow - datetime.now(INDIA)).total_seconds())
        return Refusal(429, uploads_refused(), max(wait, 1))
    return None


def with_retry_after(response, seconds: int):
    response.headers["Retry-After"] = str(seconds)
    return response


def plain_refusal(_scope: Scope) -> HTMLResponse:
    return HTMLResponse(TOO_LARGE, status_code=413)


class BodyCap:
    """Refuse a request whose body is past the cap, before reading any of it.

    A stated length is believed, because uvicorn holds the sender to it. With no stated
    length, which no browser sends, the bytes are counted as they arrive and the read
    stops at the cap, so the most that reaches the disk is the cap.
    """

    def __init__(self, app: ASGIApp, refuse: Callable[[Scope], HTMLResponse]) -> None:
        self.app = app
        self.refuse = refuse

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        stated = dict(scope["headers"]).get(b"content-length")
        if stated is not None and stated.isdigit():
            if int(stated) > k.MAX_REQUEST_BYTES:
                await self.refuse(scope)(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return

        read = 0

        async def counted() -> Message:
            nonlocal read
            message = await receive()
            read += len(message.get("body", b""))
            if read > k.MAX_REQUEST_BYTES:
                raise HTTPException(status_code=413, detail=TOO_LARGE)
            return message

        await self.app(scope, counted, send)
