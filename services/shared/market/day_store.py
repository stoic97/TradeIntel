"""Market data stored by day: one gzip file per underlying per trading day (TICKET-997).

**Layout.** ``<root>/<UNDERLYING>/<YYYY>/<YYYY-MM-DD>.csv.gz``, and beside the year folders
``<root>/<UNDERLYING>/manifest.json``. A day file is the series' header line and that day's rows,
exactly as the series wrote them, compressed at level 6 with no time in the gzip header, so the
same day always makes the same bytes. A page or a count reads one day at a time, so nothing ever
needs the whole series: there is no work when the server starts, and adding a day writes one
small file.

**Checked when written, not when read.** ``DayStore.put`` is the one way a day is written. It
refuses, naming the day and the stamp but never a price, when:

* a stamp isn't on a whole minute, doesn't come after the one before it, or isn't on that day;
* the day's session check refuses it (``mcx_check`` for MCX, ``open_check`` for NSE and BSE);
* the day is held already and no reason is given to replace it.

A day goes to a temporary name and is moved into place with ``os.replace``; ``save`` replaces the
manifest the same way, after the days. **The manifest is the record**: a day file it doesn't list
is never read, so a run that stops half way leaves nothing a reader can see.

**What each day was checked against** is kept with it (``DayEntry.checked``):

* ``"calendar"``: MCX. The session's shape (full, evening only, morning only) must be the one
  ``mcx_sessions.yaml`` gives a reason for, a closed day has no bars, and a full session's first
  bar is at the open. The calendar starts on its first entry (25 Dec 2025); a later day it doesn't
  list must be a full session.
* ``"open"``: NSE and BSE. The first bar is at the session's open, and a day the exchange
  closures call closed has no bars.
* ``"stamps only"``: a day older than any calendar we hold, carried from a series that passed its
  own checks when it was built (TICKET-893). Its stamps are checked; its session's shape can't be.
  The crude series has 100 such days before the calendar starts whose first bar isn't at the open
  (evening-only sessions, Budget and muhurat weekends), and nothing lists them.

The manifest's ``days`` map gives each day's row count and the sha256 of its **uncompressed**
text, so a different gzip build can never fail the check. A reader checks that hash before it
uses a day.

Files are read through ``open()`` only. Nothing here imports production or research.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path

from services.shared.market import series as ms

MANIFEST = "manifest.json"
LEVEL = 6
CALENDAR_CHECK, OPEN_CHECK, STAMPS_ONLY = "calendar", "open", "stamps only"

log = logging.getLogger(__name__)

SessionCheck = Callable[[date, list[datetime]], str]
"""Given a day and its minutes, the check it passed, or ``Refused``."""


class Refused(Exception):
    """Nothing was written, and the message says why: dates and stamps, never a price."""


@dataclass(frozen=True)
class DayEntry:
    rows: int
    sha256: str
    """Of the uncompressed text: the header line and the day's rows."""
    checked: str


@dataclass(frozen=True)
class DayManifest:
    underlying: str
    serves: tuple[str, ...]
    source: str
    roll: str
    clock: str
    interval: str
    built: date
    as_of: date
    """The last complete session held."""
    sessions: tuple[str, ...]
    """Every session that was not full, with its reason, one line each."""
    days: dict[str, DayEntry]
    replaced: tuple[str, ...] = ()
    """Each day written over a day already held, with the reason it was asked for."""

    def first_day(self) -> date:
        return date.fromisoformat(min(self.days))

    def covers(self, day: date) -> bool:
        return bool(self.days) and self.first_day() <= day <= self.as_of

    def days_behind(self, today: date) -> int:
        return (today - self.as_of).days


def day_path(folder: str | Path, day: date) -> Path:
    return Path(folder) / f"{day:%Y}" / f"{day.isoformat()}.csv.gz"


def _read(path: Path) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _write(path: Path, data: bytes) -> None:
    """To a temporary name first, then into place: a reader never sees half a file."""
    tmp = path.with_name(path.name + ".part")
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


# ---------- the checks ----------

def _stamp_text(row: bytes) -> str:
    return row.split(b",", 1)[0][:25].decode("ascii", "replace")


def _stamp(row: bytes) -> datetime:
    text = row.split(b",", 1)[0].decode("ascii")
    d, clock = text.split(" ")
    h, m, s = clock.split(":")
    return datetime(int(d[:4]), int(d[5:7]), int(d[8:10]), int(h), int(m), int(s))  # noqa: DTZ001 - naive IST


def check_stamps(day: date, rows: list[bytes]) -> list[datetime]:
    """Every stamp on a whole minute, rising, and on this day. Returns the minutes."""
    if not rows:
        raise Refused(f"{day}: no bars; a day without bars is not written")
    minutes: list[datetime] = []
    for row in rows:
        try:
            t = _stamp(row)
        except (ValueError, UnicodeDecodeError):
            raise Refused(f"{day}: {_stamp_text(row)!r} is not a timestamp") from None
        if t.second:
            raise Refused(f"{day}: {t:%Y-%m-%d %H:%M:%S} is not on a whole minute")
        if t.date() != day:
            raise Refused(f"{t:%Y-%m-%d %H:%M} is not on {day}")
        if minutes and t <= minutes[-1]:
            raise Refused(f"{day}: {t:%H:%M} doesn't come after the row before it")
        minutes.append(t)
    return minutes


