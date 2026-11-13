"""The crude 1-minute series: how it is built, how current it is, and which sessions it lacks.

**Construction (TICKET-893).** A continuous future is a construction, not a fact, so the
construction is written here once and recorded in every manifest (``ROLL_CONVENTION``).
The series is MCX's near month: the nearest unexpired CRUDEOIL futures contract, followed
up to and including its last trading day, then the next. Prices are each contract's own,
never back-adjusted, so a roll shows as a jump between one session's close and the next
session's open, and a reader that compares across a roll has to know that.

**Currency.** A series is dated. ``SeriesManifest.as_of`` is its last complete session,
and ``covers(day)`` is the question a claim asks before it uses a bar, so a trade after
``as_of`` gets "series does not cover this date" rather than a stale answer.

**Sessions.** ``check_sessions`` walks every calendar day of a range. A weekday with no
bars, an evening-only or morning-only session, and any weekend session must each be in
the exchange calendar (``mcx_sessions.yaml``) with a reason of the right kind; anything
else is unexplained, and the extension script refuses to write while one remains. A day
the calendar calls closed that traded a full session is unexplained too: a wrong calendar
is found, not trusted.

The mini (CRUDEOILM) trades the same market in the same rupees a barrel, so it is served
by this series (``CRUDE_SERVES``) rather than wanting its own.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

import yaml

CALENDAR = Path(__file__).with_name("mcx_sessions.yaml")
KINDS = ("closed", "evening_only", "morning_only", "special")
EVENING_OPENS = time(17, 0)
"""MCX's evening session opens at 17:00 IST. A session whose first bar is at or after it
is evening only; one whose last bar is before it is morning only."""

CRUDE_SERVES = ("CRUDEOIL", "CRUDEOILM")
ROLL_CONVENTION = (
    "Near month: the series follows the nearest unexpired MCX CRUDEOIL futures contract up to "
    "and including its last trading day, then the next contract from the following session. "
    "Prices are each contract's own, not back-adjusted, so a roll shows as a jump between one "
    "session's close and the next session's open."
)
CLOCK = "IST, naive timestamps; each bar is stamped at the start of its minute"

_SEEN = {"closed": "no bars", "evening_only": "evening only", "morning_only": "morning only"}


@dataclass(frozen=True)
class SessionException:
    day: date
    kind: str
    reason: str


@dataclass(frozen=True)
class SessionCheck:
    listed: tuple[tuple[date, str, str], ...]
    """Sessions that are not full, each with what was seen and the calendar's reason."""
    unexplained: tuple[tuple[date, str], ...]
    """Sessions that are not full and have no reason of the right kind, or that contradict it."""

    @property
    def ok(self) -> bool:
        return not self.unexplained


def load_calendar(path: str | Path = CALENDAR) -> dict[date, SessionException]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    out: dict[date, SessionException] = {}
    for e in raw["sessions"]:
        d = e["day"] if isinstance(e["day"], date) else date.fromisoformat(str(e["day"]))
        if e["kind"] not in KINDS:
            raise ValueError(f"{d}: kind {e['kind']!r} is not one of {KINDS}")
        if d in out:
            raise ValueError(f"{d} is listed twice")
        out[d] = SessionException(d, e["kind"], str(e["reason"]).strip())
    return out


def _shape(minutes: list[datetime]) -> str:
    if not minutes:
        return "no bars"
    if min(minutes).time() >= EVENING_OPENS:
        return "evening only"
    if max(minutes).time() < EVENING_OPENS:
        return "morning only"
    return "full"


def check_sessions(minutes: Iterable[datetime], start: date, end: date,
                   calendar: dict[date, SessionException]) -> SessionCheck:
    by_day: dict[date, list[datetime]] = {}
    for m in minutes:
        if start <= m.date() <= end:
            by_day.setdefault(m.date(), []).append(m)
    listed: list[tuple[date, str, str]] = []
    unexplained: list[tuple[date, str]] = []
    day = start
    while day <= end:
        seen = _shape(by_day.get(day, []))
        entry = calendar.get(day)
        weekend = day.weekday() >= 5
        if seen == "full" and not weekend:
            if entry is not None and entry.kind != "special":
                unexplained.append((day, f"full session, but the calendar says {entry.kind.replace('_', ' ')}"))
        elif seen == "no bars" and weekend:
            pass
        elif entry is not None and (entry.kind == "special" or _SEEN.get(entry.kind) == seen):
            listed.append((day, seen, entry.reason))
        else:
            unexplained.append((day, seen))
        day += timedelta(days=1)
    return SessionCheck(tuple(listed), tuple(unexplained))


@dataclass(frozen=True)
class SeriesManifest:
    underlying: str
    serves: tuple[str, ...]
    file: str
    sha256: str
    rows: int
    first_bar: datetime
    last_bar: datetime
    as_of: date
    """The last complete session in the file."""
    source: str
    roll: str
    clock: str
    interval: str
    built: date
    extended_from: date
    """The first session added by the run that wrote this manifest."""
    sessions: tuple[str, ...]
    """Every session in the added range that was not full, with its reason, one line each."""

    def covers(self, day: date) -> bool:
        return self.first_bar.date() <= day <= self.as_of

    def days_behind(self, today: date) -> int:
        return (today - self.as_of).days


_DATETIMES = ("first_bar", "last_bar")
_DATES = ("as_of", "built", "extended_from")


def write_manifest(m: SeriesManifest, path: str | Path) -> None:
    d = asdict(m)
    for k in _DATETIMES + _DATES:
        d[k] = d[k].isoformat()
    d["serves"], d["sessions"] = list(m.serves), list(m.sessions)
    Path(path).write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_manifest(path: str | Path) -> SeriesManifest:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    for k in _DATETIMES:
        d[k] = datetime.fromisoformat(d[k])
    for k in _DATES:
        d[k] = date.fromisoformat(d[k])
    d["serves"], d["sessions"] = tuple(d["serves"]), tuple(d["sessions"])
    return SeriesManifest(**d)