def mcx_check(calendar: dict[date, ms.SessionException], session_open: time) -> SessionCheck:
    """MCX's session check against ``mcx_sessions.yaml``, from the calendar's first entry on."""
    start = min(calendar) if calendar else None

    def check(day: date, minutes: list[datetime]) -> str:
        if start is None or day < start:
            return STAMPS_ONLY
        got = ms.check_sessions(minutes, day, day, calendar)
        if not got.ok:
            raise Refused(f"{day}: {got.unexplained[0][1]}, and mcx_sessions.yaml gives no reason for it")
        if ms._shape(minutes) == "full" and day not in calendar and minutes[0].time() != session_open:
            raise Refused(f"{day}: the first bar is at {minutes[0]:%H:%M}, not the open, {session_open:%H:%M}")
        return CALENDAR_CHECK

    return check


def open_check(session_open: time, closed: frozenset[date], through: date | None) -> SessionCheck:
    """NSE and BSE: the first bar at the open, and no bars on a day the closures call closed."""

    def check(day: date, minutes: list[datetime]) -> str:
        if through is not None and day <= through and day in closed:
            raise Refused(f"{day}: the exchange was closed that day, and there are bars")
        if minutes[0].time() != session_open:
            raise Refused(f"{day}: the first bar is at {minutes[0]:%H:%M}, not the open, {session_open:%H:%M}")
        return OPEN_CHECK

    return check


# ---------- the store ----------

class DayStore:
    """One underlying's folder. ``put`` writes days; ``save`` records them in the manifest."""

    def __init__(self, folder: str | Path, underlying: str) -> None:
        self.folder = Path(folder)
        self.underlying = underlying
        self.manifest = read_manifest(self.folder) if (self.folder / MANIFEST).exists() else None
        self.days: dict[str, DayEntry] = dict(self.manifest.days) if self.manifest else {}
        self._replaced: list[str] = list(self.manifest.replaced) if self.manifest else []

    def put(self, day: date, header: bytes, rows: list[bytes], *, check: SessionCheck | None = None,
            reason: str | None = None) -> DayEntry:
        """Check one day and write its file. Refuses before anything reaches disk."""
        if not header.endswith(b"\n"):
            raise Refused("the header line must end with a line end")
        if rows and not rows[-1].endswith(b"\n"):
            raise Refused(f"{day}: the last row must end with a line end")
        minutes = check_stamps(day, rows)
        checked = check(day, minutes) if check is not None else STAMPS_ONLY
        key = day.isoformat()
        if key in self.days and not reason:
            raise Refused(f"{day} is held already; replacing it needs a reason")
        text = header + b"".join(rows)
        entry = DayEntry(rows=len(rows), sha256=hashlib.sha256(text).hexdigest(), checked=checked)
        path = day_path(self.folder, day)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write(path, gzip.compress(text, LEVEL, mtime=0))
        if key in self.days:
            note = f"{key} replaced on {date.today().isoformat()}: {reason}"  # noqa: DTZ011
            self._replaced.append(note)
            log.warning("%s %s", self.underlying, note)
        self.days[key] = entry
        return entry

    def text(self, day: date) -> bytes:
        return read_day(self.folder, day, self.days[day.isoformat()])

    def save(self, *, serves: tuple[str, ...], source: str, roll: str, clock: str, interval: str,
             built: date, sessions: tuple[str, ...] = (), as_of: date | None = None) -> DayManifest:
        """Record every day held in the manifest, replaced after the day files."""
        if not self.days:
            raise Refused(f"{self.underlying}: no days to record")
        m = DayManifest(
            underlying=self.underlying, serves=tuple(serves), source=source, roll=roll, clock=clock,
            interval=interval, built=built, as_of=as_of or date.fromisoformat(max(self.days)),
            sessions=tuple(sessions), days=dict(sorted(self.days.items())), replaced=tuple(self._replaced))
        write_manifest(m, self.folder)
        self.manifest = m
        return m


def read_day(folder: str | Path, day: date, entry: DayEntry) -> bytes:
    """A day's text, after checking it against the hash the manifest holds."""
    path = day_path(folder, day)
    try:
        text = gzip.decompress(_read(path))
    except (OSError, EOFError) as exc:
        raise Refused(f"{day}: {path.name} can't be read ({exc.__class__.__name__})") from None
    if hashlib.sha256(text).hexdigest() != entry.sha256:
        raise Refused(f"{day}: {path.name} doesn't match the hash its manifest holds")
    return text


def write_manifest(m: DayManifest, folder: str | Path) -> None:
    d = asdict(m)
    for k in ("built", "as_of"):
        d[k] = d[k].isoformat()
    d["serves"], d["sessions"], d["replaced"] = list(m.serves), list(m.sessions), list(m.replaced)
    Path(folder).mkdir(parents=True, exist_ok=True)
    _write(Path(folder) / MANIFEST, (json.dumps(d, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))


def manifest_bytes(folder: str | Path) -> bytes:
    return _read(Path(folder) / MANIFEST)


def parse_manifest(raw: bytes) -> DayManifest:
    d = json.loads(raw.decode("utf-8"))
    d["built"], d["as_of"] = date.fromisoformat(d["built"]), date.fromisoformat(d["as_of"])
    d["serves"], d["sessions"] = tuple(d["serves"]), tuple(d["sessions"])
    d["replaced"] = tuple(d.get("replaced", ()))
    d["days"] = {k: DayEntry(**v) for k, v in d["days"].items()}
    return DayManifest(**d)


def read_manifest(folder: str | Path) -> DayManifest:
    return parse_manifest(manifest_bytes(folder))
